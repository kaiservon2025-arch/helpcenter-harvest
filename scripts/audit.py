# -*- coding: utf-8 -*-
"""audit.py - does the delivered document really contain everything the site has?

A. re-crawl every category and compare article counts / slugs with data/tree.json
B. per-article text retention: parsed blocks vs raw HTML (<97% is flagged)
C. image accounting: <img> in source vs image blocks + inline images
D. translation coverage: segments that still have no Chinese text
E. docx structure: heading levels, inline shapes, tables, paragraphs

Writes audit_report.json and prints a verdict block. Run it after every build;
a 232-article manual is only trustworthy if all five checks are clean.
"""
import json
import os
import re

from lxml import html as LH

import hc
import harvest as H

C = hc.Cfg()
DATA = C.data
REPORT = os.path.join(C.root, "audit_report.json")


def text_len(h):
    try:
        t = LH.fromstring("<x>" + (h or "") + "</x>").text_content()
    except Exception:  # noqa: BLE001
        t = re.sub(r"<[^>]+>", "", h or "")
    return len(re.sub(r"\s+", "", t))


def count_imgs(h):
    return len(re.findall(r"<img", h or "", re.I))


def block_text(bs):
    out = []
    for b in bs:
        if b["t"] in ("p", "h", "quote"):
            out.append(b.get("html", ""))
        elif b["t"] == "list":
            out.extend(b.get("items", []))
        elif b["t"] == "table":
            for r in b["rows"]:
                for c in r:
                    out.append(c.get("html", ""))
        elif b["t"] == "callout":
            out.append(block_text(b["blocks"]))
    return "".join(out)


def main():
    report = {}
    tree = json.load(open(os.path.join(DATA, "tree.json"), encoding="utf-8"))
    eps = C.cfg["endpoints"]

    print("=" * 72)
    print("A. re-crawl: article counts per category")
    cats = H.norm(H.pick(H.call(eps["categories"]), eps["categories"].get("key") or "data") or [],
                  eps["categories"]["map"])
    api_slugs, per_cat = set(), {}
    for c in cats:
        rows = H.paged(eps["articles"], category_id=c["id_category"], category_slug=c.get("slug"))
        per_cat[c.get("slug")] = len(rows)
        for a in rows:
            api_slugs.add((c.get("slug"), a.get("slug")))
    stored = {(a["_category_slug"], a["slug"]) for a in tree["articles"]}
    missing = api_slugs - stored
    gone = stored - api_slugs
    print("   categories=%d api_articles=%d unique=%d" % (len(cats), sum(per_cat.values()), len(api_slugs)))
    print("   stored=%d  api-not-stored=%d  stored-not-api=%d" % (len(stored), len(missing), len(gone)))
    for x in list(missing)[:5]:
        print("     missing:", x)
    report["api"] = {"categories": len(cats), "api_unique": len(api_slugs), "stored": len(stored),
                     "missing": len(missing), "gone": len(gone), "per_category": per_cat}

    print("=" * 72)
    print("B. per-article text retention")
    blk = {}
    for f in os.listdir(C.blocks):
        d = json.load(open(os.path.join(C.blocks, f), encoding="utf-8"))
        blk[d["slug"]] = d
    raw = {a["slug"]: a.get("content") or "" for a in tree["articles"]}
    bad = []
    for slug, r in raw.items():
        if slug not in blk:
            bad.append((slug, "NO-BLOCKS", 0, 0))
            continue
        a, b = text_len(r), text_len(block_text(blk[slug]["blocks"]))
        ratio = b / a if a else 1
        if ratio < 0.97:
            bad.append((slug, round(ratio, 3), a, b))
    print("   articles=%d  below-97%%: %d" % (len(raw), len(bad)))
    for x in bad[:10]:
        print("     ", x)
    report["retention"] = {"articles": len(raw), "below": len(bad), "worst": bad[:20]}

    print("=" * 72)
    print("C. image accounting")
    raw_imgs = sum(count_imgs(r) for r in raw.values())
    counters = {"blocks": 0, "inline": 0}

    def scan(bs):
        for b in bs:
            if b["t"] in ("img", "imgfail"):
                counters["blocks"] += 1
            elif b["t"] in ("p", "h", "quote"):
                counters["inline"] += count_imgs(b.get("html", ""))
            elif b["t"] == "list":
                for it in b.get("items", []):
                    counters["inline"] += count_imgs(it)
            elif b["t"] == "table":
                for r in b["rows"]:
                    for c in r:
                        counters["inline"] += count_imgs(c.get("html", ""))
            elif b["t"] == "callout":
                scan(b["blocks"])

    for d in blk.values():
        scan(d["blocks"])
    delta = raw_imgs - counters["blocks"] - counters["inline"]
    print("   source <img>=%d  blocks=%d  inline=%d  delta=%d" % (raw_imgs, counters["blocks"], counters["inline"], delta))
    report["images"] = {"source": raw_imgs, "blocks": counters["blocks"], "inline": counters["inline"], "delta": delta}

    print("=" * 72)
    print("D. translation coverage")
    zh = {}
    for f in os.listdir(C.zh):
        d = json.load(open(os.path.join(C.zh, f), encoding="utf-8"))
        zh.update(d.get("segments") or {})
    need = {}

    def collect(bs):
        for b in bs:
            if b["t"] in ("p", "h", "quote"):
                need[b["key"]] = b.get("html", "")
            elif b["t"] == "list":
                for k, it in zip(b.get("keys", []), b.get("items", [])):
                    need[k] = it
            elif b["t"] == "table":
                for r in b["rows"]:
                    for c in r:
                        need[c["key"]] = c.get("html", "")
            elif b["t"] == "callout":
                collect(b["blocks"])

    for d in blk.values():
        collect(d["blocks"])
    missing_t = [k for k in need if not str(zh.get(k, "")).strip()]
    missing_text = [k for k in missing_t if text_len(need[k]) > 0]
    print("   segments=%d translated=%d missing=%d (with text: %d)" %
          (len(need), len(need) - len(missing_t), len(missing_t), len(missing_text)))
    for k in missing_text[:10]:
        print("      ", k, need[k][:80])
    report["translation"] = {"segments": len(need), "missing": len(missing_t), "missing_with_text": len(missing_text)}

    print("=" * 72)
    print("E. docx structure")
    if os.path.exists(C.out_docx):
        from docx import Document
        doc = Document(C.out_docx)
        h = {1: 0, 2: 0, 3: 0, 4: 0}
        for para in doc.paragraphs:
            sn = para.style.name if para.style is not None else ""
            for lv in (1, 2, 3, 4):
                if sn == "Heading %d" % lv:
                    h[lv] += 1
        print("   H1=%d H2=%d H3=%d H4=%d images=%d tables=%d paragraphs=%d" %
              (h[1], h[2], h[3], h[4], len(doc.inline_shapes), len(doc.tables), len(doc.paragraphs)))
        report["docx"] = {"h1": h[1], "h2": h[2], "h3": h[3], "h4": h[4],
                          "images": len(doc.inline_shapes), "tables": len(doc.tables),
                          "paragraphs": len(doc.paragraphs), "path": C.out_docx}
    else:
        print("   docx not found:", C.out_docx)
        report["docx"] = None

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("=" * 72)
    print("verdict: missing=%d retention_bad=%d img_delta=%d missing_text=%d" %
          (report["api"]["missing"], report["retention"]["below"],
           report["images"]["delta"], report["translation"]["missing_with_text"]))
    print("report:", REPORT)


if __name__ == "__main__":
    main()
