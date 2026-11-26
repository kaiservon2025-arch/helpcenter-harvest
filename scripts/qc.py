# -*- coding: utf-8 -*-
"""qc.py - quality check for translated segment files.

Checks every task segment against its Chinese file data/zh/T####.json:
  no-key / empty / not-translated / mostly-english / too-short / tag-mismatch

Writes qc_report.json next to the data directory and prints a summary.
"""
import glob
import json
import os
import re

import hc

C = hc.Cfg()
T, Z = C.tasks, C.zh
CJK = re.compile(r"[\u4e00-\u9fff]")
LAT = re.compile(r"[A-Za-z]{2,}")
TAG = re.compile(r"</?([a-zA-Z0-9]+)")

DEFAULT_WHITELIST = {
    "sku", "fbn", "fbp", "asn", "po", "rtv", "grn", "vat", "trn", "cr", "api", "pdf",
    "excel", "csv", "app", "ios", "android", "b2b", "cod", "eta", "gdpr", "hs", "dha",
}
WHITELIST = DEFAULT_WHITELIST | {w.lower() for w in (C.cfg.get("translate") or {}).get("whitelist") or []}
MIN_RATIO = float((C.cfg.get("translate") or {}).get("min_length_ratio") or 0.16)


def strip(h):
    return re.sub(r"<[^>]+>", "", h or "")


def main():
    bad, total = [], 0
    files = sorted(glob.glob(os.path.join(T, "*.json")))
    for f in files:
        name = os.path.basename(f)
        z = os.path.join(Z, name)
        if not os.path.exists(z):
            bad.append((name, "MISSING", 0))
            continue
        a = json.load(open(f, encoding="utf-8"))
        b = json.load(open(z, encoding="utf-8"))
        segs = {s["k"]: s["html"] for i in a["items"] for s in i["segments"]}
        zh = b.get("segments") or {}
        issues = []
        for k, src in segs.items():
            v = zh.get(k)
            if v is None:
                issues.append((k, "no-key", src[:60]))
                continue
            total += 1
            st, vt = strip(src).strip(), strip(v).strip()
            if not vt:
                issues.append((k, "empty", src[:60]))
                continue
            vc = len(CJK.findall(vt))
            sc = len(CJK.findall(st))
            words = [w.lower() for w in LAT.findall(vt)]
            untranslated = [w for w in words if w not in WHITELIST and not w.isdigit()]
            if vc == 0 and len(untranslated) >= 2:
                issues.append((k, "not-translated", vt[:80]))
            elif len(untranslated) >= 8 and sc < len(untranslated) * 2:
                issues.append((k, "mostly-english", vt[:80]))
            elif len(st) > 220 and len(vt) < len(st) * MIN_RATIO:
                issues.append((k, "too-short", vt[:80]))
            elif TAG.findall(src) != TAG.findall(v):
                issues.append((k, "tag-mismatch", vt[:60]))
        if issues:
            bad.append((name, len(issues), issues[:3]))

    print("task files:", len(files), "segments checked:", total)
    print("files with issues:", len(bad))
    for name, cnt, ex in bad[:20]:
        print("  %s: %s %s" % (name, cnt, ex))
    out = os.path.join(C.root, "qc_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump([{"file": n, "count": c, "examples": e} for n, c, e in bad], f, ensure_ascii=False, indent=1)
    print("report:", out)


if __name__ == "__main__":
    main()
