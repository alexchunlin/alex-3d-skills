#!/bin/sh
# Build the drawing-tools venv (/tmp/drawtools-venv, Python 3.12). RapidOCR's ONNX models ship in its wheel,
# so nothing is downloaded at run time. OCP is pinned to the CADGenBench venv's build (cadquery-ocp-novtk 7.9.3.1.1);
# the resolver's default pick (cadquery-ocp-proxy 8.0) breaks `import build123d` (no OCP.collections).
set -e
V="${1:-/tmp/drawtools-venv}"
uv venv "$V" --python 3.12
uv pip install --python "$V/bin/python" "rapidocr_onnxruntime==1.4.4" "onnxruntime==1.31.1" \
  "opencv-python-headless==5.0.0.93" "numpy==2.5.4" "pillow==13.0.0" "scipy==1.18.1" "build123d==0.10.0" \
  "cadquery-ocp-novtk==7.9.3.1.1" "cadquery-ocp-proxy==7.9.3.1.1" "ocp-gordon==0.2.2"
"$V/bin/python" -I -c "import rapidocr_onnxruntime, cv2, build123d; print('drawtools venv ok')"
