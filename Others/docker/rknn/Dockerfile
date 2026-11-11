# Offline RKNN converter (.pt -> .rknn for the Orange Pi 5 Pro RK3588 NPU). Runs on the Mac (arm64) via Docker.
#   docker run --rm -v "$PWD":/work brics-rknn yolo export model=models/fire/best.pt format=rknn name=rk3588
FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 build-essential cmake git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
RUN pip install --no-cache-dir "ultralytics" "rknn-toolkit2>=2.3.2,<2.5" "onnx>=1.16.1,<1.19.0" "setuptools<82" onnxslim onnxruntime
ENV YOLO_OFFLINE=1
WORKDIR /work
