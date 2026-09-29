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
RUN pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121
RUN pip3 install --no-cache-dir onnxruntime-gpu

COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY public/ ./public/
COPY package.json package-lock.json ./
RUN npm install --production

RUN mkdir -p reports evidence thumbnails backend/models

ENV PYTHONUNBUFFERED=1
ENV AI_SENTINEL_ENABLE_CAPTURE_LOOP=true
ENV AI_SENTINEL_DEVICE=cuda

EXPOSE 3000 8002

CMD ["bash", "-c", "cd backend && python api.py & cd .. && npm run start"]
