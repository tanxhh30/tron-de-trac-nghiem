"""
Chạy nhanh: chỉ cần sửa các dòng bên dưới rồi chạy `python chay.py`.
File .docx nên để cùng thư mục với file này (hoặc ghi đường dẫn đầy đủ).
"""
import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from build_exam import tron_de

# ====================== CHỈ CẦN SỬA PHẦN NÀY ======================

FILE_DOCX = "examples/DeMau.docx"   # <-- Đường dẫn file Word đề gốc

# Nội dung phần đầu trang của đề
TIEU_DE = {
    'so':     "SỞ GIÁO DỤC VÀ ĐÀO TẠO ...",
    'school': "TRƯỜNG ...",
    'title':  "ĐỀ KIỂM TRA ...",
    'namhoc': "NĂM HỌC 2025 - 2026",
    'mon':    "Môn: TOÁN ...",
    'time':   "Thời gian: 90 phút, không kể thời gian phát đề",
    'het':    "__________HẾT__________",   # để "" nếu không dùng
}

# Font chữ và cỡ chữ (pt)
DINH_DANG = {
    'font_noi_dung':    "Times New Roman", 'co_noi_dung':    11,    # câu hỏi + đáp án
    'font_dau_trang':   "Times New Roman", 'co_dau_trang':   12,    # tiêu đề, Họ tên, SBD
    'font_tieu_muc':    "Times New Roman", 'co_tieu_muc':    13,    # "PHẦN 1. ..."
    'font_chan_trang':  "Tahoma",          'co_chan_trang':  9,     # "Mã đề / Trang x / y"
    'font_bang_dap_an': "Tahoma",          'co_bang_dap_an': 10.5,  # file dap_an.pdf
    'gian_dong': 0.62,          # khoảng cách dòng đề bài
    'gian_dong_dap_an': 0.95,   # khoảng cách dòng đáp án (tăng nếu phân số bị đè)
    'gian_cau': 1.2,            # khoảng cách giữa các câu
}

# ====================== CHẠY ======================

tron_de(
    FILE_DOCX,
    so_made=4,                  # số mã đề
    out_dir="ket_qua",
    tieu_de=TIEU_DE,
    dinh_dang=DINH_DANG,
    so_chu_so_made=4,           # 4 → 0001, 0002... ; 3 → 001, 002...
    # so_cau_phan1=12,          # bỏ comment nếu muốn giới hạn số câu
    # so_cau_phan2=4,
    # so_cau_phan3=(3, 5),      # mỗi mã đề random 3–5 câu Phần 3
    # so_cau_phan4=2,
)
