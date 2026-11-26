# -*- coding: utf-8 -*-
"""build_blocks.py - turn raw article HTML into typed blocks + local images.

In : data/tree.json (written by harvest.py)
Out: data/index.json, data/blocks/NNNN.json, images/<sha1>.jpg

Block types: h / p / list / table / img / imgfail / hr / link / callout / quote
Every translatable text leaf later gets a stable key (see make_segments.py).
"""
import hashlib
import io
import json
import os
import re
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from lxml import html as LH
from PIL import Image

import hc

C = hc.Cfg()
ROOT, DATA, IMG, BLK = C.root, C.data, C.images, C.blocks
ctx = ssl.create_default_context()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def clean_inner(el):
    """innerHTML with editor cruft removed."""
    for bad in el.xpath(".//script | .//style | .//noscript"):
        bad.getparent().remove(bad)
    for e in el.iter():
        if e.tag in ("img", "br", "hr"):
            continue
        # drop presentational attributes except colspan/rowspan
        for attr in ("style", "class", "width", "height", "align", "bgcolor", "border",
                     "cellpadding", "cellspacing", "colwidth", "data-variant", "loading", "decoding"):
            if attr in e.attrib:
                del e.attrib[attr]
    s = (el.text or "")
    for child in el:
        s += LH.tostring(child, encoding="unicode", method="html")
    s = re.sub(r"<(\w+)[^>]*></\1>", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    return s.strip()


def has_img(el):
    return bool(el.xpath(".//img"))


def walk(el, blocks, imgmap):
    for ch in el.iterchildren():
        tag = ch.tag if isinstance(ch.tag, str) else ""
        cls = ch.get("class") or ""
        if tag in ("script", "style", "noscript"):
            continue
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            t = clean_inner(ch)
            if t:
                blocks.append({"t": "h", "level": int(tag[1]), "html": t})
        elif tag == "p":
            if has_img(ch) and not (ch.text or "").strip():
                for im in ch.xpath(".//img"):
                    add_img(blocks, im)
                continue
            t = clean_inner(ch)
            if t and re.sub(r"<[^>]+>|&nbsp;|\s", "", t):
                blocks.append({"t": "p", "html": t})
        elif tag in ("ul", "ol"):
            items = []
            for li in ch.xpath("./li") or ch.xpath(".//li"):
                t = clean_inner(li)
                if t:
                    items.append(t)
            if items:
                blocks.append({"t": "list", "ordered": tag == "ol", "items": items})
        elif tag == "table":
            rows = []
            for tr in ch.xpath(".//tr"):
                cells = []
                for td in tr.xpath("./td | ./th"):
                    cells.append({
                        "html": clean_inner(td),
                        "head": td.tag == "th",
                        "colspan": int(td.get("colspan") or 1),
                        "rowspan": int(td.get("rowspan") or 1),
                    })
                if cells:
                    rows.append(cells)
            if rows:
                blocks.append({"t": "table", "rows": rows})
        elif tag == "img":
            add_img(blocks, ch)
        elif tag == "hr":
            blocks.append({"t": "hr"})
        elif tag == "video":
            src = ch.get("src") or (ch.xpath("./source/@src") or [""])[0]
            if src:
                blocks.append({"t": "link", "url": src, "label": "video"})
        elif tag == "details":
            summ = ch.xpath("./summary")
            if summ:
                t = clean_inner(summ[0])
                if t:
                    blocks.append({"t": "h", "level": 4, "html": t})
            body = LH.Element("div")
            for c2 in ch.iterchildren():
                if c2.tag != "summary":
                    body.append(c2)
            walk(body, blocks, imgmap)
        elif tag == "div" and "hc-callout" in cls:
            variant = "note"
            m = re.search(r"hc-callout-(\w+)", cls)
            if m:
                variant = m.group(1)
            inner = LH.Element("div")
            for c2 in ch.iterchildren():
                inner.append(c2)
            sub = []
            walk(inner, sub, imgmap)
            if sub:
                blocks.append({"t": "callout", "variant": variant, "blocks": sub})
            elif (ch.text or "").strip():
                blocks.append({"t": "callout", "variant": variant,
                               "blocks": [{"t": "p", "html": clean_inner(ch)}]})
        elif tag in ("div", "section", "article", "center", "tbody"):
            walk(ch, blocks, imgmap)
        elif tag == "blockquote":
            t = clean_inner(ch)
            if t:
                blocks.append({"t": "quote", "html": t})
        elif tag == "a":
            t = clean_inner(ch)
            if t:
                blocks.append({"t": "p", "html": t})
        elif tag == "br":
            continue
        else:
            t = clean_inner(ch)
            if t and re.sub(r"<[^>]+>|&nbsp;|\s", "", t):
                blocks.append({"t": "p", "html": t})


def add_img(blocks, im):
    src = (im.get("src") or "").strip()
    if not src:
        return
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = C.base + src
    blocks.append({"t": "img", "src": src, "alt": (im.get("alt") or "").strip()})


def norm_text(blocks):
    """plain text of blocks, for stats/audit."""
    out = []
    for b in blocks:
        if b["t"] in ("p", "h", "quote"):
            if b.get("html"):
                out.append(LH.fromstring("<x>" + b["html"] + "</x>").text_content())
        elif b["t"] == "list":
            for it in b["items"]:
                out.append("- " + LH.fromstring("<x>" + it + "</x>").text_content())
        elif b["t"] == "table":
            for row in b["rows"]:
                out.append(" | ".join(LH.fromstring("<x>" + c["html"] + "</x>").text_content() for c in row))
        elif b["t"] == "callout":
            out.extend(norm_text(b["blocks"]))
    return out


def img_local(src):
    return hashlib.sha1(src.encode()).hexdigest()[:16]


def download(url, path_base):
    for ext in (".jpg", ".png"):
        p = path_base + ext
        if os.path.exists(p) and os.path.getsize(p) > 500:
            return p
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity",
                                                   "Referer": C.img_referer})
        raw = urllib.request.urlopen(req, timeout=60, context=ctx).read()
        im = Image.open(io.BytesIO(raw))
        im.load()
        if im.mode in ("P", "RGBA", "LA"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        w = C.img_max_width
        if im.width > w:
            im = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
        p = path_base + ".jpg"
        im.save(p, "JPEG", quality=C.img_quality, optimize=True)
        return p
    except Exception as e:  # noqa: BLE001 - one bad image must not stop the crawl
        print("IMGFAIL", url, type(e).__name__, str(e)[:80], flush=True)
        return None


def main():
    tree = json.load(open(os.path.join(DATA, "tree.json"), encoding="utf-8"))
    groups = {g["id_category_group"]: g for g in tree["groups"]}
    cats = {c["id_category"]: c for c in tree["categories"]}
    stages = {s["id_journey_stage"]: s for s in tree["stages"]}
    arts = tree["articles"]
    url_tpl = (C.cfg.get("article_url") or "{base}/{locale}/category/{category_slug}/{slug}")

    def sk(a):
        c = cats.get(a["_category_id"], {})
        g = groups.get(c.get("id_category_group"), {})
        st = stages.get(a.get("id_journey_stage"), {})
        return (g.get("sort_order", 99), c.get("sort_order", 99), st.get("sort_order", 999),
                a.get("sort_order") or 0, str(a["id_article"]).zfill(6))

    arts.sort(key=sk)

    allsrc, parsed = [], {}
    for a in arts:
        doc = LH.fromstring("<div id='root'>" + (a.get("content") or "") + "</div>")
        blocks = []
        walk(doc, blocks, None)
        parsed[a["slug"]] = blocks

        def collect(bs):
            for b in bs:
                if b["t"] == "img":
                    allsrc.append(b["src"])
                elif b["t"] == "callout":
                    collect(b["blocks"])

        collect(blocks)
    uniq = sorted(set(allsrc))
    print("articles:", len(arts), "img refs:", len(allsrc), "unique imgs:", len(uniq), flush=True)

    def job(u):
        return u, download(u, os.path.join(IMG, img_local(u)))

    ok = {}
    with ThreadPoolExecutor(max_workers=C.img_workers) as ex:
        for i, (u, p) in enumerate(ex.map(job, uniq), 1):
            ok[u] = p
            if i % 100 == 0:
                print("  images", i, "/", len(uniq), flush=True)

    index = []
    total_chars = 0
    for n, a in enumerate(arts, 1):
        blocks = parsed[a["slug"]]

        def fix(bs):
            for b in bs:
                if b["t"] == "img":
                    p = ok.get(b["src"])
                    b["local"] = os.path.relpath(p, ROOT).replace("\\", "/") if p else None
                    if not p:
                        b["t"] = "imgfail"
                elif b["t"] == "callout":
                    fix(b["blocks"])

        fix(blocks)
        c = cats.get(a["_category_id"], {})
        g = groups.get(c.get("id_category_group"), {})
        st = stages.get(a.get("id_journey_stage"), {})
        url = a.get("url") or url_tpl.format(base=C.base, locale=C.locale,
                                             category_slug=a["_category_slug"], slug=a["slug"])
        rec = {
            "n": n,
            "id": a["id_article"],
            "slug": a["slug"],
            "url": url,
            "title": a["title"],
            "group_en": g.get("name"), "group_id": g.get("id_category_group"),
            "cat_en": c.get("name"), "cat_slug": a["_category_slug"],
            "stage_en": st.get("name"), "stage_id": a.get("id_journey_stage"),
            "read_minutes": a.get("read_minutes"),
            "blocks": blocks,
        }
        with open(os.path.join(BLK, "%04d.json" % n), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=0)
        txt = "\n".join(norm_text(blocks))
        total_chars += len(txt)
        row = {k: rec[k] for k in ("n", "id", "slug", "url", "title", "group_en", "group_id",
                                   "cat_en", "cat_slug", "stage_en", "stage_id", "read_minutes")}
        row["text_chars"] = len(txt)
        index.append(row)

    nav = {
        "groups": [{"id": g["id_category_group"], "name": g["name"], "sort": g["sort_order"],
                    "description": g.get("description")}
                   for g in sorted(tree["groups"], key=lambda x: x["sort_order"])],
        "categories": [{"id": c["id_category"], "name": c["name"], "slug": c["slug"],
                        "sort": c["sort_order"], "group": c["id_category_group"],
                        "description": c.get("description")}
                       for c in sorted(tree["categories"], key=lambda x: x["sort_order"])],
        "stages": [{"id": s["id_journey_stage"], "name": s["name"], "cat": s.get("id_category"),
                    "sort": s["sort_order"], "description": s.get("description")}
                   for s in sorted(tree["stages"], key=lambda x: (str(x.get("id_category")), x["sort_order"]))],
    }
    with open(os.path.join(DATA, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"nav": nav, "articles": index}, f, ensure_ascii=False, indent=1)
    print("text chars total:", total_chars, "avg:", total_chars // max(1, len(arts)))
    print("images ok:", sum(1 for v in ok.values() if v), "/", len(uniq))


if __name__ == "__main__":
    main()
