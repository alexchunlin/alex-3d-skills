"""OCR prior art on the hand-labelled CADGenBench dev drawings (tools/verify.d/drawing_labels/), 2026-10-27.

Run each engine in its own venv (outputs [{t, b}] per drawing, template area dropped, to OUT/<engine>/<id>.json),
then score all of them with the drawtools venv:

  /tmp/drawtools-venv/bin/python -I drawing_ocr_compare.py run rapidocr-default OUT 102 103 139 145 147
  /tmp/drawtools-venv/bin/python -I drawing_ocr_compare.py run drawtool OUT ...        # tools/drawing/dtlib.ocr
  /tmp/easyocr-venv/bin/python   -I drawing_ocr_compare.py run easyocr OUT ...         # easyocr 1.7, pip
  /tmp/edocr2-venv/bin/python    -I drawing_ocr_compare.py run edocr2 OUT ...          # clone of javvi51/edocr2 in
                                                                                       # /tmp/dt-prior/edocr2, models in
                                                                                       # /tmp/dt-prior/models
  /tmp/drawtools-venv/bin/python -I drawing_ocr_compare.py score OUT

Every engine is scored with the same matcher (dtlib.textscore: normalised text + touching boxes), so all of them
get the Ø/° misread fixes of dtlib.textparse.norm. eDOCr2 needs Tesseract for its "is this a dimension" filter
and for tables; Tesseract isn't installed, so the filter is stubbed to "yes" (its best case for dimensions).
"""
import json, os, sys, time
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "TF_NUM_INTRAOP_THREADS"):
    os.environ.setdefault(_v, "4")  # torch (EasyOCR) and TensorFlow (eDOCr2) read these at import
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "drawing"))
from dtlib import sheet  # numpy + PIL only
DATA = "/tmp/cgb-data"
TEST = {101, 106, 111, 116, 121, 126, 131, 136, 141, 146}


def box4(q):
    xs = [p[0] for p in q]; ys = [p[1] for p in q]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def run_rapidocr_default(path):
    import cv2
    from rapidocr_onnxruntime import RapidOCR
    eng = run_rapidocr_default.eng = getattr(run_rapidocr_default, "eng", None) or RapidOCR()
    res, _ = eng(cv2.imread(path))
    return [{"t": t, "b": box4(q)} for q, t, s in res or []]


def run_drawtool(path):
    from dtlib import ocr
    return [{"t": d["raw"], "b": d["box"]} for d in ocr.read(sheet.load_gray(path))]


def run_easyocr(path):
    import easyocr, torch
    torch.set_num_threads(4)
    r = run_easyocr.r = getattr(run_easyocr, "r", None) or easyocr.Reader(["en"], gpu=False, verbose=False)
    return [{"t": t, "b": box4(q)} for q, t, s in r.readtext(path)]


def run_edocr2(path):
    sys.path.insert(0, "/tmp/dt-prior/edocr2")
    import cv2
    from edocr2 import tools
    tools.ocr_pipelines.ocr_img_cv2 = lambda *a, **k: ([], None)  # no Tesseract: dimension filter says yes
    P = tools.ocr_pipelines.Pipeline
    if not hasattr(P, "_orig_symbol_search"):
        P._orig_symbol_search = P.symbol_search
        def safe(self, img, dimensions, *a, **k):
            # edocr2 f6f9651 raises "truth value of an array is ambiguous" in symbol_search (list.remove on
            # tuples holding arrays) on most of these sheets; keep the recognised dimensions without the Ø pass
            try:
                return P._orig_symbol_search(self, img, list(dimensions), *a, **k)
            except ValueError:
                run_edocr2.symbol_errors = getattr(run_edocr2, "symbol_errors", 0) + 1
                return dimensions
        P.symbol_search = safe
    if not hasattr(run_edocr2, "m"):
        from edocr2.keras_ocr.recognition import Recognizer
        from edocr2.keras_ocr.detection import Detector
        dim_model = "/tmp/dt-prior/models/recognizer_dimensions_2.keras"
        alphabet = tools.ocr_pipelines.read_alphabet(dim_model)
        rec = Recognizer(alphabet=alphabet); rec.model.load_weights(dim_model)
        run_edocr2.m = (Detector(), rec, alphabet)
    det, rec, alphabet = run_edocr2.m
    img = cv2.imread(path)
    _, frame, gdt_boxes, tables, dim_boxes = tools.layer_segm.segment_img(img, autoframe=True, frame_thres=0.7,
                                                                          GDT_thres=0.02, binary_thres=127)
    proc = img.copy()
    if frame:
        proc = proc[frame.y:frame.y + frame.h, frame.x:frame.x + frame.w]
    dims, other, _, _ = tools.ocr_pipelines.ocr_dimensions(proc, det, rec, alphabet, frame, dim_boxes, cluster_thres=20,
                                                           max_img_size=1048, language="eng", backg_save=False)
    ox, oy = (frame.x, frame.y) if frame else (0, 0)
    out = []
    for t, q in list(dims) + [(o[0], o[1]) for o in other]:
        b = box4(q)
        out.append({"t": str(t), "b": [int(b[0] + ox), int(b[1] + oy), int(b[2] + ox), int(b[3] + oy)]})
    return out


def main():
    if sys.argv[1] == "run":
        eng, out, ids = sys.argv[2], sys.argv[3], sys.argv[4:]
        fn = globals()["run_" + eng.replace("-", "_")]
        os.makedirs(os.path.join(out, eng), exist_ok=True)
        for i in ids:
            assert int(i) not in TEST, "test-set drawing"
            p = f"{DATA}/{i}/input.png"
            t = time.time(); r = fn(p); dt = time.time() - t
            shape = sheet.load_gray(p).shape
            r = [d for d in r if not sheet.in_template(d["b"], shape)]
            json.dump({"secs": round(dt, 1), "items": r}, open(os.path.join(out, eng, f"{i}.json"), "w"))
            print(eng, i, len(r), f"{dt:.1f}s", flush=True)
    elif sys.argv[1] == "score":
        from dtlib import textscore
        out = sys.argv[2]
        lab = os.path.join(HERE, "..", "verify.d", "drawing_labels")
        for eng in sorted(os.listdir(out)):
            tot = dict(tp=0, n_pred=0, n_lab=0, dim_tp=0, dim_pred=0, dim_lab=0); secs = 0; per = []
            for f in sorted(os.listdir(os.path.join(out, eng))):
                d = json.load(open(os.path.join(out, eng, f)))
                s = textscore.score(d["items"], json.load(open(os.path.join(lab, f)))["items"])
                for k in tot: tot[k] += s[k]
                secs += d["secs"]; per.append(f"{f[:3]} {s['P']:.2f}/{s['R']:.2f}")
            n = len(per)
            print(f"{eng:18s} P {tot['tp']/max(1,tot['n_pred']):.3f} R {tot['tp']/tot['n_lab']:.3f} "
                  f"dims P {tot['dim_tp']/max(1,tot['dim_pred']):.3f} R {tot['dim_tp']/tot['dim_lab']:.3f} "
                  f"({tot['n_lab']} labels, {secs/n:.1f} s/sheet)  per drawing P/R: {', '.join(per)}")


if __name__ == "__main__":
    main()
