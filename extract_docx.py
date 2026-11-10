"""
Extract a Vietnamese multiple-choice exam (.docx) into a structured JSON of
questions, preserving real math (OMML -> LaTeX via pandoc -> Typst) and
legacy MathType OLE equations (read straight from their Equation Native
"TeX Input Language" stream instead of rasterizing the low-res WMF preview).
"""
import io
import json
import os
import re
import unicodedata
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from latex2typst import latex_to_typst
from mtef2latex import mtef_to_latex, MTEFError

try:
    import olefile
except ImportError:
    olefile = None



CAU_RE = re.compile(r'^(?:Câu|CÂU|Bài|BÀI)\s*(\d+)\s*[\.:]?\s*$', re.IGNORECASE)
PHAN_RE = re.compile(r'^PH[ẦA]N\s*([IVX\d]+)\b', re.IGNORECASE)
OPT4_RE = re.compile(r'^(\*?)([A-D])[\.\)]?$')
OPTAD_RE = re.compile(r'^(\*?)([a-d])\)?$')
OPTAD_DOT_RE = re.compile(r'^(\*?)([a-d])[\.\)]?$')  # Phần 2 cho phép "a." lẫn "a)"
# Stricter variants (trailing punctuation mandatory) used only for the
# incremental early-stop scan in split_block_runs -- see the comment there.
_OPT4_STRICT_RE = re.compile(r'^(\*?)([A-D])[\.\)]$')
_OPTAD_STRICT_RE = re.compile(r'^(\*?)([a-d])\)$')
_OPTAD_STRICT_DOT_RE = re.compile(r'^(\*?)([a-d])[\.\)]$')
END_RE = re.compile(r'^[\s….·\.\-–—_*~]*H[ẾE]T[\s….·\.\-–—_*~]*$', re.IGNORECASE)
ESSAY_RE = re.compile(r't[ựư]u?\s*lu[ậa]n', re.IGNORECASE)  # "Tự luận" và lỗi gõ "Tựu luận"
DAPAN_RE = re.compile(r'^Đáp\s*(?:án|số)\s*[:\.]?\s*(.*)$', re.IGNORECASE)


def escape_typst_text(s):
    """Escape a plain text run for safe embedding into Typst markup."""
    if s == '':
        return s
    out = []
    for ch in s:
        if ch in '#*_@$`<>[]\\':
            out.append('\\' + ch)
        else:
            out.append(ch)
    return ''.join(out)


SUPPORTED_IMG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg'}


def normalize_images(media_dir):
    """Typst can only embed .png/.jpg/.jpeg/.gif/.svg images. Most legacy
    formula pictures (.wmf) belong to an OLE MathType object and get replaced
    by real Typst math via extract_ole_math -- but a Word file can also have
    an ordinary PICTURE (a diagram, a pasted screenshot, a stray copy-pasted
    symbol...) saved in .wmf/.emf, which is NOT an OLE math object and so
    never goes through that path. Passing one straight to Typst crashes the
    entire PDF build with "unknown image format". Try to convert any
    unsupported image to PNG (works when Pillow can decode the source
    format); anything that still can't be read is reported back so the
    caller can fall back to a visible in-exam placeholder instead of a hard
    crash that loses every mã đề in the batch.
    Returns (renamed: {'media/old.ext': 'media/new.png'}, failed: {'media/old.ext', ...}).
    """
    renamed = {}
    failed = set()
    media_sub = os.path.join(media_dir, 'media')
    if not os.path.isdir(media_sub):
        return renamed, failed
    for fn in sorted(os.listdir(media_sub)):
        ext = os.path.splitext(fn)[1].lower()
        if ext in SUPPORTED_IMG_EXTS:
            continue
        old_rel = 'media/' + fn
        src = os.path.join(media_sub, fn)
        try:
            from PIL import Image
            im = Image.open(src)
            im.load()
            new_fn = os.path.splitext(fn)[0] + '.png'
            im.convert('RGBA').save(os.path.join(media_sub, new_fn))
            renamed[old_rel] = 'media/' + new_fn
        except Exception:
            failed.add(old_rel)
    return renamed, failed


