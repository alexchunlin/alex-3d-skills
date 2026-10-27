"""Drawing-reading helpers for the CADGenBench pilot: sheet I/O, OCR, scale and measure, holes, overlay."""
import os as _os

# Cap thread pools (BLAS, OpenMP; ONNX Runtime and OpenCV in ocr.engine) before numpy loads: the tools run
# next to other agents. DRAWTOOLS_THREADS overrides the default of 4.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_v, _os.environ.get("DRAWTOOLS_THREADS", "4"))
