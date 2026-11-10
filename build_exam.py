#!/usr/bin/env python3
"""
Trộn đề trắc nghiệm: đọc 1 file .docx (đề gốc, có đánh dấu đáp án đúng bằng
dấu "*" trước phương án, ví dụ "*A." hoặc "*a)"), sinh ra nhiều mã đề đã
xáo trộn câu hỏi + đáp án, xuất trực tiếp ra PDF (không qua Markdown), kèm
1 file PDF đáp án tổng hợp cho giáo viên.

Yêu cầu định dạng file .docx nguồn:
  - Mỗi câu bắt đầu bằng "Câu N." được in đậm (Word tự đánh số đậm là được).
  - Có thể chia 3 phần bằng dòng in đậm bắt đđầu "PHẦN 1/2/3..." :
      PHẦN 1: trắc nghiệm 4 đáp án A/B/C/D (đáp án đúng ghi "*A." "*B."...)
      PHẦN 2: đúng/sai 4 ý a/b/c/d (đáp án đúng ghi "*a)" "*b)"...)
      PHẦN 3: trả lời ngắn, có dòng "Đáp án: ..." (dòng này sẽ KHÔNG in
              vào đề thi, chỉ dùng để lấy đáp án cho giáo viên)
  - Công thức toán gõ bằng Word Equation (OMML) hoặc MathType (OLE) đều
    được, kể cả公 thức MathType cũ từ các bản Word rất cũ.

Cách dùng:
    python3 build_exam.py DE_NGUON.docx --so-made 4 --out-dir output_data

Yêu cầu cài đặt: pandoc, olefile (pip), typst (pip).
"""
import argparse
import json
import os
import shutil
import sys

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tự động dùng .venv nếu môi trường hiện tại thiếu thư viện
try:
    import typst
    import olefile
except ImportError:
    _venv_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Scripts', 'python.exe')
    if os.path.exists(_venv_py) and sys.executable.lower() != _venv_py.lower():
        import subprocess
        sys.exit(subprocess.call([_venv_py] + sys.argv))

import extract_docx as E
import shuffle as S
import render as R