def extract_ole_math(docx_path):
    """Return {image_basename: tex_string} for every legacy MathType OLE object."""
    mapping = {}
    if olefile is None:
        return mapping
    with zipfile.ZipFile(docx_path) as z:
        try:
            rels = z.read('word/_rels/document.xml.rels')
        except KeyError:
            return mapping
        root = ET.fromstring(rels)
        ns = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
        rel_target = {}
        for el in root.findall('r:Relationship', ns):
            rel_target[el.get('Id')] = el.get('Target')

        doc_xml = z.read('word/document.xml').decode('utf-8', 'replace')
        for m in re.finditer(r'<w:object.*?</w:object>', doc_xml, re.S):
            seg = m.group(0)
            rids = re.findall(r'r:id="(rId\d+)"', seg)
            img_target = ole_target = None
            for rid in rids:
                tgt = rel_target.get(rid, '')
                if tgt.startswith('media/'):
                    img_target = os.path.basename(tgt)
                elif tgt.startswith('embeddings/'):
                    ole_target = tgt
            if not (img_target and ole_target):
                continue
            try:
                data = z.read('word/' + ole_target)
            except KeyError:
                continue
            try:
                ole = olefile.OleFileIO(io.BytesIO(data))
                stream = ole.openstream('Equation Native').read()
            except Exception:
                continue
            tex = None
            marker = b'TeX Input Language'
            idx = stream.find(marker)
            if idx != -1:
                start = idx + len(marker)
                if start < len(stream) and stream[start] == 0:
                    start += 1
                end = stream.find(b'\x00', start)
                if end == -1:
                    end = len(stream)
                raw = stream[start:end]
                try:
                    tex = raw.decode('utf-8')
                except UnicodeDecodeError:
                    tex = raw.decode('latin-1')
            if not tex:
                # No embedded "TeX Input Language" string (MathType only writes
                # it when its TeX translator option was on). Decode the raw
                # binary MTEF equation data itself instead. If that fails, leave
                # this object out of the mapping so the caller falls back to the
                # visible placeholder -- never guess a formula.
                try:
                    hdr_len = int.from_bytes(stream[0:2], 'little')
                    if 0 < hdr_len < len(stream):
                        tex = mtef_to_latex(stream[hdr_len:]).strip()
                except (MTEFError, IndexError, ValueError):
                    tex = None
            if tex:
                mapping[img_target] = tex
    return mapping


def run_pandoc(docx_path, media_dir):
    os.makedirs(media_dir, exist_ok=True)
    out_json = os.path.join(media_dir, '_ast.json')
    subprocess.run(
        ['pandoc', '-f', 'docx', '-t', 'json',
         '--extract-media', media_dir, docx_path, '-o', out_json],
        check=True, capture_output=True,
    )
    with open(out_json, encoding='utf-8') as f:
        return json.load(f)


def flatten_inlines(inlines, strong=False, underline=False, runs=None):
    """underline is tracked separately from strong: some source .docx files
    mark the CORRECT multiple-choice answer by underlining its letter instead
    of (or in addition to) the documented '*' prefix convention, so we need
    to know which text was underlined, not just which was bold."""
    if runs is None:
        runs = []
    for x in inlines:
        t = x['t']
        c = x.get('c')
        if t == 'Str':
            runs.append({'type': 'text', 'value': unicodedata.normalize('NFC', c), 'strong': strong, 'underline': underline})
        elif t == 'Space':
            runs.append({'type': 'text', 'value': ' ', 'strong': False, 'underline': False})
        elif t == 'SoftBreak':
            runs.append({'type': 'text', 'value': ' ', 'strong': False, 'underline': False})
        elif t == 'LineBreak':
            runs.append({'type': 'break', 'value': '', 'strong': False, 'underline': False})
        elif t == 'Math':
            runs.append({'type': 'math', 'value': c[1], 'strong': strong, 'underline': underline})
        elif t == 'Image':
            runs.append({'type': 'image', 'value': c[2][0], 'strong': False, 'underline': False})
        elif t in ('Strong',):
            flatten_inlines(c, True, underline, runs)
        elif t == 'Underline':
            flatten_inlines(c, strong, True, runs)
        elif t == 'Emph':
            flatten_inlines(c, strong, underline, runs)
        elif t == 'Span':
            # Pandoc's Span is [Attr, [Inline]] -- a 2-element array, so the
            # inline content is c[1], not c[2] (an out-of-range index that
            # only surfaces when a source .docx actually contains a Span,
            # e.g. highlighted/colored text or a language-tagged run).
            flatten_inlines(c[1], strong, underline, runs)
        elif t == 'Quoted':
            q = '"' if c[0]['t'] == 'DoubleQuote' else "'"
            runs.append({'type': 'text', 'value': q, 'strong': strong, 'underline': underline})
            flatten_inlines(c[1], strong, underline, runs)
            runs.append({'type': 'text', 'value': q, 'strong': strong, 'underline': underline})
        else:
            pass
    return runs


