# -*- coding: utf-8 -*-
"""
Assemble the Chinese handbook DOCX from:
  data/index.json  (order + metadata)
  nav_zh.json      (Chinese group/category/stage names)
  data/zh/*.json   (translated segments)
  data/blocks/*.json (structure + local images)
"""
import json, os, glob, re, sys
from datetime import date
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import html as LH
from PIL import Image

from docx_lib import (set_run_font, add_hyperlink, shade, cell_borders, table_borders,
                      fixed_layout, cell_margins, add_field, para_border_bottom,
                      para_box_border, FONT_CN, FONT_EN, ACCENT, GREY)

import hc

C = hc.Cfg()
ROOT, DATA, OUT_DOCX = C.root, C.data, C.out_docx
DOCS = C.docs
os.makedirs(os.path.dirname(OUT_DOCX), exist_ok=True)

BODY_FONT = 10.5
TABLE_FONT = 8.5

CALLOUT_STYLE = {
    "note": ("#F4F7FB", "注意", "#2F5D8A"),
    "info": ("#EAF2FB", "提示", "#1F4E79"),
    "idea": ("#EFF7EC", "要点", "#2E6B2E"),
    "warning": ("#FFF6E3", "警告", "#8A5A00"),
    "alert": ("#FDECEC", "重要", "#9C2B2B"),
}


