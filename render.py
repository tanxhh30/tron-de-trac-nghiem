import os
import re
import typst

PREAMBLE = r'''
#let made = "{made}"
#set page(
  paper: "a4",
  margin: (x: 1.8cm, y: 2cm),
  footer: [
    #set text({s_foot}pt, font: {f_foot})
    #text(fill: rgb("#0047AB"))[Mã đề {made}] #h(1fr) #text()[Trang #context counter(page).display() / #context counter(page).final().first()]
  ],
)
#set text(font: {f_body}, size: {s_body}pt, lang: "vi")
#show heading: set text(font: {f_title}, size: {s_title}pt)
#set par(justify: true, leading: {l_body}em, spacing: {l_par}em)
#show math.equation: set text(font: ("New Computer Modern Math", "Times New Roman"))

// Khoảng cách dòng RIÊNG cho phần đáp án (A/B/C/D, a/b/c/d) -- rộng hơn khoảng
// cách dòng thường để đủ chỗ cho phân số/công thức cao. Chỉnh bằng 'gian_dong_dap_an'
// (chay.py hoặc ô "Khoảng cách dòng – đáp án" trên giao diện).
#let dap-an-leading = {l_ans}em

// Khoảng thụt lề đầu mỗi dòng đáp án (A/B/C/D, a/b/c/d). Chỉnh số này nếu
// muốn thụt nhiều/ít hơn.
#let dap-an-indent = 0.5cm

// Cung tròn (không mũi tên): dấu cung ⌒ phía trên nội dung -- dùng cho đáp án
// kiểu "sđ cung AM". (Dấu nón \widehat ở phần đề vẫn là hat(...).)
#let overarc(body) = math.accent(body, sym.paren.t)

// Dấu cung (ký hiệu cung AM, "sđ AM"): đặt mũi tên cong ↷ phía trên nội dung.
// Chỉnh dy (độ cao mũi tên) hoặc size (cỡ mũi tên) nếu muốn lệch/to/nhỏ hơn.
#let cung(body) = {{
  box(baseline: 0%, {{
    body
    place(
      top + center,
      dy: -0.55em,
      text(size: 0.9em)[↷]
    )
  }})
}}

// Độ rộng ảnh mặc định khi không ghi rõ. Muốn chỉnh riêng 1 ảnh nào đó: sửa
// trực tiếp dòng #exam-image(...) tương ứng trong đề, thêm width:, ví dụ
// #exam-image("_exam_media/media/image10.png", width: 37%)
// Ảnh luôn giữ ĐÚNG độ rộng đã ghi (không tự co nhỏ để nhét vào chỗ trống cuối trang).
// Cách làm: đo chiều cao thật của ảnh rồi cố định luôn chiều cao đó; nếu không đủ chỗ ở cuối
// trang thì nguyên cả ảnh được đẩy sang trang sau. Chỉnh độ rộng bằng width: (vd 50% hoặc 6cm).
#let exam-image(path, width: 42%) = align(center)[#block(above: 0.5em, below: 0.5em, breakable: false)[
  #layout(size => {{
    let w = if type(width) == ratio {{ size.width * width }} else if type(width) == relative {{ size.width * width.ratio + width.length }} else {{ width }}
    let h = measure(image(path, width: w)).height
    if h > 24cm {{ w = w * (24cm / h); h = 24cm }}
    image(path, width: w, height: h)
  }})
]]

#let choices(..items) = layout(size => {{
  let its = items.pos()
  let w = calc.max(..its.map(it => measure(it).width)) + dap-an-indent
  let g = 1.6 * measure(box(width: 1em)).width
  let cols = if 4 * w + 3 * g <= size.width {{ 4 }} else if 2 * w + g <= size.width {{ 2 }} else {{ 1 }}
  block(above: 0.6em, below: 0.7em)[
    #set par(leading: dap-an-leading)
    #grid(columns: (1fr,) * cols, column-gutter: g, row-gutter: 0.9em, inset: (left: dap-an-indent), ..its)
  ]
}})

#let tf-choices(..items) = block(above: 0.8em, below: 0.7em)[
  #set par(leading: dap-an-leading)
  #for it in items.pos() [
    #h(dap-an-indent)#it
    #v(0.5em)
  ]
]

// === HEADER ===
#block(width: 100%)[
  #set text(font: {f_head}, size: {s_head}pt)
  #set par(justify: false, leading: 0.55em)
  #grid(columns: (1fr, 1fr), column-gutter: 0.3cm, align: center + top,
    [
      {so} \
      #text(weight: "bold")[{school}] \
      #v(0.5em)
      #box(stroke: 0.8pt, inset: (x: 0.6cm, y: 0.3cm))[#text(weight: "bold")[MÃ ĐỀ: {made}]]
    ],
    [
      #text(weight: "bold")[{title}] \
      #text(weight: "bold")[{namhoc}] \
      #text(weight: "bold")[{mon}] \
      #text(style: "italic")[{time}]
    ],
  )
]
#v(1.1em)
#block(width: 100%, inset: (x: 0.8cm))[
  #set text(font: {f_head}, size: {s_head}pt)
  #text(weight: "bold")[Họ, tên thí sinh:] #box(width: 1fr, repeat[…]) #text(weight: "bold")[Số báo danh:] #box(width: 4.8cm, repeat[…])
]
#v(0.8em)
// === BODY ===
'''