def block_to_runs(block):
    if block['t'] == 'Para' or block['t'] == 'Plain':
        return flatten_inlines(block['c'])
    return []


def _item_has_cau_label(item_blocks):
    """True if a Word auto-numbered list item already starts with a manually
    typed, bold 'Câu N.' (so we must NOT inject a synthetic one on top)."""
    for ib in item_blocks:
        if ib['t'] in ('Para', 'Plain'):
            runs = flatten_inlines(ib['c'])
            bold_text = ''.join(r['value'] for r in runs if r['type'] == 'text' and r['strong'])
            return bool(CAU_RE.match(re.sub(r'\s+', ' ', bold_text).strip()))
        if ib['t'] == 'BlockQuote':
            continue
        return False
    return False


def expand_blocks(blocks):
    """Yield (block_type, block) pairs, unwrapping BlockQuote into its child
    Paras and OrderedList items into a synthetic bold 'Câu N.' marker (using
    Word's own list number) followed by the item's content. This lets a
    source .docx number Phần-1-style questions either by typing 'Câu N.' by
    hand OR by relying on Word's automatic numbered-list numbering -- both
    end up going through the exact same downstream parsing logic below."""
    out = []
    for b in blocks:
        if b['t'] == 'BlockQuote':
            for bb in b['c']:
                out.append(bb)
        elif b['t'] == 'OrderedList':
            attribs, items = b['c']
            start = attribs[0]
            for idx, item_blocks in enumerate(items):
                if not _item_has_cau_label(item_blocks):
                    num = start + idx
                    out.append({'t': 'Para', 'c': [
                        {'t': 'Strong', 'c': [{'t': 'Str', 'c': 'Câu'}, {'t': 'Space'}, {'t': 'Str', 'c': f'{num}.'}]}
                    ]})
                for ib in item_blocks:
                    if ib['t'] == 'BlockQuote':
                        for bb in ib['c']:
                            out.append(bb)
                    else:
                        out.append(ib)
        else:
            out.append(b)
    return out


def runs_to_typst(runs, ole_math, images_out, img_renamed=None, img_failed=None, warnings=None):
    """Convert a run list into an inline Typst source string."""
    img_renamed = img_renamed or {}
    img_failed = img_failed or set()
    parts = []
    ole_idx = []  # indexes in `parts` that hold a formula (Equation or MathType)
    for r in runs:
        if r['type'] == 'text':
            parts.append(escape_typst_text(r['value']))
        elif r['type'] == 'break':
            parts.append(' \\ ')
        elif r['type'] == 'math':
            typ = latex_to_typst(r['value'])
            if typ:
                ole_idx.append(len(parts))
            parts.append(f'${typ}$' if typ else '')
        elif r['type'] == 'image':
            base = os.path.basename(r['value'])
            if base in ole_math:
                typ = latex_to_typst(ole_math[base])
                if typ:
                    ole_idx.append(len(parts))
                parts.append(f'${typ}$' if typ else '')
                continue
            rel_key = 'media/' + base
            path = r['value']
            if rel_key in img_renamed:
                path = os.path.join(os.path.dirname(os.path.dirname(r['value'])), img_renamed[rel_key])
            if rel_key in img_failed:
                if warnings is not None:
                    warnings.append(base)
                parts.append('#text(fill: red, style: "italic")[\\[Không hiển thị được hình/công thức ở đây - vui lòng kiểm tra lại trong file gốc: ' + escape_typst_text(base) + '\\]]')
                continue
            # Typst requires forward slashes in every path, on every OS --
            # os.path.join() on Windows produces backslashes, which Typst
            # rejects outright ("path must not contain a backslash"). Convert
            # right here, once, so every downstream consumer of this string
            # (including build_exam.py's later media_dir -> _exam_media
            # rewrite) is working with the same forward-slash form.
            path = path.replace('\\', '/')
            images_out.append(path)
            parts.append(f'#exam-image("{path}", width: 42%)')
    # A formula sitting directly against a word ("<formula>thì") has no
    # space in the .docx itself -- Word hides that because the object carries
    # its own padding. Rendered as plain math it would fuse with the word, so
    # add a space when a letter touches either side of such a formula.
    for i in ole_idx:
        if i + 1 < len(parts) and parts[i + 1][:1].isalpha():
            parts[i + 1] = ' ' + parts[i + 1]
        if i > 0 and parts[i - 1][-1:].isalpha():
            parts[i - 1] = parts[i - 1] + ' '
    text = ''.join(parts)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'[`*\\]+\s*$', '', text.strip())
    return text.strip()