# ---------------------------------------------------------------- translations
def load_zh():
    zh = {}
    titles = {}
    for f in glob.glob(os.path.join(DATA, "zh", "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        zh.update(d.get("segments", {}))
        for k, v in (d.get("titles") or {}).items():
            titles[str(k)] = v
    return zh, titles


# ---------------------------------------------------------------- inline html
INLINE_MAP = {
    "strong": "bold", "b": "bold", "em": "italic", "i": "italic",
    "u": "underline", "s": "strike", "del": "strike", "code": "code", "kbd": "code",
}


def render_inline(paragraph, html, size=BODY_FONT, base_bold=False, color=None, font=None):
    if not html:
        return
    try:
        frag = LH.fragment_fromstring("<div>" + html + "</div>", create_parent="root")
    except Exception:
        run = paragraph.add_run(re.sub(r"<[^>]+>", "", html))
        set_run_font(run, size, bold=base_bold, color=color)
        return
    state = {"bold": base_bold, "italic": False, "underline": False, "strike": False, "code": False}

    def walk(node):
        if node.text:
            add_text(node.text, state)
        for ch in node:
            tag = (ch.tag or "").lower() if isinstance(ch.tag, str) else ""
            kind = INLINE_MAP.get(tag)
            old = None
            if kind in ("bold", "italic", "underline", "strike", "code"):
                old = state[kind]
                state[kind] = True
            if tag == "br":
                paragraph.add_run().add_break()
            elif tag == "a":
                url = ch.get("href") or ""
                txt = ch.text_content()
                if url.startswith("http") and txt.strip():
                    add_hyperlink(paragraph, url, txt, size=size, bold=state["bold"])
                    if ch.tail:
                        add_text(ch.tail, state)
                    if kind:
                        state[kind] = old
                    return
                walk(ch)
            elif tag == "img":
                add_inline_image(paragraph, ch.get("src") or "")
            else:
                walk(ch)
            if kind and old is not None:
                state[kind] = old
            if ch.tail:
                add_text(ch.tail, state)

    def add_text(txt, st):
        if not txt:
            return
        txt = txt.replace("\xa0", " ")
        if not txt.strip() and txt != " ":
            txt = ""
        if not txt:
            return
        run = paragraph.add_run(txt)
        set_run_font(run, size, bold=st["bold"], italic=st["italic"],
                     underline=st["underline"], color=color, font="Consolas" if st["code"] else font)
        if st["strike"]:
            run.font.strike = True

    walk(frag)
    # trim leading/trailing empty runs
    return


def add_inline_image(paragraph, src):
    if not src:
        return
    import hashlib
    h = hashlib.sha1(src.encode()).hexdigest()[:16]
    path = os.path.join(ROOT, "images", h + ".jpg")
    if not os.path.exists(path):
        return
    run = paragraph.add_run()
    try:
        run.add_picture(path, width=Cm(11.5))
    except Exception:
        pass


def plain(html):
    try:
        return LH.fromstring("<x>" + html + "</x>").text_content()
    except Exception:
        return re.sub(r"<[^>]+>", "", html)


# ---------------------------------------------------------------- blocks
class Builder:
    def __init__(self, doc, zh):
        self.doc = doc
        self.zh = zh
        self.img_count = 0
        self.missing = 0

    def tr(self, key, html):
        v = self.zh.get(key)
        if v is None or not str(v).strip():
            self.missing += 1
            return html
        return v

    def blocks(self, blocks, container, in_callout=False):
        for b in blocks:
            t = b["t"]
            if t == "h":
                lv = b.get("level", 2)
                p = container.add_paragraph()
                if lv <= 2:
                    p.paragraph_format.space_before = Pt(10)
                    p.paragraph_format.space_after = Pt(4)
                else:
                    p.paragraph_format.space_before = Pt(8)
                    p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.keep_with_next = True
                render_inline(p, self.tr(b.get("key"), b.get("html", "")),
                              size={1: 15, 2: 13, 3: 11.5, 4: 11}.get(lv, 10.5), base_bold=True,
                              color=ACCENT)
            elif t == "p":
                p = container.add_paragraph()
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(5)
                p.paragraph_format.line_spacing = 1.45
                render_inline(p, self.tr(b.get("key"), b.get("html", "")))
            elif t == "quote":
                p = container.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.6)
                p.paragraph_format.space_after = Pt(5)
                from docx_lib import para_left_border
                para_left_border(p, "C9D6E4", 12)
                render_inline(p, self.tr(b.get("key"), b.get("html", "")), color=GREY)
            elif t == "list":
                ordered = b.get("ordered")
                for i, (k, item) in enumerate(zip(b.get("keys", []), b.get("items", [])), 1):
                    p = container.add_paragraph()
                    pf = p.paragraph_format
                    pf.left_indent = Cm(0.95)
                    pf.first_line_indent = Cm(-0.5)
                    pf.space_before = Pt(1)
                    pf.space_after = Pt(2)
                    pf.line_spacing = 1.35
                    mark = f"{i}. " if ordered else "• "
                    run = p.add_run(mark)
                    set_run_font(run, BODY_FONT, bold=False, color=ACCENT)
                    render_inline(p, self.tr(k, item))
            elif t == "table":
                self.table(b, container)
            elif t == "img":
                self.image(b, container)
            elif t == "imgfail":
                p = container.add_paragraph()
                run = p.add_run("［图片缺失，原图地址：" + b.get("src", "") + "］")
                set_run_font(run, 8, color=GREY, italic=True)
            elif t == "callout":
                self.callout(b, container)
            elif t == "hr":
                p = container.add_paragraph()
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                para_border_bottom(p, "E3E3E3", 6)
            elif t == "link":
                p = container.add_paragraph()
                run = p.add_run("视频/外链：")
                set_run_font(run, BODY_FONT, bold=True)
                add_hyperlink(p, b["url"], b["url"])

    def image(self, b, container):
        local = b.get("local")
        path = os.path.join(ROOT, local.replace("/", os.sep)) if local else None
        if not path or not os.path.exists(path):
            return
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            return
        p = container.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(6)
        width_cm = 15.4
        if w < 500:
            width_cm = max(6.0, 15.4 * w / 900)
        # cap by height so a very tall screenshot does not dominate the page
        max_h = 19.0
        if h / w * width_cm > max_h:
            width_cm = max_h * w / h
        run = p.add_run()
        run.add_picture(path, width=Cm(min(width_cm, 15.4)))
        para_box_border(p)
        self.img_count += 1

    def callout(self, b, container):
        bg, label, fg = CALLOUT_STYLE.get(b.get("variant", "note"), CALLOUT_STYLE["note"])
        inner = b.get("blocks", [])
        head_txt = plain(inner[0].get("html", "")) if inner and inner[0]["t"] == "p" else ""
        head_txt = (self.tr(inner[0].get("key"), inner[0].get("html", "")) if inner and inner[0]["t"] == "p" else "")
        head_plain = plain(head_txt).strip()
        skip_label = bool(re.match(r"^(注意|提示|警告|重要|要点|Note|Important|Warning|Info|Tip)\s*[:：]", head_plain))
        tbl = container.add_table(rows=1, cols=1)
        tbl.autofit = False
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        cell.width = Cm(15.4)
        shade(cell, bg.lstrip("#"))
        cell_borders(cell, sz=2, color="D8DEE6")
        cell.paragraphs[0].text = ""
        first = cell.paragraphs[0]
        if not skip_label:
            run = first.add_run(label + "　")
            set_run_font(run, 9.5, bold=True, color=RGBColor.from_string(fg.lstrip("#")))
        first.paragraph_format.space_after = Pt(1)
        if len(inner) == 1 and inner[0]["t"] == "p":
            render_inline(first, self.tr(inner[0].get("key"), inner[0].get("html", "")), size=9.5)
        else:
            self.blocks(inner, cell)
        container.add_paragraph().paragraph_format.space_after = Pt(2)

    def table(self, b, container):
        rows = b["rows"]
        ncols = max((sum(c.get("colspan", 1) for c in r) for r in rows), default=1)
        tbl = container.add_table(rows=len(rows), cols=ncols)
        tbl.autofit = False
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        fixed_layout(tbl)
        table_borders(tbl, sz=3, color="C9CFD6")
        cell_margins(tbl, 30, 30, 55, 55)
        total = 15.4
        for col in tbl.columns:
            col.width = Cm(total / ncols)

        # occupancy plan
        occ = [[False] * ncols for _ in range(len(rows))]
        plan = []
        for ri, row in enumerate(rows):
            ci = 0
            for c in row:
                while ci < ncols and occ[ri][ci]:
                    ci += 1
                if ci >= ncols:
                    break
                cs = max(1, min(c.get("colspan", 1), ncols - ci))
                rs = max(1, min(c.get("rowspan", 1), len(rows) - ri))
                for r2 in range(ri, ri + rs):
                    for c2 in range(ci, ci + cs):
                        occ[r2][c2] = True
                plan.append((ri, ci, rs, cs, c))
                ci += cs

        # merges
        for ri, ci, rs, cs, c in plan:
            if rs > 1 or cs > 1:
                try:
                    tbl.cell(ri, ci).merge(tbl.cell(ri + rs - 1, ci + cs - 1))
                except Exception:
                    pass
        # keep rows intact across pages + repeat header row
        for row in tbl.rows:
            trPr = row._tr.get_or_add_trPr()
            cs_el = OxmlElement("w:cantSplit")
            trPr.append(cs_el)
        if rows and all(c.get("head") for c in rows[0]):
            trPr = tbl.rows[0]._tr.get_or_add_trPr()
            th = OxmlElement("w:tblHeader")
            trPr.append(th)
        # clear
        for ri, ci, rs, cs, c in plan:
            cell = tbl.cell(ri, ci)
            for p in cell.paragraphs[1:]:
                p._element.getparent().remove(p._element)
            cell.paragraphs[0].text = ""
        if rows and all(c.get("head") for c in rows[0]):
            for cell in tbl.rows[0].cells:
                for p_ in cell.paragraphs:
                    p_.paragraph_format.keep_with_next = True
        # fill
        for ri, ci, rs, cs, c in plan:
            cell = tbl.cell(ri, ci)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.2
            if c.get("head"):
                shade(cell, "E9EFF6")
            render_inline(p, self.tr(c.get("key"), c.get("html", "")), size=TABLE_FONT,
                          base_bold=bool(c.get("head")))
        container.add_paragraph().paragraph_format.space_after = Pt(2)


# ---------------------------------------------------------------- doc setup
def setup(doc):
    st = doc.styles["Normal"]
    st.font.name = FONT_EN
    st.font.size = Pt(BODY_FONT)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    st.paragraph_format.line_spacing = 1.45
    st.paragraph_format.space_after = Pt(4)

    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.4)
    sec.right_margin = Cm(2.4)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)
    sec.different_first_page_header_footer = True