def tron_de(docx_path, so_made=4, ma_de_bat_dau=1, out_dir='output_data',
            seed=42, tron_cau=True, tron_dap_an=True,
            so_cau_phan1=None, so_cau_phan2=None, so_cau_phan3=None, so_cau_phan4=None,
            tieu_de=None, so_chu_so_made=4, dinh_dang=None,
            chi_tao_typ=False, log=print):
    """Hàm chính, dùng lại được: đọc 1 file .docx, xuất N mã đề PDF + 1 bảng đáp án PDF.

    docx_path      -- đường dẫn file .docx đề gốc
    so_made        -- số mã đề cần sinh
    ma_de_bat_dau  -- số mã đề đầu tiên (001, 002, ... hoặc số khác)
    out_dir        -- thư mục xuất kết quả
    seed           -- seed ngẫu nhiên, giữ nguyên để tái lập đúng bộ đề cũ
    tron_cau       -- True: xáo thứ tự câu hỏi trong từng phần
    tron_dap_an    -- True: xáo thứ tự đáp án A/B/C/D (hoặc a/b/c/d)
    tieu_de        -- dict ghi đè nội dung đầu trang (xem render.DEFAULT_HEADER):
                      so, school, title, namhoc, mon, time. None = dùng mặc định.
    dinh_dang      -- dict font/cỡ chữ từng mục (xem render.DEFAULT_STYLE). None = mặc định.
    chi_tao_typ    -- True: chỉ trộn và ghi các file .typ (CHƯA biên dịch PDF) để người dùng
                      xem/sửa; trả về dict mô tả kết quả (dùng cho giao diện giao_dien.py).
    log            -- hàm ghi thông báo (mặc định print).
    so_chu_so_made -- số chữ số của mã đề (4 -> 0001, 0002...; 3 -> 001, 002...)
    so_cau_phan1/2/3/4 -- (4 = Tự luận) số câu lấy vào đề cho từng phần. Mỗi giá trị có thể là:
        None          : lấy hết toàn bộ ngân hàng câu hỏi của phần đó (mặc định)
        một số nguyên : luôn lấy đúng N câu (ngẫu nhiên trong ngân hàng) cho mọi mã đề
        (min, max)    : mỗi mã đề lấy một số câu NGẪU NHIÊN khác nhau trong khoảng
                        [min, max] -- tức là các mã đề có thể có số câu khác nhau
      Nếu số câu yêu cầu vượt quá số câu có trong ngân hàng, sẽ tự động lấy tối đa
      những gì có.

    Trả về: đường dẫn thư mục chứa kết quả.
    """
    counts = {1: so_cau_phan1, 2: so_cau_phan2, 3: so_cau_phan3, 4: so_cau_phan4}
    out_dir = os.path.abspath(out_dir)
    media_dir = os.path.join(out_dir, '_media')
    work_dir = os.path.join(out_dir, '_work')
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    log(f'[*] Đang đọc và phân tích: {docx_path}')
    questions, img_warnings = E.parse_docx(docx_path, media_dir)
    n1 = sum(1 for q in questions if q['part'] == 1)
    n2 = sum(1 for q in questions if q['part'] == 2)
    n3 = sum(1 for q in questions if q['part'] == 3)
    n4 = sum(1 for q in questions if q['part'] == 'essay')
    log(f'    -> Tìm thấy {len(questions)} câu (Phần 1: {n1}, Phần 2: {n2}, Phần 3: {n3}, Tự luận: {n4})')
    if img_warnings:
        log(f'[!] CẢNH BÁO: {len(img_warnings)} ảnh trong file gốc không đọc được '
              f'(định dạng .wmf/.emf cũ, không phải công thức MathType) nên đã thay bằng '
              f'dòng chữ đỏ trong đề: {", ".join(img_warnings)}')
        log('    -> Mở file .docx gốc, tìm ảnh đó và dán lại dạng PNG/JPG (hoặc gõ lại bằng Equation) rồi chạy lại.')
    if len(questions) == 0:
        log('[-] Không tìm thấy câu hỏi nào. Kiểm tra lại định dạng "Câu N." có được in đậm không.')
        return {'ok': False, 'out_dir': out_dir} if chi_tao_typ else out_dir

    # Canh bao cau thieu dap an / thieu dap an dung ngay tu dau (thay vi de
    # den luc bien dich Typst moi bao loi kho hieu).
    for q in questions:
        if q['part'] == 1 and len(q['options']) != 4:
            log(f"[!] CẢNH BÁO: Câu {q['num']} (Phần 1) có {len(q['options'])}/4 đáp án trong file gốc "
                  f"-> kiểm tra lại file .docx (câu này sẽ in không có đáp án).")
        elif q['part'] == 2 and len(q['options']) != 4:
            log(f"[!] CẢNH BÁO: Câu {q['num']} (Phần 2) có {len(q['options'])}/4 ý a,b,c,d trong file gốc.")
        elif q['part'] in (1, 2) and q['options'] and not any(o['correct'] for o in q['options']):
            log(f"[!] CẢNH BÁO: Câu {q['num']} chưa đánh dấu đáp án đúng bằng dấu * trong file gốc.")

    header = {**R.DEFAULT_HEADER, **(tieu_de or {})}

    # Image references baked into question text point at the absolute
    # `media_dir` used during extraction. Typst sandboxes file access to the
    # directory containing the .typ file, so rewrite those to a short
    # relative token and copy the media alongside where we compile.
    # (Image paths embedded in the text are always forward-slash, even on
    # Windows -- see extract_docx.runs_to_typst -- so compare against a
    # forward-slash form of media_dir too, or this match silently misses on
    # Windows and the untouched absolute Windows path leaks into the .typ
    # file, which Typst then rejects for containing a backslash.)
    rel_token = '_exam_media'
    media_dir_fwd = media_dir.replace('\\', '/')

    def _rewrite(s):
        return s.replace(media_dir_fwd, rel_token).replace(media_dir, rel_token) if s else s

    for q in questions:
        q['stem'] = _rewrite(q['stem'])
        for o in q.get('options', []):
            o['content'] = _rewrite(o['content'])

    work_media = os.path.join(work_dir, rel_token)
    src_media = os.path.join(media_dir, 'media')
    if os.path.isdir(src_media):
        os.makedirs(os.path.join(work_media, 'media'), exist_ok=True)
        for fn in os.listdir(src_media):
            shutil.copy(os.path.join(src_media, fn), os.path.join(work_media, 'media', fn))

    all_variants = []
    made_list = []
    for i in range(so_made):
        made = f'{ma_de_bat_dau + i:0{so_chu_so_made}d}'
        s = seed + i
        variant, akey = S.make_variant(
            questions, seed=s,
            shuffle_questions=tron_cau,
            shuffle_options=tron_dap_an,
            counts=counts,
        )
        typ_src = R.render_typst(variant, made, header, dinh_dang)
        pdf_path = os.path.join(out_dir, f'de_{made}.pdf')
        so_cau_thuc_te = f"P1:{len(variant['part1'])} P2:{len(variant['part2'])} P3:{len(variant['part3'])} TL:{len(variant['essay'])}"
        typ_path = os.path.join(work_dir, f'de_{made}.typ')
        if chi_tao_typ:
            with open(typ_path, 'w', encoding='utf-8') as f:
                f.write(typ_src)
            log(f'[*] Đã tạo file .typ mã đề {made} ({so_cau_thuc_te})')
        else:
            log(f'[*] Đang biên dịch mã đề {made} ({so_cau_thuc_te}) -> {pdf_path}')
            R.compile_typst(typ_src, pdf_path, work_dir)
        all_variants.append((made, akey))
        made_list.append({'made': made, 'typ': typ_path, 'pdf': pdf_path, 'thong_ke': so_cau_thuc_te})

    # Lưu thông số để giao diện có thể dựng lại bảng đáp án sau khi người dùng sửa các file .typ
    with open(os.path.join(work_dir, 'state.json'), 'w', encoding='utf-8') as f:
        json.dump({'header': header, 'dinh_dang': dinh_dang or {}, 'out_dir': out_dir,
                   'made': [m['made'] for m in made_list]}, f, ensure_ascii=False, indent=1)
    if chi_tao_typ:
        return {'ok': True, 'out_dir': out_dir, 'work_dir': work_dir, 'made': made_list,
                'dem': {'p1': n1, 'p2': n2, 'p3': n3, 'tl': n4}}

    log('[*] Đang xuất bảng đáp án tổng hợp')
    key_src = R.render_answer_key(all_variants, header, dinh_dang)
    key_pdf = os.path.join(out_dir, 'dap_an.pdf')
    R.compile_typst(key_src, key_pdf, work_dir)

    log(f'\n[+] Hoàn tất! {so_made} mã đề + 1 bảng đáp án đã lưu tại: {out_dir}')
    return out_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('docx', help='File Word đề gốc (.docx)')
    ap.add_argument('--so-made', type=int, default=4, help='Số mã đề cần sinh (mặc định 4)')
    ap.add_argument('--ma-de-bat-dau', type=int, default=1, help='Mã đề đầu tiên (mặc định 001)')
    ap.add_argument('--out-dir', default='output_data', help='Thư mục xuất kết quả')
    ap.add_argument('--seed', type=int, default=42, help='Seed ngẫu nhiên (để tái lập kết quả)')
    ap.add_argument('--khong-tron-cau', action='store_true', help='Giữ nguyên thứ tự câu hỏi, chỉ trộn đáp án')
    ap.add_argument('--khong-tron-dap-an', action='store_true', help='Giữ nguyên thứ tự đáp án, chỉ trộn câu hỏi')
    ap.add_argument('--so-cau-phan1', default=None,
                     help='Số câu Phần 1 mỗi mã đề: 1 số (vd 15) hoặc khoảng MIN-MAX (vd 12-16) '
                          'để mỗi mã đề random 1 số câu KHÁC NHAU trong khoảng đó. Mặc định: lấy hết.')
    ap.add_argument('--so-cau-phan2', default=None, help='Số câu Phần 2 mỗi mã đề (cú pháp như --so-cau-phan1)')
    ap.add_argument('--so-cau-phan3', default=None, help='Số câu Phần 3 mỗi mã đề (cú pháp như --so-cau-phan1)')
    ap.add_argument('--so-cau-phan4', default=None, help='Số câu Phần 4 (Tự luận) mỗi mã đề (cú pháp như --so-cau-phan1)')
    args = ap.parse_args()

    def _parse_count_spec(s):
        if s is None:
            return None
        s = s.strip()
        if '-' in s:
            lo, hi = s.split('-', 1)
            return (int(lo), int(hi))
        return int(s)

    tron_de(
        args.docx, so_made=args.so_made, ma_de_bat_dau=args.ma_de_bat_dau,
        out_dir=args.out_dir, seed=args.seed,
        tron_cau=not args.khong_tron_cau, tron_dap_an=not args.khong_tron_dap_an,
        so_cau_phan1=_parse_count_spec(args.so_cau_phan1),
        so_cau_phan2=_parse_count_spec(args.so_cau_phan2),
        so_cau_phan3=_parse_count_spec(args.so_cau_phan3),
        so_cau_phan4=_parse_count_spec(args.so_cau_phan4),
    )


if __name__ == '__main__':
    main()
