# Trộn đề trắc nghiệm

Công cụ giúp giáo viên **trộn đề trắc nghiệm** từ file Word (`.docx`) thành nhiều mã đề PDF khác nhau, kèm bảng đáp án tổng hợp.

Hỗ trợ đầy đủ:
- Phần 1: Trắc nghiệm 4 lựa chọn (A/B/C/D)
- Phần 2: Đúng/Sai (a/b/c/d)
- Phần 3: Trả lời ngắn
- Phần 4: Tự luận
- Công thức toán (Word Equation + MathType cũ)
- Hình ảnh trong đề
- Giao diện đồ họa dễ dùng

---

## Yêu cầu hệ thống

| Thành phần | Ghi chú |
|------------|---------|
| **Python** | 3.10 trở lên |
| **pandoc** | Bắt buộc (dùng để đọc file Word) |
| **Thư viện Python** | Xem `requirements.txt` |

### Cài đặt pandoc

- **Windows**: Tải bản cài tại [pandoc.org/installing.html](https://pandoc.org/installing.html) hoặc dùng `winget install pandoc`
- **macOS**: `brew install pandoc`
- **Ubuntu/Debian**: `sudo apt install pandoc`

---

## Cài đặt nhanh

```bash
# 1. Clone về máy
git clone https://github.com/<ten-cua-ban>/tron-de-trac-nghiem.git
cd tron-de-trac-nghiem

# 2. Tạo môi trường ảo (khuyến nghị)
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Cài thư viện
pip install -r requirements.txt
```

---

## Cách sử dụng

### 1. Giao diện đồ họa (khuyến nghị)

```bash
python giao_dien.py
```

Hoặc bấm đúp file `chay_giao_dien.bat` (Windows).

Trình duyệt sẽ tự mở tại `http://127.0.0.1:8765`.

**Quy trình trên giao diện:**
1. Chọn file Word đề gốc
2. Chọn số mã đề, seed, số câu mỗi phần…
3. Bấm **Trộn đề**
4. Xem thử / chỉnh sửa từng câu nếu cần
5. Xuất PDF tất cả mã đề + bảng đáp án

### 2. Dòng lệnh nhanh

Sửa file `chay.py` (chỉ cần đổi tên file Word và tiêu đề), rồi chạy:

```bash
python chay.py
```

Hoặc dùng trực tiếp:

```bash
python build_exam.py DE_NGUON.docx --so-made 4 --out-dir ket_qua
```

#### Các tham số hữu ích

| Tham số | Ý nghĩa | Mặc định |
|---------|---------|----------|
| `--so-made` | Số mã đề cần tạo | 4 |
| `--ma-de-bat-dau` | Mã đề bắt đầu | 1 |
| `--so-chu-so-made` | Số chữ số mã đề (3 → 001, 4 → 0001) | 4 |
| `--seed` | Seed ngẫu nhiên (giữ nguyên để tái lập) | 42 |
| `--khong-tron-cau` | Chỉ trộn đáp án, giữ nguyên thứ tự câu | — |
| `--khong-tron-dap-an` | Chỉ trộn câu, giữ nguyên thứ tự đáp án | — |
| `--so-cau-phan1` | Số câu Phần 1 (vd: `12` hoặc `10-15`) | lấy hết |
| `--so-cau-phan2` | Số câu Phần 2 | lấy hết |
| `--so-cau-phan3` | Số câu Phần 3 | lấy hết |
| `--so-cau-phan4` | Số câu Tự luận | lấy hết |

Ví dụ nâng cao:

```bash
python build_exam.py de_goc.docx \
  --so-made 6 \
  --so-cau-phan1 12 \
  --so-cau-phan2 4 \
  --so-cau-phan3 3-5 \
  --out-dir ket_qua
```

---

## Định dạng file Word nguồn

Để chương trình nhận đúng, file `.docx` cần tuân thủ quy ước sau:

### Cấu trúc chung
- Mỗi câu bắt đầu bằng **`Câu N.`** (in đậm).
- Có thể dùng **danh sách đánh số tự động** của Word.
- Chia phần bằng dòng in đậm: `PHẦN 1`, `PHẦN 2`, `PHẦN 3`, `PHẦN 4` / `Tự luận`.

### Phần 1 – Trắc nghiệm 4 lựa chọn
```
Câu 1. Nội dung câu hỏi...
*A. Đáp án đúng
B. Đáp án sai
C. Đáp án sai
D. Đáp án sai
```
→ Đáp án đúng đánh dấu bằng dấu `*` trước chữ cái (`*A.`, `*B.`…).

### Phần 2 – Đúng / Sai
```
Câu 1. Nội dung câu hỏi...
*a) Ý đúng
b) Ý sai
*c) Ý đúng
d) Ý sai
```

### Phần 3 – Trả lời ngắn
```
Câu 1. Nội dung câu hỏi...
Đáp án: 12
```
→ Dòng `Đáp án: ...` **không in** vào đề thi, chỉ dùng để lập bảng đáp án.

### Phần 4 – Tự luận
Chỉ cần ghi nội dung bài. Có thể có “Lời giải” phía sau (chương trình sẽ bỏ qua khi in đề).

### Công thức & hình ảnh
- Công thức: dùng **Word Equation** hoặc **MathType** đều được.
- Hình ảnh: nên dùng PNG/JPG. File `.wmf`/`.emf` cũ có thể không đọc được.

Xem file mẫu trong thư mục `examples/`.

---

## Kết quả đầu ra

Sau khi chạy, thư mục kết quả chứa:
```
ket_qua/
├── de_0001.pdf
├── de_0002.pdf
├── ...
├── dap_an.pdf          ← bảng đáp án tổng hợp
└── _work/              ← file .typ trung gian (có thể chỉnh tay)
```

---

## Tùy chỉnh tiêu đề & font

Trong `chay.py` (hoặc trên giao diện):

```python
TIEU_DE = {
    'so':     "SỞ GIÁO DỤC VÀ ĐÀO TẠO ...",
    'school': "TRƯỜNG ...",
    'title':  "ĐỀ KIỂM TRA ...",
    'namhoc': "NĂM HỌC 2025 - 2026",
    'mon':    "Môn: TOÁN 11",
    'time':   "Thời gian: 90 phút, không kể thời gian phát đề",
    'het':    "__________HẾT__________",
}

DINH_DANG = {
    'font_noi_dung':  "Times New Roman", 'co_noi_dung': 11,
    'font_dau_trang': "Times New Roman", 'co_dau_trang': 12,
    # ...
}
```

---

## Xử lý sự cố thường gặp

| Lỗi | Cách xử lý |
|-----|------------|
| Không tìm thấy câu hỏi | Kiểm tra dòng `Câu N.` có **in đậm** không |
| Công thức bị lỗi / chữ đỏ | Mở lại file Word, chuyển công thức sang Equation hoặc MathType mới |
| Ảnh không hiện | Chuyển ảnh sang PNG/JPG |
| `pandoc` not found | Cài pandoc và đảm bảo đã có trong PATH |
| Lỗi font | Cài font Times New Roman / Tahoma, hoặc đổi font trong `DINH_DANG` |

---

## Giấy phép

MIT License – tự do sử dụng, chỉnh sửa và phân phối.

---

## Đóng góp

Mọi đóng góp đều welcome! Hãy mở Issue hoặc Pull Request.
