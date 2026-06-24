# Callio Dockerfile
# 使用 Python 3.11 slim 作为基础镜像（避免 ChatTTS/torch 版本兼容问题）
#
# 构建：docker build -t callio:latest .
# 本地运行：docker run --rm -p 8000:8000 callio:latest

FROM python:3.11-slim

# 系统依赖（ffmpeg 用于 EdgeTTS 音频转换；curl 用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖（先复制 requirements.txt 以利用 Docker 层缓存）
COPY requirements.txt .

# 安装核心依赖（跳过大型可选依赖 ChatTTS/torch 以减小镜像体积）
# 生产环境如需 ChatTTS，去掉下面两行的 --no-deps/exclude 限制
RUN pip install --no-cache-dir \
    pipecat-ai \
    fastapi \
    "uvicorn[standard]" \
    websockets \
    openai \
    requests \
    qrcode \
    pillow \
    python-dotenv \
    numpy \
    scipy \
    loguru \
    typing-extensions \
    edge-tts \
    faster-whisper

# 复制项目源码
COPY callio/ ./callio/
COPY app/ ./app/
COPY docs/ ./docs/

# 持久化数据目录（数据库、模型缓存）
RUN mkdir -p /app/data
ENV CALLIO_DB_PATH=/app/data/callio.db

# 使用 EdgeTTS 作为容器内默认 TTS（无需本地模型）
ENV CALLIO_TTS_BACKEND=edge
ENV CALLIO_TTS_PRELOAD=0
ENV CALLIO_WHISPER_PRELOAD=0
ENV CALLIO_HOST=0.0.0.0
ENV CALLIO_PORT=8000

EXPOSE 8000

CMD ["python", "-m", "callio"]
