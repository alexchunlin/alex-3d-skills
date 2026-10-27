"""Find the drawn views (blobs of ink, dimensions included) so an agent can crop without counting pixels."""
from __future__ import annotations
import numpy as np
import cv2
from . import sheet


def find(gray, gap=40, min_side=80):
    ink = sheet.ink_mask(gray) & ~sheet.template_mask(gray.shape)
    m = ink.astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, gap))
    m = cv2.dilate(m, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    boxes = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        # undo the dilation margin
        x0, y0, x1, y1 = x + gap // 2, y + gap // 2, x + w - gap // 2, y + h - gap // 2
        if max(x1 - x0, y1 - y0) < min_side:
            continue
        sub = ink[y0:y1, x0:x1]
        boxes.append({"box": [int(x0), int(y0), int(x1), int(y1)], "ink": int(sub.sum())})
    # merge boxes that overlap
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i]["box"], boxes[j]["box"]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    boxes[i] = {"box": [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])],
                                "ink": boxes[i]["ink"] + boxes[j]["ink"]}
                    del boxes[j]; changed = True
                    break
            if changed:
                break
    # shaded iso views are dense: ink fraction helps the agent tell them apart
    for b in boxes:
        x0, y0, x1, y1 = b["box"]
        b["fill"] = round(b["ink"] / max(1, (x1 - x0) * (y1 - y0)), 3)
    boxes.sort(key=lambda b: (b["box"][1] // 200, b["box"][0]))
    return boxes