def extract_answer_runs(seg_runs):
    """Given a Part-3 paragraph's run list that starts with 'Đáp án:' /
    'Đáp số:', return the runs making up the answer itself (dropping the
    label). The answer is often typeset as an inline math formula rather
    than plain digits, so this keeps any Math run instead of only the
    plain-text characters that come after the label."""
    text_only_join = ''.join(r['value'] for r in seg_runs if r['type'] == 'text')
    stripped = text_only_join.strip()
    m = DAPAN_RE.match(stripped)
    if not m:
        return None
    prefix_len = len(stripped) - len(m.group(1))
    leading_ws = len(text_only_join) - len(text_only_join.lstrip())
    cut_at = leading_ws + prefix_len
    consumed = 0
    started = False
    out = []
    for r in seg_runs:
        if r['type'] == 'text':
            if not started:
                take = len(r['value'])
                if consumed + take <= cut_at:
                    consumed += take
                    continue
                keep_from = cut_at - consumed
                new_r = dict(r)
                new_r['value'] = r['value'][keep_from:]
                out.append(new_r)
                consumed = cut_at
                started = True
                continue
            out.append(r)
        else:
            started = True
            out.append(r)
    return out


def runs_plain_label(runs):
    """If this run-list is ONLY a bold label like 'A.' / '*b)' / 'Câu 3.', return it stripped."""
    texty = [r for r in runs if r['type'] == 'text' and r['value'].strip() != '']
    if len(texty) == 1 and texty[0]['strong']:
        return texty[0]['value'].strip()
    # allow "Câu" + " " + "3." split across runs
    joined = ''.join(r['value'] for r in runs if r['type'] == 'text').strip()
    if all(r['strong'] or r['value'].strip() == '' for r in runs if r['type'] == 'text'):
        return joined
    return None


def _expected_next_letter(cur_kind, cur_label):
    """If we're currently inside an option (cur_label is ('A'/'a'-style
    tuple)), what's the NEXT letter in sequence -- used to safely recognize
    an un-bolded label ("B." typed as plain text) that isn't the first token
    of its paragraph, without risking a false match on ordinary prose that
    happens to contain a standalone "A." (e.g. "...điểm A."): only accepted
    when it's exactly the next letter expected right after the current one."""
    if cur_kind not in ('opt4', 'optad') or cur_label is None:
        return None
    _, letter = cur_label
    nxt = chr(ord(letter) + 1)
    if cur_kind == 'opt4' and nxt <= 'D':
        return nxt
    if cur_kind == 'optad' and nxt <= 'd':
        return nxt
    return None


