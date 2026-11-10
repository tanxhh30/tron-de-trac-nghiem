#!/usr/bin/env python3
"""
Giao diện trộn đề (chạy trên trình duyệt, nhưng mọi xử lý vẫn nằm trên máy bạn).

    python giao_dien.py            (hoặc bấm đúp chay_giao_dien.bat)

Trình duyệt sẽ tự mở trang http://127.0.0.1:8765 . Đóng cửa sổ dòng lệnh (hoặc bấm
nút "Thoát" trên trang) để tắt chương trình. Không cần cài thêm thư viện nào ngoài
những thứ app trộn đề đã dùng (typst, olefile, pandoc).
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Tự dùng .venv của dự án nếu môi trường Python hiện tại thiếu thư viện (giống build_exam.py)
try:
    import typst  # noqa: E402
    import olefile  # noqa: E402,F401
except ImportError:
    _venv_py = os.path.join(HERE, '.venv', 'Scripts', 'python.exe')
    if os.path.exists(_venv_py) and sys.executable.lower() != _venv_py.lower():
        sys.exit(subprocess.call([_venv_py] + sys.argv))
    raise
import build_exam as B  # noqa: E402
import extract_docx as E  # noqa: E402
import render as R  # noqa: E402

PORT = 8765
HEADER_MARK = '// === HEADER ==='
BODY_MARK = '// === BODY ==='
STATE = {'out_dir': None, 'work_dir': None}
COMPILE_LOCK = threading.Lock()  # typst biên dịch từng việc một cho chắc chắn
PART_BY_NAME = {v: k for k, v in R.PART_NAMES.items()}


# ============================================================ tiện ích chung
def _made_ok(made):
    return bool(re.fullmatch(r'[0-9A-Za-z_\-]{1,20}', str(made)))


def typ_path(made):
    if not _made_ok(made) or not STATE['work_dir']:
        raise ValueError('Chưa có đề nào được mở.')
    return os.path.join(STATE['work_dir'], f'de_{made}.typ')


def pdf_path(made):
    return os.path.join(STATE['out_dir'], f'de_{made}.pdf')


def read_text(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def write_text(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)


_HINTS = [
    (r'unknown variable', 'Trong công thức có một từ không hợp lệ. Hãy thêm dấu cách giữa các chữ cái '
                          '(vd: "cos2a" -> "cos 2a") hoặc đặt chữ thường trong dấu nháy "…".'),
    (r'missing argument', 'Còn chỗ trống chưa điền. Ví dụ phân số cần đủ tử và mẫu: frac(tử, mẫu); căn cần có số bên trong: sqrt(…).'),
    (r'expected expression', 'Có dấu ^ hoặc _ (hoặc dấu phép tính) chưa có nội dung đi kèm phía sau.'),
    (r'unclosed delimiter|unexpected end of|expected closing', 'Thiếu dấu đóng: kiểm tra các dấu $ ... $, ngoặc ( ), [ ].'),
    (r'unexpected argument|expected at least one value', 'Một hàm (như frac, sqrt) có sai số lượng giá trị. '
                                                        'Phân số cần đủ 2 phần: frac(tử, mẫu).'),
    (r'file not found|failed to load file|image', 'Không tìm thấy file ảnh. Đừng xóa hoặc sửa dòng #exam-image(...).'),
]


def friendly_error(e):
    msg = str(e).strip()
    hint = ''
    for pat, h in _HINTS:
        if re.search(pat, msg, re.I):
            hint = h
            break
    return {'ok': False, 'loi': msg[:600], 'goi_y': hint}


# ============================================================ phân tích / trộn
def parse_spec(v):
    """null -> None (lấy hết) ; số -> int ; [a, b] -> (a, b)"""
    if v in (None, '', []):
        return None
    if isinstance(v, (list, tuple)):
        return (int(v[0]), int(v[1]))
    return int(v)


def api_phan_tich(d):
    docx = d.get('docx', '')
    if not os.path.isfile(docx):
        return {'ok': False, 'loi': 'Không tìm thấy file Word này.'}
    tmp = tempfile.mkdtemp(prefix='tronde_')
    try:
        questions, img_warn = E.parse_docx(docx, os.path.join(tmp, '_media'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    dem = {'p1': 0, 'p2': 0, 'p3': 0, 'tl': 0}
    canh_bao = []
    for q in questions:
        k = {1: 'p1', 2: 'p2', 3: 'p3', 'essay': 'tl'}.get(q['part'])
        if k:
            dem[k] += 1
        if q['part'] == 1 and len(q['options']) != 4:
            canh_bao.append(f"Câu {q['num']} (Phần 1) có {len(q['options'])}/4 đáp án trong file gốc.")
        elif q['part'] == 2 and len(q['options']) != 4:
            canh_bao.append(f"Câu {q['num']} (Phần 2) có {len(q['options'])}/4 ý a, b, c, d trong file gốc.")
        elif q['part'] in (1, 2) and q['options'] and not any(o['correct'] for o in q['options']):
            canh_bao.append(f"Câu {q['num']} chưa đánh dấu đáp án đúng bằng dấu * trong file gốc.")
    if img_warn:
        canh_bao.append(f'{len(img_warn)} ảnh cũ (.wmf/.emf) không đọc được, sẽ hiện chữ đỏ trong đề: '
                        + ', '.join(img_warn[:8]) + ('…' if len(img_warn) > 8 else ''))
    return {'ok': True, 'dem': dem, 'tong': len(questions), 'canh_bao': canh_bao}


def _tron_result(logs=None):
    """Mô tả các mã đề đang có trong thư mục làm việc."""
    work = STATE['work_dir']
    made = []
    state = {}
    sp = os.path.join(work, 'state.json')
    if os.path.isfile(sp):
        state = json.loads(read_text(sp))
    names = state.get('made') or sorted(
        re.match(r'de_(.+)\.typ$', f).group(1) for f in os.listdir(work) if re.match(r'de_.+\.typ$', f))
    for m in names:
        if os.path.isfile(typ_path(m)):
            made.append({'made': m, 'co_pdf': os.path.isfile(pdf_path(m))})
    return {'ok': True, 'out_dir': STATE['out_dir'], 'made': made, 'logs': logs or [],
            'tieu_de': state.get('header') or R.DEFAULT_HEADER,
            'dinh_dang': {**R.DEFAULT_STYLE, **(state.get('dinh_dang') or {})}}


def api_tron(d):
    docx = d.get('docx', '')
    if not os.path.isfile(docx):
        return {'ok': False, 'loi': 'Chưa chọn file Word nguồn (hoặc không tìm thấy file).'}
    out_dir = os.path.abspath(d.get('out_dir') or os.path.join(os.path.dirname(docx), 'ket_qua'))
    c = d.get('counts', {})
    logs = []
    with COMPILE_LOCK:
        res = B.tron_de(
            docx, so_made=int(d.get('so_made', 4)), ma_de_bat_dau=int(d.get('ma_de_bat_dau', 1)),
            out_dir=out_dir, seed=int(d.get('seed', 42)),
            tron_cau=bool(d.get('tron_cau', True)), tron_dap_an=bool(d.get('tron_dap_an', True)),
            so_cau_phan1=parse_spec(c.get('1')), so_cau_phan2=parse_spec(c.get('2')),
            so_cau_phan3=parse_spec(c.get('3')), so_cau_phan4=parse_spec(c.get('4')),
            tieu_de=d.get('tieu_de') or None, so_chu_so_made=int(d.get('so_chu_so_made', 4)),
            dinh_dang=d.get('dinh_dang') or None, chi_tao_typ=True, log=logs.append)
    if not res or not res.get('ok'):
        return {'ok': False, 'loi': 'Không tìm thấy câu hỏi nào trong file. Kiểm tra "Câu N." có in đậm không.',
                'logs': logs}
    STATE['out_dir'] = res['out_dir']
    STATE['work_dir'] = res['work_dir']
    return _tron_result(logs)


def api_mo_lai(d):
    out_dir = os.path.abspath(d.get('out_dir', ''))
    work = os.path.join(out_dir, '_work')
    if not os.path.isdir(work) or not any(re.match(r'de_.+\.typ$', f) for f in os.listdir(work)):
        return {'ok': False, 'loi': 'Thư mục này chưa có đề đã trộn (không thấy các file .typ trong _work).'}
    STATE['out_dir'], STATE['work_dir'] = out_dir, work
    return _tron_result()


# ============================================================ đọc / ghi file .typ theo "khối"
def split_typ(src):
    i = src.find(BODY_MARK)
    if i < 0:
        raise ValueError('File .typ này không có dấu mốc "// === BODY ===" (không phải file do app tạo).')
    i += len(BODY_MARK)
    return src[:i], src[i:]


def _scan_brackets(s):
    """Tách chuỗi "[a], [b], [c]" thành ['a','b','c']. Dấu [ ] nằm trong công thức $…$ không tính."""
    out, i, n = [], 0, len(s)
    while i < n:
        while i < n and s[i] in ' \t\r\n,':
            i += 1
        if i >= n:
            break
        if s[i] != '[':
            return None
        i += 1
        start, depth, math = i, 1, False
        while i < n:
            c = s[i]
            if c == '\\':
                i += 2
                continue
            if c == '$':
                math = not math
            elif math and c == '"':
                i += 1
                while i < n and s[i] != '"':
                    i += 2 if s[i] == '\\' else 1
            elif not math:
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        if depth != 0:
            return None
        out.append(s[start:i])
        i += 1
    return out


_LABEL_RE = re.compile(r'^\*(Câu|Bài) (\d+)\.\* ?')
_P3_TAIL = '\n\n#v(0.7em) Đáp án: #box(width: 4cm, repeat[.])\n\n#v(0.6em)'
_ESSAY_TAIL = '\n\n#v(3cm)'
_KEY_SPLIT = re.compile(r'(?m)^// @KEY (\d)(?: (.*))?$')


def parse_item(part, keyval, text):
    text = text.strip('\n').rstrip()
    raw = {'kind': 'raw', 'part': part, 'key': keyval, 'raw': text}
    m = _LABEL_RE.match(text)
    if not m:
        return raw
    word, rest = m.group(1), text[m.end():]
    if part == 1 or part == 2:
        tag = '#choices(' if part == 1 else '#tf-choices('
        idx = rest.rfind('\n\n' + tag)
        if idx < 0 or not rest.endswith(')'):
            return raw
        opts = _scan_brackets(rest[idx + 2 + len(tag):-1])
        if opts is None:
            return raw
        lab = r'^\*([A-D])\.\* ?' if part == 1 else r'^\*([a-d])\)\* ?'
        contents = []
        for o in opts:
            mo = re.match(lab, o)
            if not mo:
                return raw
            contents.append(o[mo.end():])
        return {'kind': 'p1' if part == 1 else 'p2', 'word': word, 'stem': rest[:idx],
                'options': contents, 'key': keyval}
    if part == 3:
        # File cũ có thêm 2 dòng "Đáp án: ....": bỏ đi (đề mới không còn các dòng này)
        stem = rest[:-len(_P3_TAIL)] if rest.endswith(_P3_TAIL) else rest
        return {'kind': 'p3', 'word': word, 'stem': stem, 'key': keyval}
    if part == 4:
        if not rest.endswith(_ESSAY_TAIL):
            return raw
        return {'kind': 'essay', 'word': word, 'stem': rest[:-len(_ESSAY_TAIL)], 'key': keyval}
    return raw


def split_end(body):
    """Tách phần kết thúc đề (dòng HẾT) ra khỏi thân đề để không lẫn vào câu cuối."""
    if R.END_MARK in body:
        main, tail = body.split(R.END_MARK, 1)
        return main.rstrip('\n'), R.END_MARK + tail
    return body, ''


def parse_typ(src):
    head, body = split_typ(src)
    body, _ = split_end(body)
    sections = []
    chunks = re.split(r'(?m)^== (.*)$', body)
    for k in range(1, len(chunks), 2):
        title, text = chunks[k].strip(), chunks[k + 1]
        part = PART_BY_NAME.get(re.sub(r'^PHẦN \d+\.\s*', '', title))
        items = []
        ms = list(_KEY_SPLIT.finditer(text))
        if ms and text[:ms[0].start()].strip():
            items.append({'kind': 'raw', 'part': 0, 'key': '', 'raw': text[:ms[0].start()].strip()})
        for j, mk in enumerate(ms):
            end = ms[j + 1].start() if j + 1 < len(ms) else len(text)
            items.append(parse_item(int(mk.group(1)), (mk.group(2) or '').strip(), text[mk.end():end]))
        sections.append({'part': part if part is not None else 'khac', 'title': title, 'items': items})
    return sections


def item_to_typ(it, so):
    """Một câu -> đoạn mã Typst (đúng định dạng render.py tạo ra)."""
    k = it['kind']
    if k == 'raw':
        return R._key_line(it.get('part', 0), it.get('key', '')) + '\n\n' + it['raw'] if it.get('part') else it['raw']
    word = it.get('word', 'Câu')
    head = f'*{word} {so}.* {it["stem"]}'
    if k == 'p1':
        opts = ', '.join(f'[*{"ABCD"[i] if i < 4 else "?"}.* {c}]' for i, c in enumerate(it['options']))
        return '\n\n'.join([R._key_line(1, it.get('key', '')), head, f'#choices({opts})'])
    if k == 'p2':
        opts = ', '.join(f'[*{"abcd"[i] if i < 4 else "?"})* {c}]' for i, c in enumerate(it['options']))
        return '\n\n'.join([R._key_line(2, it.get('key', '')), head, f'#tf-choices({opts})'])
    if k == 'p3':
        return R._key_line(3, it.get('key', '')) + '\n\n' + head
    return R._key_line(4) + '\n\n' + head + _ESSAY_TAIL


def sections_to_body(sections):
    present = [s for s in sections if s['items']]
    parts = []
    for n, s in enumerate(present, 1):
        name = R.PART_NAMES.get(s['part'])
        title = f'PHẦN {n}. {name}' if name else s['title']
        parts.append(('' if n == 1 else '\n') + f'== {title}\n')
        for i, it in enumerate(s['items'], 1):
            parts.append(item_to_typ(it, i))
    return '\n\n'.join(parts)


def assemble(head, sections, tail=''):
    return head + '\n\n\n' + sections_to_body(sections) + ('\n\n' + tail if tail else '')


# ============================================================ API chỉnh sửa
def api_doc(d):
    src = read_text(typ_path(d['made']))
    return {'ok': True, 'sections': parse_typ(src)}


def api_luu(d):
    p = typ_path(d['made'])
    head, body = split_typ(read_text(p))
    write_text(p, assemble(head, d['sections'], split_end(body)[1]))
    return {'ok': True}


def api_nguon(d):
    return {'ok': True, 'nguon': read_text(typ_path(d['made']))}


def api_luu_nguon(d):
    src = d['nguon']
    split_typ(src)
    write_text(typ_path(d['made']), src)
    return {'ok': True}


def api_xem_cau(d):
    src = read_text(typ_path(d['made']))
    head, _ = split_typ(src)
    defs = head.split(HEADER_MARK)[0]
    snippet = item_to_typ(d['item'], int(d.get('so', 1)))
    snippet = re.sub(r'(?m)^// @KEY.*$', '', snippet)
    doc = defs + ('\n#set page(width: 17.8cm, height: auto, margin: (x: 0.2cm, y: 0.25cm), footer: none)\n'
                  + snippet + '\n')
    work = STATE['work_dir']
    tmp = os.path.join(work, f'_pv_{uuid.uuid4().hex[:10]}.typ')
    try:
        with COMPILE_LOCK:
            # Giống bước biên dịch thật: tự tách các từ bị dính liền (cos2a -> cos 2 a) rồi thử lại,
            # để hình xem thử luôn khớp với PDF cuối cùng.
            fixed = []
            for _ in range(30):
                write_text(tmp, doc)
                try:
                    png = typst.compile(tmp, format='png', ppi=170.0)
                    break
                except typst.TypstError as e:
                    m = R._UNKNOWN_VAR_RE.search(str(e))
                    if not m or m.group(1) in fixed:
                        raise
                    doc, changed = R._heal_source(doc, m.group(1))
                    if not changed:
                        raise
                    fixed.append(m.group(1))
        if isinstance(png, (list, tuple)):
            png = png[0]
        return {'ok': True, 'png': base64.b64encode(png).decode('ascii')}
    except Exception as e:  # noqa: BLE001
        return friendly_error(e)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def api_bien_dich(d):
    made = d['made']
    src = read_text(typ_path(made))
    try:
        with COMPILE_LOCK:
            R.compile_typst(src, pdf_path(made), STATE['work_dir'])
    except Exception as e:  # noqa: BLE001
        return friendly_error(e)
    return {'ok': True, 'pdf': pdf_path(made)}


def _all_made():
    return [m['made'] for m in _tron_result()['made']]


def api_dap_an(d):
    out = {}
    for m in _all_made():
        out[m] = R.akey_from_typ(read_text(typ_path(m)))
    return {'ok': True, 'dap_an': out}


def api_bang_dap_an(d):
    work = STATE['work_dir']
    sp = os.path.join(work, 'state.json')
    st = json.loads(read_text(sp)) if os.path.isfile(sp) else {}
    variants = [(m, R.akey_from_typ(read_text(typ_path(m)))) for m in _all_made()]
    src = R.render_answer_key(variants, st.get('header') or R.DEFAULT_HEADER, st.get('dinh_dang') or None)
    out = os.path.join(STATE['out_dir'], 'dap_an.pdf')
    try:
        with COMPILE_LOCK:
            R.compile_typst(src, out, work)
    except Exception as e:  # noqa: BLE001
        return friendly_error(e)
    return {'ok': True, 'pdf': out}


def api_ap_dung_dau_trang(d):
    """Dựng lại phần đầu trang (tiêu đề + font/cỡ chữ) cho mọi mã đề, giữ nguyên các câu đã sửa."""
    header = {**R.DEFAULT_HEADER, **(d.get('tieu_de') or {})}
    style = d.get('dinh_dang') or None
    esc = {k: R._escape_markup(v) for k, v in header.items()}
    for m in _all_made():
        p = typ_path(m)
        _, body = split_typ(read_text(p))
        main, _tail = split_end(body)
        head = R.PREAMBLE.format(made=m, **esc, **R._style_args(style))
        tail = R.render_end(header.get('het', ''))
        write_text(p, head + main + ('\n\n' + tail if tail else ''))
    sp = os.path.join(STATE['work_dir'], 'state.json')
    st = json.loads(read_text(sp)) if os.path.isfile(sp) else {}
    st['header'], st['dinh_dang'] = header, style or {}
    write_text(sp, json.dumps(st, ensure_ascii=False, indent=1))
    return {'ok': True}


# ============================================================ hộp thoại chọn file / thư mục
_DIALOG_CODE = r'''
import sys, tkinter as tk
from tkinter import filedialog
kind, start = sys.argv[1], sys.argv[2]
r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)
if kind == 'file':
    p = filedialog.askopenfilename(title='Chọn file đề Word', initialdir=start or None,
                                   filetypes=[('Word', '*.docx'), ('Tất cả', '*.*')])
else:
    p = filedialog.askdirectory(title='Chọn thư mục lưu kết quả', initialdir=start or None)
sys.stdout.buffer.write((p or '').encode('utf-8'))
'''


def api_chon(d):
    kind = 'file' if d.get('loai') == 'file' else 'dir'
    start = d.get('batdau') or ''
    if start and not os.path.isdir(start):
        start = os.path.dirname(start)
    try:
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        r = subprocess.run([sys.executable, '-c', _DIALOG_CODE, kind, start], capture_output=True, env=env, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode('utf-8', 'replace')[-200:])
        return {'ok': True, 'path': r.stdout.decode('utf-8').strip()}
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'loi': f'Không mở được hộp thoại chọn ({e}). Hãy dán đường dẫn vào ô.'}


def api_mo_thu_muc(d):
    p = d.get('path') or STATE['out_dir']
    if not p or not os.path.exists(p):
        return {'ok': False, 'loi': 'Thư mục chưa tồn tại.'}
    try:
        if sys.platform.startswith('win'):
            os.startfile(p)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', p])
        else:
            subprocess.Popen(['xdg-open', p])
        return {'ok': True}
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'loi': str(e)}


def api_mac_dinh(d):
    return {'ok': True, 'tieu_de': R.DEFAULT_HEADER, 'dinh_dang': R.DEFAULT_STYLE, 'thu_muc': HERE}


def api_thoat(d):
    threading.Timer(0.4, lambda: os._exit(0)).start()
    return {'ok': True}


ROUTES = {
    '/api/mac-dinh': api_mac_dinh, '/api/chon': api_chon, '/api/phan-tich': api_phan_tich,
    '/api/tron': api_tron, '/api/mo-lai': api_mo_lai, '/api/doc': api_doc, '/api/luu': api_luu,
    '/api/nguon': api_nguon, '/api/luu-nguon': api_luu_nguon, '/api/xem-cau': api_xem_cau,
    '/api/bien-dich': api_bien_dich, '/api/dap-an': api_dap_an, '/api/bang-dap-an': api_bang_dap_an,
    '/api/ap-dung-dau-trang': api_ap_dung_dau_trang, '/api/mo-thu-muc': api_mo_thu_muc, '/api/thoat': api_thoat,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # im lặng
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            html = os.path.join(HERE, 'giao_dien.html')
            return self._send(200, open(html, 'rb').read(), 'text/html; charset=utf-8')
        if u.path == '/pdf':
            p = os.path.abspath(parse_qs(u.query).get('path', [''])[0])
            base = STATE['out_dir']
            if base and p.lower().endswith('.pdf') and os.path.isfile(p) \
                    and os.path.commonpath([os.path.abspath(base), p]) == os.path.abspath(base):
                return self._send(200, open(p, 'rb').read(), 'application/pdf')
        return self._send(404, b'Not found', 'text/plain')

    def do_POST(self):
        fn = ROUTES.get(urlparse(self.path).path)
        if not fn:
            return self._send(404, b'{}', 'application/json')
        try:
            n = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(n) or b'{}')
            res = fn(data)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            res = {'ok': False, 'loi': f'{type(e).__name__}: {e}'}
        self._send(200, json.dumps(res, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')


def main():
    port = PORT
    while True:
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            port += 1
    url = f'http://127.0.0.1:{port}'
    print(f'Giao diện trộn đề đang chạy tại {url}\n(Đóng cửa sổ này hoặc bấm "Thoát" trên trang để tắt.)')
    if '--khong-mo-trinh-duyet' not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