# Nội dung phần đầu trang (mặc định theo mẫu của trường). Ghi đè bằng tham số
# tieu_de={...} của tron_de() hoặc biến TIEU_DE trong chay.py.
DEFAULT_HEADER = {
    'so': 'SỞ GIÁO DỤC VÀ ĐÀO TẠO AN GIANG',
    'school': 'TRƯỜNG PT iSCHOOL LONG XUYÊN',
    'title': 'ĐỀ KIỂM TRA CUỐI HỌC KỲ I',
    'namhoc': 'NĂM HỌC 2025 - 2026',
    'mon': 'Môn: TOÁN 11',
    'time': 'Thời gian: 90 phút, không kể thời gian phát đề',
    'het': '__________HẾT__________',   # dòng cuối đề (in đậm, nghiêng); để trống nếu không dùng
}

# Font chữ / cỡ chữ (pt) của từng mục. Ghi đè bằng tham số dinh_dang={...} của
# tron_de() hoặc biến DINH_DANG trong chay.py. Font không có trong máy sẽ tự
# chuyển sang Liberation Serif / Noto Serif.
DEFAULT_STYLE = {
    'font_noi_dung': 'Times New Roman', 'co_noi_dung': 11,     # câu hỏi + đáp án
    'font_dau_trang': 'Times New Roman', 'co_dau_trang': 12,   # khối tiêu đề, Họ tên, SBD
    'font_tieu_muc': 'Times New Roman', 'co_tieu_muc': 13,     # "PHẦN 1. Trắc nghiệm..."
    'font_chan_trang': 'Tahoma', 'co_chan_trang': 9,           # "Mã đề / Trang x / y"
    'font_bang_dap_an': 'Tahoma', 'co_bang_dap_an': 10.5,      # file dap_an.pdf
    # Khoảng cách (đơn vị em, 1em = cỡ chữ): giữa các dòng của đề bài / của đáp án / giữa các câu
    'gian_dong': 0.62, 'gian_dong_dap_an': 0.95, 'gian_cau': 1.2,
}


def _font_tuple(name):
    name = str(name).replace('\\', '').replace('"', '')
    return f'("{name}", "Liberation Serif", "Liberation Sans", "Noto Serif")'


def _style_args(style):
    st = {**DEFAULT_STYLE, **(style or {})}
    num = lambda k: format(float(st[k]), 'g')
    return dict(
        f_body=_font_tuple(st['font_noi_dung']), s_body=num('co_noi_dung'),
        f_head=_font_tuple(st['font_dau_trang']), s_head=num('co_dau_trang'),
        f_title=_font_tuple(st['font_tieu_muc']), s_title=num('co_tieu_muc'),
        f_foot=_font_tuple(st['font_chan_trang']), s_foot=num('co_chan_trang'),
        f_key=_font_tuple(st['font_bang_dap_an']), s_key=num('co_bang_dap_an'),
        l_body=num('gian_dong'), l_ans=num('gian_dong_dap_an'), l_par=num('gian_cau'),
    )


# Tên từng phần. Số thứ tự "PHẦN n." được đánh lại liên tục theo các phần CÓ trong đề.
PART_NAMES = {
    1: 'Trắc nghiệm khách quan 4 lựa chọn.',
    2: 'Trắc nghiệm đúng – sai.',
    3: 'Trả lời ngắn.',
    'essay': 'Tự luận.',
}

PART_TITLES = {
    1: 'PHẦN 1. Trắc nghiệm khách quan 4 lựa chọn.',
    2: 'PHẦN 2. Trắc nghiệm đúng – sai.',
    3: 'PHẦN 3. Trả lời ngắn.',
    4: 'PHẦN 4. Tự luận.',
}


def _images_block(images):
    return '\n'.join(f'#exam-image("{p}")' for p in images)


def _key_line(part, value=''):
    """Dòng ghi chú (comment Typst, không in ra đề) lưu đáp án đúng của câu ngay trong file .typ.
    Nhờ vậy sau khi người dùng sửa/xóa/đổi chỗ câu hỏi, bảng đáp án vẫn dựng lại đúng."""
    return f'// @KEY {part} {value}'.rstrip().replace('\n', ' ')


