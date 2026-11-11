#!/bin/bash
# Convert a trained model to RKNN (Orange Pi 5 Pro NPU) OFFLINE on the Mac, using Docker (Colima).
#   bash setup/convert_rknn.sh models/fire/best.pt [imgsz]
# Output: models/fire/best_rknn_model/  -> use in config:  model: models/fire/best_rknn_model
set -e
cd "$(dirname "$0")/.."
PT=${1:?usage: convert_rknn.sh models/<name>/best.pt [imgsz]}
IMGSZ=${2:-640}
colima status >/dev/null 2>&1 || colima start
ONNX="${PT%.pt}.onnx"
[ -f "$ONNX" ] && cp "$ONNX" "$ONNX.keep"          # the RKNN export rewrites best.onnx -> keep our verified one
docker run --rm --network none -v "$PWD":/work brics-rknn bash -c \
  "mkdir -p /root/.config/Ultralytics && cp /work/weights/Arial*.ttf /root/.config/Ultralytics/ 2>/dev/null; yolo export model=$PT format=rknn name=rk3588 imgsz=$IMGSZ"
[ -f "$ONNX.keep" ] && mv "$ONNX.keep" "$ONNX"
ls -la "$(dirname $PT)" "${PT%.pt}_rknn_model"
echo "use in config:  model: ${PT%.pt}_rknn_model"
