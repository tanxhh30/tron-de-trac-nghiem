# Trộn đề trắc nghiệm – image sẵn sàng chạy
FROM python:3.12-slim-bookworm

# Cài pandoc + font cơ bản (để PDF đẹp)
RUN apt-get update && apt-get install -y --no-install-recommends \
        pandoc \
        fonts-liberation \
        fonts-dejavu-core \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code
COPY . .

# Cổng giao diện web
EXPOSE 8765

# Mặc định chạy giao diện
CMD ["python", "giao_dien.py", "--khong-mo-trinh-duyet"]