def split_block_runs(runs, lower_dot=False):
    """Split one paragraph's run list at bold option-label / Câu / PHẦN boundaries.
    Returns list of (label_or_None, kind, runs_segment)."""
    segments = []
    cur_label, cur_kind, cur = None, None, []
    i = 0
    n = len(runs)
    oad_re = OPTAD_DOT_RE if lower_dot else OPTAD_RE
    oad_strict_re = _OPTAD_STRICT_DOT_RE if lower_dot else _OPTAD_STRICT_RE
    while i < n:
        r = runs[i]
        if i == 0 and r['type'] == 'text' and not r['strong'] and re.match(r'^(Câu|CÂU|Bài|BÀI|PH[ẦA]N|Phan)\b', r['value'].strip(), re.IGNORECASE):
            # Some source files never bold "Câu N:" / "PHẦN N" at all (unlike
            # every other convention seen so far, all plain text). Only tried
            # at the very start of a paragraph -- that's the only place these
            # labels ever appear -- and only once the FIRST run already looks
            # like the start of one (cheap prefix check) so a normal stem
            # paragraph never pays for an unbounded scan here.
            j2 = i
            acc2 = ''
            found = None
            while j2 < n and runs[j2]['type'] == 'text':
                acc2 += runs[j2]['value']
                j2 += 1
                stripped2 = re.sub(r'\s+', ' ', acc2).strip()
                mcau2 = CAU_RE.match(stripped2)
                if mcau2:
                    found = ('cau', stripped2, j2)
                    break
                mphan2 = PHAN_RE.match(stripped2)
                if mphan2:
                    found = ('phan', stripped2, j2)
                    break
                if len(stripped2) > 40:
                    break
            if found:
                kind2, combined2, end2 = found
                if cur or cur_label is not None:
                    segments.append((cur_label, cur_kind, cur))
                cur = []
                cur_label, cur_kind = combined2, kind2
                i = end2
                continue
        if r['type'] == 'text' and not r['strong']:
            # Some source files never bold option labels at all ("A." "B."
            # typed as plain text, even several per paragraph: "A. ... B. ...").
            # Recognize one when it's the very first token of its own
            # paragraph (unambiguous on its own) OR when it's exactly the
            # next letter expected after the option we're currently building
            # (safe even mid-paragraph/mid-sentence, since a coincidental
            # "A." in prose would essentially never land right where "B." is
            # expected next).
            stripped0 = r['value'].strip()
            m_o4_solo = OPT4_RE.match(stripped0)
            m_oad_solo = oad_re.match(stripped0)
            expected = _expected_next_letter(cur_kind, cur_label)
            take = None
            if i == 0 and (m_o4_solo or m_oad_solo):
                take = m_o4_solo or m_oad_solo
                take_kind = 'opt4' if m_o4_solo else 'optad'
            elif expected is not None:
                if m_o4_solo and cur_kind == 'opt4' and m_o4_solo.group(2) == expected:
                    take, take_kind = m_o4_solo, 'opt4'
                elif m_oad_solo and cur_kind == 'optad' and m_oad_solo.group(2) == expected:
                    take, take_kind = m_oad_solo, 'optad'
            if take is not None:
                if cur or cur_label is not None:
                    segments.append((cur_label, cur_kind, cur))
                cur = []
                cur_label, cur_kind = (take.group(1) == '*', take.group(2)), take_kind
                i += 1
                continue
        if r['type'] == 'text' and r['strong']:
            val = r['value'].strip()
            # Incrementally grow a "bold phrase" starting here, stopping as soon
            # as it forms a complete "Câu N." / "*A." / "*a)" label (so a
            # trailing bold annotation right after -- a difficulty tag "(TH)"
            # after "Câu N.", or a tag like "[TD 1.1]" after an option letter --
            # doesn't get swallowed into the same streak and break the match).
            # The label sub-patterns require their punctuation here (unlike the
            # looser OPT4_RE/OPTAD_RE used elsewhere) specifically to avoid a
            # bare bold single letter ("cho điểm **A**") being mistaken for a
            # label mid-stream; the no-punctuation case is only accepted where
            # it's unambiguous (very first token of the whole paragraph, or the
            # expected next letter in an already-open option list).
            j = i
            acc = ''
            early_kind, early_match, early_end = None, None, None
            underline_label = False
            while j < n and runs[j]['type'] == 'text' and (runs[j]['strong'] or runs[j]['value'].strip() == ''):
                if runs[j].get('underline') and runs[j]['value'].strip() != '':
                    underline_label = True
                acc += runs[j]['value']
                j += 1
                stripped = re.sub(r'\s+', ' ', acc).strip()
                mc = CAU_RE.match(stripped)
                if mc:
                    early_kind, early_match, early_end = 'cau', mc, j
                    break
                mo = _OPT4_STRICT_RE.match(stripped)
                if mo:
                    early_kind, early_match, early_end = 'o4', mo, j
                    break
                ma = oad_strict_re.match(stripped)
                if ma:
                    early_kind, early_match, early_end = 'oad', ma, j
                    break
            cau_match_end = early_end if early_kind == 'cau' else None
            if early_kind is not None:
                combined = re.sub(r'\s+', ' ', acc).strip()
                j = early_end
                m_cau = early_match if early_kind == 'cau' else None
                m_phan = None
                m_o4 = early_match if early_kind == 'o4' else None
                m_oad = early_match if early_kind == 'oad' else None
            else:
                # re-scan the full streak (no early "Câu" match) for PHẦN / option labels
                j = i
                streak_vals = []
                while j < n and runs[j]['type'] == 'text' and (runs[j]['strong'] or runs[j]['value'].strip() == ''):
                    sv = runs[j]['value']
                    if runs[j].get('underline') and sv.strip() != '':
                        underline_label = True
                    streak_vals.append(sv)
                    j += 1
                # combined = the WHOLE streak joined (a label like "B." can arrive as
                # separate runs, e.g. an underlined "B" followed by a plain "."), so
                # match the option-label regexes against the full streak, not just
                # the first run's text -- matching only the first run silently drops
                # any option label split across differently-formatted runs.
                combined = re.sub(r'\s+', ' ', ''.join(streak_vals)).strip()
                m_cau = None
                m_phan = PHAN_RE.match(combined)
                m_o4 = OPT4_RE.match(combined)
                m_oad = oad_re.match(combined)
                if not (m_phan or m_o4 or m_oad):
                    j = i + 1
            # A label is only accepted here if it's safely unambiguous: the
            # very first thing in this paragraph (i==0), the first option
            # right after a "Câu N." we just matched (cur_kind=='cau'), or
            # exactly the next letter expected in an option sequence already
            # under way (cur_kind matches and the letter follows in order).
            # Without this, retrying the match word-by-word after a failed
            # attempt -- needed so e.g. "A. . B. . C. . D." on one bold line
            # still finds B/C/D -- also lets ordinary SENTENCES that happen
            # to mention a câu number or list "a), b), c), d)" (confirmed
            # against a real file: instructions reading "...trả lời câu 13,
            # câu 14... Trong mỗi ý a), b), c), d)..." right after a "PHẦN
            # II." header) get misread as real question/option boundaries.
            if m_cau and cur_kind is not None:
                m_cau = None
            if (m_o4 or m_oad) and i != 0:
                letter = (m_o4 or m_oad).group(2)
                expected = _expected_next_letter(cur_kind, cur_label)
                first_ok = cur_kind in (None, 'cau') and letter in ('A', 'a')
                next_ok = expected is not None and letter == expected
                if not (first_ok or next_ok):
                    m_o4 = m_oad = None
            if m_cau or m_phan or m_o4 or m_oad:
                star_prefix = False
                if m_o4 or m_oad:
                    trimmed = list(cur)
                    while trimmed and trimmed[-1]['type'] == 'text' and trimmed[-1]['value'].strip() == '':
                        trimmed.pop()
                    if trimmed and trimmed[-1]['type'] == 'text' and trimmed[-1]['value'].strip() == '*':
                        star_prefix = True
                        cur = trimmed[:-1]
                if cur or cur_label is not None:
                    segments.append((cur_label, cur_kind, cur))
                cur = []
                if m_cau:
                    cur_label, cur_kind = combined, 'cau'
                    i = j
                    continue
                elif m_phan:
                    cur_label, cur_kind = combined, 'phan'
                    i = j
                    continue
                elif m_o4:
                    # Correct answer can be marked either with a leading '*' (documented
                    # convention) or by underlining the option letter itself (a common
                    # convention in older Vietnamese exam docs) -- accept either.
                    starred = (m_o4.group(1) == '*') or star_prefix or underline_label
                    cur_label, cur_kind = (starred, m_o4.group(2)), 'opt4'
                elif m_oad:
                    starred = (m_oad.group(1) == '*') or star_prefix or underline_label
                    cur_label, cur_kind = (starred, m_oad.group(2)), 'optad'
                i = j
                continue
        cur.append(r)
        i += 1
    if cur or cur_label is not None:
        segments.append((cur_label, cur_kind, cur))
    return segments


