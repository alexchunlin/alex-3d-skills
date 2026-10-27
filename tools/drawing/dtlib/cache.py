"""OCR results cached per (image, crop, settings) under /tmp/drawtools-cache, so text, scale --auto and holes
don't re-read the same sheet (a whole-sheet read is 10-20 s)."""
import hashlib, json, os

DIR = os.environ.get("DRAWTOOLS_CACHE", "/tmp/drawtools-cache")


def key(path, *parts):
    st = os.stat(path)
    h = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}|{parts}".encode()).hexdigest()[:16]
    return os.path.join(DIR, h + ".json")


def get(k):
    try:
        return json.load(open(k))
    except (OSError, ValueError):
        return None


def put(k, v):
    os.makedirs(DIR, exist_ok=True)
    tmp = k + f".{os.getpid()}"
    json.dump(v, open(tmp, "w")); os.replace(tmp, k)
