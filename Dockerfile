FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 DATA_DIR=/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements-video.txt requirements-deploy.txt ./
# CPU-only wheels avoid shipping unused CUDA libraries.
RUN pip install --no-cache-dir torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements-deploy.txt
COPY . .
RUN python tools/prepare_video.py
EXPOSE 8080
CMD ["python", "deploy_server.py"]