def parse_docx(docx_path, media_dir):
    ole_math = extract_ole_math(docx_path)
    ast = run_pandoc(docx_path, media_dir)
    img_renamed, img_failed = normalize_images(media_dir)
    warnings = []
    blocks = expand_blocks(ast['blocks'])

    questions = []
    cur_q = None
    cur_part = 1
    part_titles = {}
    pending_images = []

    def r2t(runs, images_out):
        return runs_to_typst(runs, ole_math, images_out, img_renamed, img_failed, warnings)

    def flush_stem(runs):
        nonlocal cur_q
        typ = r2t(runs, cur_q['images'])
        if typ:
            cur_q['stem_parts'].append(typ)

    mode = 'stem'  # or 'answer' (part 3, after "Lời giải")

    for block in blocks:
        if block['t'] == 'Table':
            if cur_q is not None:
                cur_q['tables'].append(block)
            continue
        runs = block_to_runs(block)
        if not runs:
            continue
        _plain = ''.join(r['value'] for r in runs if r['type'] == 'text')
        if END_RE.match(_plain):
            break  # dòng "……… HẾT ………" -> hết đề, bỏ qua mọi thứ phía sau
        segments = split_block_runs(runs, lower_dot=(cur_part == 2))
        for label, kind, seg_runs in segments:
            if kind == 'phan':
                _mp = re.search(r'PH[ẦA]N\s*([IVX\d]+)', label, re.IGNORECASE)
                if ESSAY_RE.search(label) or (_mp and _mp.group(1).upper() in ('4', 'IV')):
                    # "Tự luận" (free-response/essay): no A/B/C/D or a/b/c/d
                    # structure to extract here, and -- per how every exam
                    # using this section actually works -- it must NOT be
                    # shuffled like Part 1/2/3: every mã đề carries the exact
                    # same essay questions, unchanged, appended at the end.
                    cur_part = 'essay'
                else:
                    mroman = re.search(r'PH[ẦA]N\s*([IVX\d]+)', label, re.IGNORECASE)
                    token = mroman.group(1).upper() if mroman else '1'
                    roman = {'I': 1, 'II': 2, 'III': 3}.get(token, None)
                    cur_part = roman if roman else (int(token) if token.isdigit() else 1)
                mode = 'stem'
                continue
            if kind == 'cau':
                num = re.search(r'\d+', label).group(0)
                _word = 'Bài' if re.match(r'\s*B[àÀaA]i', label, re.IGNORECASE) else 'Câu'
                cur_q = {
                    'part': cur_part, 'num': int(num), 'word': _word, 'stem_parts': [],
                    'options': [], 'images': [], 'tables': [], 'answer': None,
                }
                questions.append(cur_q)
                mode = 'stem'
                if seg_runs:
                    flush_stem(seg_runs)
                continue
            if cur_q is None:
                continue
            if cur_q.get('part') == 'essay':
                # File đề gốc thường kèm "Lời giải"/"Đáp án" sau mỗi bài: không đưa vào đề
                # (giống Phần 1-3). Bỏ qua cho đến khi gặp "Câu/Bài N." hoặc "PHẦN" kế tiếp.
                if mode == 'answer':
                    continue
                _pt = ''.join(r['value'] for r in seg_runs if r['type'] == 'text').strip()
                if kind is None and (re.match(r'^L(ời|OI)\s*gi[ảa]i', _pt, re.IGNORECASE)
                                     or DAPAN_RE.match(_pt)
                                     or re.match(r'^H(ướng|UONG)\s*d[ẫa]n', _pt, re.IGNORECASE)):
                    mode = 'answer'
                    continue
                # Free-response content: no multiple-choice structure, so
                # don't extract opt4/optad into options[] -- preserve
                # everything (including any "a)"/"b)" sub-part labels) as
                # plain visible stem text, exactly as it reads in the source.
                if kind in ('opt4', 'optad'):
                    _, letter = label
                    prefix = f'{letter}.' if kind == 'opt4' else f'{letter})'
                    typ = r2t(seg_runs, cur_q['images'])
                    if typ:
                        cur_q['stem_parts'].append(f'{prefix} {typ}')
                else:
                    flush_stem(seg_runs)
                continue
            if mode == 'answer' and kind in ('opt4', 'optad'):
                # We're past a "Lời giải" (solution) marker for this question.
                # A worked solution very often restates each choice's verdict
                # per letter ("a) ĐÚNG.", "b) SAI", ...), which otherwise
                # matches the exact same option-label pattern as the real
                # options above it and would silently get appended as
                # EXTRA/duplicate options. Ignore any option-looking segment
                # until the next "Câu N."/"PHẦN" resets mode back to 'stem'.
                continue
            if kind == 'opt4':
                correct, letter = label
                typ = r2t(seg_runs, cur_q['images'])
                cur_q['options'].append({'label': letter, 'correct': correct, 'content': typ})
                continue
            if kind == 'optad':
                correct, letter = label
                typ = r2t(seg_runs, cur_q['images'])
                cur_q['options'].append({'label': letter, 'correct': correct, 'content': typ})
                continue
            # plain (unlabeled) segment
            plain_text = ''.join(r['value'] for r in seg_runs if r['type'] == 'text').strip()
            if re.match(r'^L(ời|OI)\s*gi[ảa]i', plain_text, re.IGNORECASE):
                mode = 'answer'
                continue
            m_da = DAPAN_RE.match(plain_text)
            if m_da and cur_q is not None:
                ans_runs = extract_answer_runs(seg_runs) or []
                typ = r2t(ans_runs, cur_q['images']).strip()
                cur_q['answer'] = typ if typ else m_da.group(1).strip()
                mode = 'answer'
                continue
            if mode == 'answer':
                # ignore further solution text
                continue
            if cur_q is not None:
                flush_stem(seg_runs)

    for q in questions:
        q['stem'] = '\n\n'.join(p for p in q['stem_parts'] if p)
        del q['stem_parts']
        del q['tables']

    return questions, warnings


