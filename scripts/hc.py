# -*- coding: utf-8 -*-
"""hc.py - shared config and path resolution for the helpcenter-harvest pipeline.

Every script in this skill resolves its working directory the same way:

  1. --root <dir> on the command line
  2. HC_ROOT environment variable
  3. current working directory

and reads <root>/harvest.config.json (or the file named by --config / HC_CONFIG).
Nothing is hard-coded to one site, so the same scripts work for another help
center once harvest.config.json is written.
"""
import json
import os
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DOCS = {
    "brand": "",
    "cover_title": "",
    "cover_subtitle": "中文培训手册 · 全站资料整理",
    "subtitle": "",
    "header": "",
    "out_name": "",
    "translation_note": "机器翻译 + 术语统一（专有名词保留英文）",
    "scope_fmt": "{groups} 大板块 / {cats} 个分类 / {stages} 个学习阶段 / {articles} 篇文章",
    "intro": [],
}


DEFAULT_INTRO = [
    ("这是什么",
     "本手册把 {site} 帮助中心的全部资料逐篇翻译成中文，按「板块 → 分类 → 阶段 → 文章」四级结构重新编排，"
     "原文中的截图、表格、提示框一并保留，便于团队内部培训、查阅与二次编辑。"),
    ("怎么用",
     "先用目录定位到分类与阶段；每篇文章开头标注原文链接，可随时核对最新原文。"
     "后台菜单名、按钮名保留英文，便于与线上界面一一对应。"),
    ("内容口径",
     "正文为原文完整翻译，不删减、不改写；编号、金额、百分比、编码、链接均按原文保留。"),
    ("时效提醒",
     "资料抓取日期：{date}。平台规则变动频繁，涉及费率、政策、时效的条款，执行前请以后台与官方公告为准。"),
    ("未覆盖内容",
     "① 站内交互式计算器不产生静态文档，未收录；② 以视频为主的内容仅保留外链。"),
]


def load_config(path):
    if not os.path.exists(path):
        raise SystemExit(
            "config not found: %s\n"
            "copy the skill's harvest.config.example.json into the working directory as "
            "harvest.config.json and fill in the site values." % path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Cfg:
    def __init__(self, root=None, config=None, argv=None):
        argv = list(sys.argv[1:] if argv is None else argv)
        root_arg, cfg_arg, rest = _split_argv(argv)
        root = root_arg or root or os.environ.get("HC_ROOT") or os.getcwd()
        self.root = os.path.abspath(root)
        config = cfg_arg or config or os.environ.get("HC_CONFIG") or os.path.join(self.root, "harvest.config.json")
        self.config_path = os.path.abspath(config)
        self.cfg = load_config(self.config_path)
        self.rest = rest

        self.data = os.path.join(self.root, "data")
        self.blocks = os.path.join(self.data, "blocks")
        self.tasks = os.path.join(self.data, "tasks")
        self.zh = os.path.join(self.data, "zh")
        self.images = os.path.join(self.root, "images")
        self.out = os.path.join(self.root, "out")
        for d in (self.data, self.blocks, self.tasks, self.zh, self.images, self.out):
            os.makedirs(d, exist_ok=True)

        self.site = self.cfg.get("site") or "site"
        self.base = (self.cfg.get("base") or "").rstrip("/")
        self.locale = self.cfg.get("locale") or "en"
        self.start_url = self.cfg.get("start_url") or (self.base + "/" + self.locale)

        img = self.cfg.get("images") or {}
        self.img_referer = img.get("referer") or (self.base + "/")
        self.img_max_width = int(img.get("max_width") or 1100)
        self.img_quality = int(img.get("quality") or 86)
        self.img_workers = int(img.get("workers") or 12)

        docs = dict(DEFAULT_DOCS)
        docs.update(self.cfg.get("docs") or {})
        docs["brand"] = docs["brand"] or self.site
        docs["cover_title"] = docs["cover_title"] or docs["brand"]
        docs["subtitle"] = docs["subtitle"] or docs["cover_subtitle"]
        docs["header"] = docs["header"] or ("%s · %s" % (docs["cover_title"], docs["cover_subtitle"]))
        docs["out_name"] = docs["out_name"] or ("%s_中文培训手册.docx" % self.site)
        if not docs.get("intro"):
            docs["intro"] = DEFAULT_INTRO
        self.docs = docs
        self.out_docx = os.path.join(self.out, docs["out_name"])

    # -- endpoints ---------------------------------------------------------
    def endpoint(self, name):
        eps = self.cfg.get("endpoints") or {}
        if name not in eps:
            raise SystemExit("harvest.config.json missing endpoints.%s" % name)
        return eps[name]

    def paging(self):
        return self.cfg.get("pagination") or {}


def _split_argv(argv):
    root = cfg = None
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
            continue
        if a == "--config" and i + 1 < len(argv):
            cfg = argv[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    return root, cfg, rest


def fill(template, **kw):
    """Recursively substitute {placeholders} in strings inside a config fragment."""
    if isinstance(template, str):
        out = template
        for k, v in kw.items():
            out = out.replace("{%s}" % k, str(v))
        return out
    if isinstance(template, list):
        return [fill(x, **kw) for x in template]
    if isinstance(template, dict):
        return {k: fill(v, **kw) for k, v in template.items()}
    return template


def die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    raise SystemExit(2)