def render_q_part1(q):
    _ok = next((o['label'] for o in q['options'] if o.get('correct')), '')
    lines = [_key_line(1, _ok), f'*Câu {q["num"]}.* {q["stem"]}']
    opt_items = []
    for o in q['options']:
        opt_items.append(f'[*{o["label"]}.* {o["content"]}]')
    if opt_items:  # cau khong co dap an trong file goc -> bo qua, tranh #choices() rong gay loi
        lines.append('#choices(' + ', '.join(opt_items) + ')')
    return '\n\n'.join(l for l in lines if l.strip())


def render_q_part2(q):
    _fl = ''.join('1' if o.get('correct') else '0' for o in q['options'])
    lines = [_key_line(2, _fl), f'*Câu {q["num"]}.* {q["stem"]}']
    opt_items = []
    for o in q['options']:
        opt_items.append(f'[*{o["label"]})* {o["content"]}]')
    if opt_items:
        lines.append('#tf-choices(' + ', '.join(opt_items) + ')')
    return '\n\n'.join(l for l in lines if l.strip())


def render_q_part3(q):
    lines = [_key_line(3, q.get('answer') or ''), f'*Câu {q["num"]}.* {q["stem"]}']
    return '\n\n'.join(l for l in lines if l.strip())


def render_q_essay(q):
    """Free-response/essay question: no A/B/C/D or a/b/c/d to build --
    stem is shown exactly as extracted, with blank space left for the
    student to write their solution."""
    lines = [_key_line(4), f'*{q.get("word", "Câu")} {q["num"]}.* {q["stem"]}']
    lines.append('#v(3cm)')
    return '\n\n'.join(l for l in lines if l.strip())


def _escape_markup(s):
    if not s:
        return s
    out = []
    for ch in s:
        if ch in '#*_@$`<>[]\\':
            out.append('\\' + ch)
        else:
            out.append(ch)
    return ''.join(out)


END_MARK = '// === END ==='