def extract_header(ast):
    """Best-effort extraction of (school, title_lines, time_line) from the
    docx's opening 2-cell title table. Falls back to generic Vietnamese defaults."""
    blocks = ast.get('blocks', [])
    school, title_lines = None, []
    if blocks and blocks[0]['t'] == 'Table':
        try:
            c = blocks[0]['c']
            row_lists = [c[3][1]] if c[3][1] else []
            for tbody in c[4]:
                row_lists.append(tbody[2])
                row_lists.append(tbody[3])
            rows = [r for rl in row_lists for r in rl]
            cells = rows[0][1]
            cell0, cell1 = cells[0], cells[1]
            r0 = flatten_inlines([x for b in cell0[4] for x in b.get('c', [])])
            school = ''.join(r['value'] for r in r0 if r['type'] == 'text').strip()
            for b in cell1[4]:
                r = flatten_inlines(b.get('c', []))
                t = ''.join(x['value'] for x in r if x['type'] == 'text').strip()
                if t and not set(t) <= {'-'}:
                    title_lines.append(t)
        except Exception:
            pass
    school = school or 'TRƯỜNG ...'
    if title_lines:
        main_title = title_lines[0]
        subtitle = title_lines[1] if len(title_lines) > 1 else ''
        time_line = title_lines[2] if len(title_lines) > 2 else 'Thời gian làm bài: ... phút'
    else:
        main_title, subtitle, time_line = 'ĐỀ KIỂM TRA', '', 'Thời gian làm bài: ... phút'
    return {'school': school, 'title': main_title, 'subtitle': subtitle, 'time': time_line}


if __name__ == '__main__':
    docx = sys.argv[1] if len(sys.argv) > 1 else 'DE_NGUON.docx'
    qs = parse_docx(docx, 'media_extract')
    print(f'Parsed {len(qs)} questions')
    for q in qs[:3]:
        print(json.dumps(q, ensure_ascii=False, indent=2)[:800])
    by_part = {}
    for q in qs:
        by_part.setdefault(q['part'], []).append(q)
    for p, arr in sorted(by_part.items()):
        print('Part', p, ':', len(arr), 'questions')