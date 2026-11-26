# -*- coding: utf-8 -*-
"""nav_zh.py - scaffold nav_zh.json (Chinese names for groups / categories / stages).

build_docx.py needs nav_zh.json for the cover subtitle, the chapter titles and the
contents table. This script fills it with the English names so the document can be
built immediately; replace the values with Chinese afterwards (they are ~20-40
short strings - one small translation task, not a full pipeline step).

Existing translations are preserved when you re-run it.

Structure written:
  {
    "subtitle": "用于封面副标题的一句话",
    "groups":     {"<id>": ["中文板块名", "中文一句话描述"]},
    "categories": {"<id>": ["中文分类名", "中文一句话描述"]},
    "stages":     {"<id>": "中文阶段名"},
    "group_desc": {"<id>": "中文板块描述"}
  }
"""
import json
import os

import hc

C = hc.Cfg()
INDEX = os.path.join(C.data, "index.json")
OUT = os.path.join(C.root, "nav_zh.json")


def main():
    idx = json.load(open(INDEX, encoding="utf-8"))
    nav = idx["nav"]
    old = {}
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding="utf-8"))

    groups, cats, stages, gdesc = {}, {}, {}, {}
    todo = 0
    for g in nav["groups"]:
        k = str(g["id"])
        prev = (old.get("groups") or {}).get(k) or []
        name = prev[0] if prev else g["name"]
        desc = prev[1] if len(prev) > 1 else (g.get("description") or "")
        groups[k] = [name, desc]
        if g.get("description"):
            gdesc[k] = (old.get("group_desc") or {}).get(k) or g["description"]
        todo += 0 if prev else 1
    for c in nav["categories"]:
        k = str(c["id"])
        prev = (old.get("categories") or {}).get(k) or []
        cats[k] = [prev[0] if prev else c["name"], prev[1] if len(prev) > 1 else (c.get("description") or "")]
        todo += 0 if prev else 1
    for s in nav["stages"]:
        k = str(s["id"])
        stages[k] = (old.get("stages") or {}).get(k) or s["name"]
        todo += 0 if (old.get("stages") or {}).get(k) else 1

    out = {
        "subtitle": old.get("subtitle") or C.docs["subtitle"],
        "groups": groups,
        "categories": cats,
        "stages": stages,
        "group_desc": gdesc,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)
    print("groups=%d categories=%d stages=%d  untranslated=%d" % (len(groups), len(cats), len(stages), todo))
    print("HINT: replace the English values above with Chinese, then rebuild the docx.")


if __name__ == "__main__":
    main()