def _typst_str(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def render_end(text):
    """Dòng kết thúc đề (vd __________HẾT__________), in đậm + nghiêng, căn giữa."""
    if not str(text or '').strip():
        return ''
    return (f'{END_MARK}\n#v(1em)\n'
            f'#align(center, text(weight: "bold", style: "italic", {_typst_str(text)}))')


def render_typst(variant, made, header, style=None):
    header = {**DEFAULT_HEADER, **(header or {})}
    het = header.get('het', '')
    header = {k: _escape_markup(v) for k, v in header.items()}
    parts = [PREAMBLE.format(made=made, **header, **_style_args(style))]
    present = [k for k, key in ((1, 'part1'), (2, 'part2'), (3, 'part3'), ('essay', 'essay'))
               if variant.get(key)]
    # Đánh số lại liên tục: đề chỉ có Phần 1 + Tự luận thì Tự luận là "PHẦN 2.", không phải "PHẦN 4."
    so = {k: i for i, k in enumerate(present, 1)}

    def title(k):
        return f'PHẦN {so[k]}. {PART_NAMES[k]}'

    if variant['part1']:
        parts.append(f'== {title(1)}\n')
        parts += [render_q_part1(q) for q in variant['part1']]
    if variant['part2']:
        parts.append(f'\n== {title(2)}\n')
        parts += [render_q_part2(q) for q in variant['part2']]
    if variant['part3']:
        parts.append(f'\n== {title(3)}\n')
        parts += [render_q_part3(q) for q in variant['part3']]
    if variant.get('essay'):
        parts.append(f'\n== {title("essay")}\n')
        parts += [render_q_essay(q) for q in variant['essay']]
    end = render_end(het)
    if end:
        parts.append(end)
    return '\n\n'.join(parts)


ANSWER_KEY_PREAMBLE = r'''
// Cung tròn (không mũi tên): dấu cung ⌒ phía trên nội dung -- dùng cho đáp án
// kiểu "sđ cung AM". (Dấu nón \widehat ở phần đề vẫn là hat(...).)
#let overarc(body) = math.accent(body, sym.paren.t)

// Dấu cung (ký hiệu cung AM, "sđ AM"): đặt mũi tên cong ↷ phía trên nội dung.
// Chỉnh dy (độ cao mũi tên) hoặc size (cỡ mũi tên) nếu muốn lệch/to/nhỏ hơn.
#let cung(body) = {{
  box(baseline: 0%, {{
    body
    place(
      top + center,
      dy: -0.55em,
      text(size: 0.9em)[↷]
    )
  }})
}}

#set page(paper: "a4", margin: (x: 1.8cm, y: 2cm))
#set text(font: {f_key}, size: {s_key}pt, lang: "vi")
#align(center)[
  #text(11.5pt, weight: "bold")[{school}]
  #v(2pt)
  #text(14pt, weight: "bold")[BẢNG ĐÁP ÁN — {title}]
]
#v(8pt)
'''


_KEY_RE = re.compile(r'^// @KEY (\d)(?: (.*))?$', re.MULTILINE)


def akey_from_typ(source):
    """Đọc lại đáp án từ các dòng `// @KEY ...` của 1 file .typ (đã có thể được người dùng chỉnh sửa)."""
    akey = {'part1': {}, 'part2': {}, 'part3': {}}
    cnt = {1: 0, 2: 0, 3: 0}
    body = source.split('// === BODY ===', 1)[-1]
    for m in _KEY_RE.finditer(body):
        p, val = int(m.group(1)), (m.group(2) or '').strip()
        if p in cnt:
            cnt[p] += 1
            n = cnt[p]
            if p == 1:
                akey['part1'][n] = val or None
            elif p == 2:
                akey['part2'][n] = {c: (val[i:i + 1] == '1') for i, c in enumerate('abcd')}
            else:
                akey['part3'][n] = val or None
    return akey


def render_answer_key(all_variants, header, style=None):
    """all_variants: list of (made, akey) tuples. Renders one compact table per mã đề."""
    header = {**DEFAULT_HEADER, **(header or {})}
    school = _escape_markup(header['school'])
    title = _escape_markup(header['title'])
    parts = [ANSWER_KEY_PREAMBLE.format(school=school, title=title, **_style_args(style))]
    for made, akey in all_variants:
        parts.append(f'== Mã đề {made}')
        _no = {k: i for i, k in enumerate([k for k in (1, 2, 3) if akey[f'part{k}']], 1)}
        if akey['part1']:
            row1 = '   '.join(f'*{n}.* {l if l else "?"}' for n, l in sorted(akey['part1'].items()))
            parts.append(f'*Phần {_no[1]}:* {row1}')
        if akey['part2']:
            lines = []
            for n, flags in sorted(akey['part2'].items()):
                s = ', '.join(f'{k}) {"Đ" if v else "S"}' for k, v in flags.items())
                lines.append(f'*Câu {n}:* {s}')
            parts.append(f'*Phần {_no[2]}:* ' + '   '.join(lines))
        if akey['part3']:
            row3 = '   '.join(f'*{n}.* {a if a else "?"}' for n, a in sorted(akey['part3'].items()))
            parts.append(f'*Phần {_no[3]}:* {row3}')
    return '\n\n'.join(parts)


_UNKNOWN_VAR_RE = re.compile(r'unknown variable:\s*([^\s]+)')
_OPS = ('arcsin', 'arccos', 'arctan', 'sinh', 'cosh', 'tanh', 'coth',
        'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'log', 'ln', 'lim', 'exp')


def _split_chars(s):
    return ' '.join(re.findall(r'[A-Za-z]|\d+|.', s))


def _respace_word(word):
    """'cos2a' -> 'cos 2 a' ; 'xyz' -> 'x y z' (tách thành biến đơn lẻ)."""
    for op in _OPS:
        if word.startswith(op) and len(word) > len(op):
            return op + ' ' + _split_chars(word[len(op):])
    return _split_chars(word)


def _heal_source(typ_source, bad):
    """Chỉ sửa trong các đoạn công thức $...$, bỏ qua chuỗi trong dấu nháy."""
    segs = re.split(r'(?<!\\)\$', typ_source)
    pat = re.compile(r'(?<![A-Za-z_.])' + re.escape(bad) + r'(?![A-Za-z0-9_(])')
    changed = False
    for i in range(1, len(segs), 2):
        parts = re.split(r'("(?:[^"\\]|\\.)*")', segs[i])
        for j in range(0, len(parts), 2):
            new = pat.sub(lambda m: _respace_word(m.group(0)), parts[j])
            if new != parts[j]:
                parts[j] = new
                changed = True
        segs[i] = ''.join(parts)
    return '$'.join(segs), changed


def compile_typst(typ_source, out_pdf_path, workdir, max_fix=200):
    os.makedirs(workdir, exist_ok=True)
    typ_path = os.path.join(workdir, os.path.basename(out_pdf_path).replace('.pdf', '.typ'))
    fixed = []
    for _ in range(max_fix):
        with open(typ_path, 'w', encoding='utf-8') as f:
            f.write(typ_source)
        try:
            typst.compile(typ_path, output=out_pdf_path)
            if fixed:
                print(f'    [tự sửa] đã xử lý {len(fixed)} từ bị dính liền: {", ".join(fixed)}')
            return out_pdf_path
        except typst.TypstError as e:
            m = _UNKNOWN_VAR_RE.search(str(e))
            if not m:
                raise
            bad = m.group(1)
            typ_source, changed = _heal_source(typ_source, bad)
            if not changed or bad in fixed:
                raise
            fixed.append(bad)
    raise RuntimeError('Quá nhiều lỗi unknown variable, dừng tự sửa.')
