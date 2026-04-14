FROM python:3.9-slim

WORKDIR /app

# 替换 apt 源为阿里云镜像，解决由于代理引发的 Bad Gateway 和连接超时问题
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null

# Install system dependencies
# ffmpeg: required by OpenCV for RTSP reading
# libgl1, libglib2.0-0: required for opencv-python
# iputils-ping: useful for network troubleshooting tools if needed
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
# 使用国内 PyPI 镜像加速 Python 依赖下载
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# Copy the rest of the application
COPY . .

# Run the app
CMD ["python", "main.py"]