def header_footer(doc, title):
    sec = doc.sections[0]
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = hp.add_run(title)
    set_run_font(run, 8, color=RGBColor(0x8C, 0x8C, 0x8C))
    para_border_bottom(hp, "DDDDDD", 4)

    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = fp.add_run("第 ")
    set_run_font(r, 9, color=GREY)
    for rr in add_field(fp, " PAGE ", "1"):
        set_run_font(rr, 9, color=GREY)
    r = fp.add_run(" 页 / 共 ")
    set_run_font(r, 9, color=GREY)
    for rr in add_field(fp, " NUMPAGES ", "1"):
        set_run_font(rr, 9, color=GREY)
    r = fp.add_run(" 页")
    set_run_font(r, 9, color=GREY)



def add_toc_styles(doc):
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    sizes = {1: 22, 2: 20, 3: 19, 4: 18}
    inds = {1: 0, 2: 240, 3: 480, 4: 720}
    bold = {1: True, 2: False, 3: False, 4: False}
    styles_el = doc.styles.element
    for lvl in (1, 2, 3, 4):
        sid = f"TOC{lvl}"
        if styles_el.find(f"{{*}}{sid}") is not None:
            continue
        xml = (
            f'<w:style {nsdecls("w")} w:type="paragraph" w:styleId="{sid}">'
            f'<w:name w:val="toc {lvl}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>'
            f'<w:uiPriority w:val="39"/><w:unhideWhenUsed/>'
            f'<w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
            f'<w:ind w:left="{inds[lvl]}" w:firstLine="0"/></w:pPr>'
            f'<w:rPr>{"<w:b/>" if bold[lvl] else ""}<w:sz w:val="{sizes[lvl]}"/></w:rPr>'
            f'</w:style>'
        )
        styles_el.append(parse_xml(xml))

