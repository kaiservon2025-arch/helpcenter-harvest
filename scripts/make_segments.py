# -*- coding: utf-8 -*-
"""make_segments.py - assign stable keys to translatable leaves, emit task files.

data/blocks/NNNN.json -> rewritten with a key on every text leaf
data/tasks/T####.json  -> {"task":N,"items":[{"n":..,"title":..,"segments":[{"k":"12-0","html":".."}]}]}

Keys are derived from the article number, so they stay stable across reruns as
long as the article keeps its number.
"""
import glob
import json
import os

import hc

C = hc.Cfg()
BLK, TASKS = C.blocks, C.tasks
BUDGET = int((C.cfg.get("translate") or {}).get("budget") or 12000)


def tag_blocks(bs, n, counter):
    for b in bs:
        if b["t"] in ("p", "h", "quote"):
            b["key"] = "%d-%d" % (n, counter[0])
            counter[0] += 1
        elif b["t"] == "list":
            b["keys"] = []
            for _ in b["items"]:
                b["keys"].append("%d-%d" % (n, counter[0]))
                counter[0] += 1
        elif b["t"] == "table":
            for row in b["rows"]:
                for c in row:
                    c["key"] = "%d-%d" % (n, counter[0])
                    counter[0] += 1
        elif b["t"] == "callout":
            tag_blocks(b["blocks"], n, counter)


def seg_of(bs):
    out = []
    for b in bs:
        if b["t"] in ("p", "h", "quote"):
            out.append({"k": b["key"], "html": b["html"]})
        elif b["t"] == "list":
            for k, it in zip(b["keys"], b["items"]):
                out.append({"k": k, "html": it})
        elif b["t"] == "table":
            for row in b["rows"]:
                for c in row:
                    if c["html"].strip():
                        out.append({"k": c["key"], "html": c["html"]})
        elif b["t"] == "callout":
            out.extend(seg_of(b["blocks"]))
    return out


def emit(ntask, items):
    path = os.path.join(TASKS, "T%04d.json" % ntask)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"task": ntask, "items": items}, f, ensure_ascii=False, indent=0)
    return ntask


def main():
    files = sorted(glob.glob(os.path.join(BLK, "*.json")))
    cur, cur_len, ntask, total_seg = [], 0, 0, 0
    for f in files:
        rec = json.load(open(f, encoding="utf-8"))
        counter = [0]
        tag_blocks(rec["blocks"], rec["n"], counter)
        rec["title_key"] = "title"
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=0)
        segs = seg_of(rec["blocks"])
        total_seg += len(segs)
        size = sum(len(s["html"]) for s in segs) + len(rec["title"])
        item = {"n": rec["n"], "title": rec["title"], "segments": segs}

        if size > BUDGET:  # one article larger than a task: split it, keep the title
            if cur:
                ntask += 1
                emit(ntask, cur)
                cur, cur_len = [], 0
            part, plen = [], 0
            for s in [{"k": "title", "html": rec["title"]}] + segs:
                if plen + len(s["html"]) > BUDGET and part:
                    ntask += 1
                    t = dict(item, segments=part, part=True)
                    emit(ntask, [t])
                    part, plen = [], 0
                part.append(s)
                plen += len(s["html"])
            if part:
                ntask += 1
                emit(ntask, [dict(item, segments=part, part=True)])
            continue

        if cur_len + size > BUDGET and cur:
            ntask += 1
            emit(ntask, cur)
            cur, cur_len = [], 0
        cur.append(item)
        cur_len += size
    if cur:
        ntask += 1
        emit(ntask, cur)
    print("articles:", len(files), "segments:", total_seg, "tasks:", ntask)


if __name__ == "__main__":
    main()
