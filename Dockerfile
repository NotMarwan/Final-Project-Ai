FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    libgl1-mesa-glx libglib2.0-0 \
    libsm6 libxext6 libxrender-dev \
    ffmpeg git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY public/ ./public/

RUN mkdir -p reports evidence thumbnails

ENV PYTHONUNBUFFERED=1
ENV AI_SENTINEL_ENABLE_CAPTURE_LOOP=true
ENV STREAM_QUALITY=high

EXPOSE 8000

CMD ["python3", "backend/api.py"]