def cover(doc, nav_zh, stats):
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(DOCS["cover_title"])
    set_run_font(run, 30, bold=True, color=ACCENT)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    run = p.add_run(DOCS["cover_subtitle"])
    set_run_font(run, 18, bold=True, color=RGBColor(0x33, 0x33, 0x33))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(18)
    run = p.add_run(nav_zh["subtitle"])
    set_run_font(run, 11, color=GREY)

    for _ in range(4):
        doc.add_paragraph()

    rows = [
        ("资料范围", DOCS["scope_fmt"].format(groups=stats['groups'], cats=stats['cats'],
                                              stages=stats['stages'], articles=stats['articles'])),
        ("配图数量", f"{stats['images']} 张（已嵌入正文对应位置）"),
        ("整理日期", stats["date"]),
        ("翻译方式", DOCS["translation_note"]),
    ]
    tbl = doc.add_table(rows=len(rows), cols=2)
    tbl.autofit = False
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    fixed_layout(tbl)
    for i, (k, v) in enumerate(rows):
        c0, c1 = tbl.cell(i, 0), tbl.cell(i, 1)
        c0.width = Cm(3.2)
        c1.width = Cm(11.0)
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(k)
        set_run_font(r0, 10, bold=True, color=ACCENT)
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(v)
        set_run_font(r1, 10)
        for c in (c0, c1):
            c_borders_off(c)
        c1_bottom = c1
        para = p1
        para.paragraph_format.space_after = Pt(6)
        p0.paragraph_format.space_after = Pt(6)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("原文出处　")
    set_run_font(r, 9, color=GREY)
    add_hyperlink(p, C.start_url, C.start_url.replace("https://", "").replace("http://", ""), size=9)
    doc.add_page_break()


def c_borders_off(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for e in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{e}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tcPr.append(borders)


def intro_page(doc, stats, nav_zh):
    p = doc.add_paragraph()
    run = p.add_run("使用说明")
    set_run_font(run, 16, bold=True, color=ACCENT)
    para_border_bottom(p, "1F4E79", 8)
    p.paragraph_format.space_after = Pt(10)

    paras = [(h, t.replace("{site}", C.site).replace("{date}", stats["date"]))
             for h, t in (DOCS.get("intro") or [])]
    for h, t in paras:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        run = p.add_run("▍ " + h)
        set_run_font(run, 11, bold=True, color=RGBColor(0x2F, 0x5D, 0x8A))
        p2 = doc.add_paragraph()
        p2.paragraph_format.left_indent = Cm(0.4)
        run2 = p2.add_run(t)
        set_run_font(run2, 10)

    # 统计表
    doc.add_paragraph()
    p = doc.add_paragraph()
    run = p.add_run("内容清单")
    set_run_font(run, 12, bold=True, color=ACCENT)

    tbl = doc.add_table(rows=1, cols=3)
    tbl.style = "Table Grid"
    tbl.autofit = True
    hdr = ["板块", "分类", "文章数"]
    for i, h in enumerate(hdr):
        cell = tbl.rows[0].cells[i]
        shade(cell, "E9EFF6")
        cell.paragraphs[0].text = ""
        r = cell.paragraphs[0].add_run(h)
        set_run_font(r, 9, bold=True)
    for gid, (gname, gdesc) in nav_zh["groups"].items():
        cats = [c for c in stats["cat_rows"] if str(c["group"]) == str(gid)]
        for c in cats:
            row = tbl.add_row()
            vals = [gname if c is cats[0] else "", c["zh"], str(c["count"])]
            for i, v in enumerate(vals):
                cell = row.cells[i]
                cell.paragraphs[0].text = ""
                r = cell.paragraphs[0].add_run(v)
                set_run_font(r, 9)
    doc.add_page_break()


def toc(doc):
    p = doc.add_paragraph()
    run = p.add_run("目　录")
    set_run_font(run, 18, bold=True, color=ACCENT)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)

    p = doc.add_paragraph()
    for rr in add_field(p, ' TOC \\o "1-4" \\h \\z \\u ',
                        "（在 Word / WPS 中按 F9 或右键“更新域”生成带页码的目录）"):
        set_run_font(rr, 10)
    doc.add_page_break()


# ---------------------------------------------------------------- main
def main(only_first=None, out=None):
    idx = json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))
    nav_zh = json.load(open(os.path.join(ROOT, "nav_zh.json"), encoding="utf-8"))
    zh, titles = load_zh()
    articles = idx["articles"]
    if only_first:
        articles = articles[:only_first]

    doc = Document()
    setup(doc)
    add_toc_styles(doc)
    header_footer(doc, DOCS["header"])

    # group/category/stage structure
    groups = {str(g["id"]): g for g in idx["nav"]["groups"]}
    cats = {str(c["id"]): c for c in idx["nav"]["categories"]}
    stages = {str(s["id"]): s for s in idx["nav"]["stages"]}

    ordered = {}
    for a in articles:
        ordered.setdefault(str(a["group_id"]), {}).setdefault(str(a["cat_slug"]), []).append(a)

    def count_imgs(bs):
        c = 0
        for b in bs:
            if b["t"] == "img":
                c += 1
            elif b["t"] == "callout":
                c += count_imgs(b["blocks"])
        return c

    nmax = max(a["n"] for a in articles)
    img_total = 0
    for f in glob.glob(os.path.join(DATA, "blocks", "*.json")):
        if int(os.path.basename(f)[:4]) <= nmax:
            img_total += count_imgs(json.load(open(f, encoding="utf-8"))["blocks"])

    stats = {
        "groups": len(ordered), "cats": len({a["cat_slug"] for a in articles}),
        "stages": len({a["stage_id"] for a in articles if a["stage_id"] not in (None, "None")}),
        "articles": len(articles),
        "images": img_total,
        "date": date.today().isoformat(),
        "cat_rows": [],
    }

    cat_rows = []
    for gid, cats_ in ordered.items():
        for slug, ar in cats_.items():
            cid = None
            for a in ar:
                for c in idx["nav"]["categories"]:
                    if c["slug"] == slug:
                        cid = c["id"]
            cat_rows.append({"group": gid, "zh": nav_zh["categories"].get(str(cid), slug), "count": len(ar)})
    stats["cat_rows"] = cat_rows

    cover(doc, nav_zh, stats)
    intro_page(doc, stats, nav_zh)
    toc(doc)

    b = Builder(doc, zh)
    part_no = 0
    chap_no = 0
    groups_sorted = sorted(ordered.items(), key=lambda kv: groups.get(kv[0], {}).get("sort", 99))
    for gid, cats_ in groups_sorted:
        part_no += 1
        gname, gdesc = nav_zh["groups"].get(str(gid), (groups.get(str(gid), {}).get("name", gid), ""))
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(f"第 {part_no} 部分")
        set_run_font(run, 12, bold=True, color=RGBColor(0x8C, 0x8C, 0x8C))
        p2 = doc.add_paragraph()
        p2.style = doc.styles["Heading 1"]
        run = p2.add_run(gname)
        set_run_font(run, 22, bold=True, color=ACCENT)
        p2.paragraph_format.space_after = Pt(4)
        desc = nav_zh.get("group_desc", {}).get(str(gid), gdesc)
        p3 = doc.add_paragraph()
        run = p3.add_run(gdesc or "")
        set_run_font(run, 10.5, color=GREY, italic=False)
        para_border_bottom(p3, "C9D6E4", 8)
        p3.paragraph_format.space_after = Pt(12)

        cats_sorted = sorted(cats_.items(), key=lambda kv: cats.get(kv[0], {}).get("sort", 99))
        for slug, arts in cats_sorted:
            chap_no += 1
            cid = next((c["id"] for c in idx["nav"]["categories"] if c["slug"] == slug), None)
            cname, cdesc = nav_zh["categories"].get(str(cid), (slug, ""))
            h = doc.add_paragraph()
            h.style = doc.styles["Heading 2"]
            h.paragraph_format.space_before = Pt(14)
            h.paragraph_format.space_after = Pt(6)
            h.paragraph_format.page_break_before = True
            run = h.add_run(f"第 {chap_no} 章　{cname}")
            set_run_font(run, 18, bold=True, color=ACCENT)
            if cdesc:
                p = doc.add_paragraph()
                run = p.add_run(cdesc)
                set_run_font(run, 10, color=GREY)
                p.paragraph_format.space_after = Pt(8)

            # stages order
            st_order = {}
            for a in arts:
                sid = str(a["stage_id"])
                if sid not in st_order:
                    st = stages.get(sid, {})
                    st_order[sid] = st.get("sort", 999)
            stage_keys = sorted({str(a["stage_id"]) for a in arts}, key=lambda s: st_order.get(s, 999))
            sec_no = 0
            for sid in stage_keys:
                sec_no += 1
                sarts = [a for a in arts if str(a["stage_id"]) == sid]
                sname = nav_zh["stages"].get(sid, stages.get(sid, {}).get("name", "其他"))
                show = not (sid in ("None", "none") or sname in (None, ""))
                if show:
                    h = doc.add_paragraph()
                    h.style = doc.styles["Heading 3"]
                    h.paragraph_format.space_before = Pt(12)
                    h.paragraph_format.space_after = Pt(4)
                    h.paragraph_format.keep_with_next = True
                    h.paragraph_format.page_break_before = False
                    run = h.add_run(f"{chap_no}.{sec_no}　{sname}")
                    set_run_font(run, 13.5, bold=True, color=RGBColor(0x2F, 0x5D, 0x8A))
                for i, a in enumerate(sarts, 1):
                    blk = json.load(open(os.path.join(DATA, "blocks", f"{a['n']:04d}.json"), encoding="utf-8"))
                    blk.setdefault("read_minutes", a.get("read_minutes"))
                    t_zh = titles.get(str(a["n"])) or blk["title"]
                    prefix = f"{chap_no}.{sec_no}.{i}" if show else f"{chap_no}.{i}"
                    h = doc.add_paragraph()
                    h.style = doc.styles["Heading 4"]
                    h.paragraph_format.space_before = Pt(10)
                    h.paragraph_format.space_after = Pt(2)
                    h.paragraph_format.keep_with_next = True
                    run = h.add_run(f"{prefix}　{t_zh}")
                    set_run_font(run, 11.5, bold=True, color=RGBColor(0x1A, 0x1A, 0x1A))

                    meta = doc.add_paragraph()
                    meta.paragraph_format.space_after = Pt(4)
                    r = meta.add_run("原文：")
                    set_run_font(r, 8, color=GREY)
                    add_hyperlink(meta, a["url"], a["url"], size=8)
                    if blk.get("read_minutes"):
                        r = meta.add_run(f"　·　阅读约 {blk['read_minutes']} 分钟")
                        set_run_font(r, 8, color=GREY)

                    b.blocks(blk["blocks"], doc)
                    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    if out:
        doc.save(out)
    else:
        doc.save(OUT_DOCX)
    print("saved:", out or OUT_DOCX)
    print("images embedded:", b.img_count, "missing translations:", b.missing)
    return b


def cats_id(idx, slug):
    for c in idx["nav"]["categories"]:
        if c["slug"] == slug:
            return c["id"]
    return slug


def walk_blocks(slug):
    return []


if __name__ == "__main__":
    args = [a for a in C.rest if not a.startswith("-")]
    n = int(args[0]) if args else None
    out = args[1] if len(args) > 1 else None
    main(n, out)
