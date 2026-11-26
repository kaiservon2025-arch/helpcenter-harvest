---
name: helpcenter-harvest
description: 把一个 SPA 型「帮助中心 / 卖家学院 / 知识库」整站抓下来，解析成结构化 blocks，分段翻译成简体中文，质检后生成带目录、封面、截图、提示框的 Word 培训手册并导出 PDF。适用于 noon、Shopee、Amazon 这类前后端分离、正文靠 /api 返回的站点；也适用于任何能用 JSON 接口列出分类与文章的站内知识库。
whenToUse: 用户要求把某个后台/帮助中心/卖家学院的资料整理成中文手册、离线文档、培训材料，或要求"把这个知识库抓下来"、"做成 Word/PDF"时。
---

# helpcenter-harvest：帮助中心 → 中文培训手册

一条从「只知道首页 URL」到「50 MB 带目录的 Word + PDF」的流水线。核心不在抓，而在**把 SPA 的接口摸出来、正文一字不少地搬进 Word、翻译段落不丢**。

## 什么时候用 / 不用

**用**：目标是 SPA 型帮助中心（HTML 是空壳，内容走 `/api/*`），需要全量、离线、可翻译、可打印。
**不用**：静态站直接 `wget`/`httpx` 更省事；只要几十篇时手工复制更快；站点有强登录风控（需要真浏览器 cookie）时，先用 Envoy/浏览器导出 cookie 再回来。

## 前置条件

- Python 3.10+，装 `python-docx`、`lxml`、`Pillow`（DSH 自带运行时已含）。
- Windows + 已安装 Microsoft Word（只有 `finalize.ps1` 需要，用于更新目录域、算页码、导 PDF；没有 Word 就到 docx 为止）。
- 一个可写工作目录，里面放 `harvest.config.json`。

## 快速开始

```powershell
# 0) 建工作目录并放配置
mkdir D:\work\mysite
copy <skill>\harvest.config.example.json D:\work\mysite\harvest.config.json
# 编辑配置：site / base / start_url / locale / endpoints / docs

# 1) 摸接口（不改任何数据）
python <skill>\scripts\harvest.py --discover
python <skill>\scripts\harvest.py --check

# 2) 抓 → 解析 → 分段
python <skill>\scripts\harvest.py --only-categories 2   # 先试 2 个分类，确认结构正常
python <skill>\scripts\harvest.py                       # 再全量
python <skill>\scripts\build_blocks.py
python <skill>\scripts\make_segments.py

# 3) 目录中文名
python <skill>\scripts\nav_zh.py

# 4) 翻译 data\tasks\T####.json → data\zh\T####.json（按 translate-spec.md）
#    可自己译，也可派子智能体，一批 10–20 个 task

# 5) 质检 → 成书 → 复核 → 导 PDF
python <skill>\scripts\qc.py
python <skill>\scripts\build_docx.py
python <skill>\scripts\audit.py
powershell -File <skill>\scripts\finalize.ps1 -Docx out\手册.docx -Pdf out\手册.pdf
```

所有脚本都认 `--root <dir>` / `--config <file>`，也认环境变量 `HC_ROOT` / `HC_CONFIG`；都不给就用当前目录。

## 配置字段（harvest.config.json）

| 字段 | 说明 |
|---|---|
| `site` / `base` / `locale` / `start_url` | 站点标识、根地址、语言、入口页（含 project 参数就带上） |
| `article_url` | 原文链接模板，占位符 `{base} {locale} {category_slug} {slug}` |
| `headers` | 附加请求头，常用 `Origin`、`Referer`（不少站点校验） |
| `endpoints.{groups,categories,stages,articles}` | 每个接口：`path`、`body`（可含 `{locale} {category_id} {page}`）、`key`（取数键，支持 `a.b`）、`paginated`、`map` |
| `map` | 把站点字段映射到规范名：`id_category_group / id_category / id_journey_stage / id_article / name / slug / title / content / sort_order / description`。**下游脚本只认规范名**，站点字段再怪也只改这里 |
| `pagination.max_pages` / `sleep` | 翻页上限与间隔（默认 200 / 0.2s；到上限会打印 WARNING，说明有数据没抓完） |
| `images.referer` / `max_width` / `quality` / `workers` | 图片防盗链 Referer、缩放宽度（1100）、JPEG 质量（86）、并发（12） |
| `translate.budget` | 单个翻译任务的字符上限（默认 12000） |
| `translate.whitelist` | 质检时认可为"可不译"的英文词（站点术语） |
| `docs` | 书名、封面、页眉、使用说明五段（`{site}` `{date}` 占位）、`out_name` |

## 五阶段都做了什么

1. **recon**：`--discover` 抓首页 → 列出 script bundle → 正则出候选 API → 读 sitemap 统计 URL 形态。`--check` 打一遍各接口，打印条数、字段名、`content` 长度——**这是判断 map 有没有配错的最快方式**。
2. **harvest**：按 groups → categories → stages → articles 顺序 POST；文章按分类翻页、按 `(category_slug, slug)` 去重；写 `data/tree.json`。若所有文章 `content` 为空会直接报错并提示检查 `map.content`，不会静默产出空手册。
3. **build_blocks**：lxml 解析正文 HTML → 类型化 blocks（标题/段落/列表/表格/图片/提示框/引用），剥掉表现属性保留 `colspan/rowspan`，图片并发下载并压缩；输出 `data/blocks/NNNN.json` + `data/index.json`（含 nav 与正文统计）。
4. **segments + 翻译**：把每个可译叶子打稳定 key（`{n}-{i}`，列表与表格单元格各有 key），按字符预算切 task；翻译只替换标签之间的文字，标签结构原样返回；`qc.py` 查漏 key、空译文、标签结构不一致、未译、过短。
5. **成书**：`build_docx.py` 按 group → category → stage 写 Heading 1–4，封面 + 使用说明 + TOC 域 + 正文；`finalize.ps1` 用 Word COM 更新域与页码并导 PDF；`audit.py` 回头重新抓一遍，核对文章数量、正文保留率（<0.97 报警）、图片数量差、翻译覆盖率。

## 验收清单（交付前逐条过）

- [ ] `--check` 四个接口条数正常，`articles` 有 content 且长度合理
- [ ] `tree.json.meta.articles` 与站点 sitemap/侧边栏数量对得上（差 1–2 篇要能解释）
- [ ] `audit_report.json`：无 `missing`（文章缺失）、`retention_bad` 为空、`img_delta` 为 0
- [ ] `qc_report.json`：无 `no-key / empty / tag-mismatch`；`mostly-english` 逐条看过
- [ ] docx 打开后目录页码正确、图片不糊、表格不串行、提示框有底色
- [ ] PDF 页数与 docx 一致，文件能正常打开
- [ ] `nav_zh.py` 打印的"未翻译"数量已处理或明确接受

## 已知坑（新站点先看这几条）

1. **服务端页大小 ≠ 你请求的 `per_page`**。以首页返回条数为准，`len(batch) < 首页条数` 才停；写死 20 或按 `per_page` 判断都会漏。
2. **正文常内联在列表接口**，不要想当然去请求详情接口（多一倍请求，还可能 404）。
3. **图片要 Referer**，否则 403 或下载到 0 字节。
4. **阶段（stage）列表通常要按分类过滤**：不带 `id_category` 只会返回第一页那 20 条，看起来"只有 20 个阶段"。配置里把 `{category_id}` 写进 `endpoints.stages.body`，脚本会自动逐分类拉并去重。
5. **`page` 参数可能被服务端忽略**：页码超出范围时，服务端会一直重复返回最后一页，翻页循环会无限抓到同一个 20 条（曾抓到 4000 条重复）。`paged()` 现在按 `id_*` 去重，发现整页都是旧数据就停。
6. **SPA 接口藏在 JS bundle**，`--discover` 的正则是起点，不是万能；找不到就看 DevTools Network。
7. **长文必须切段**：单 task 超过 12000 字符，模型会截断或漏段，`make_segments.py` 已按预算切。
8. **翻译回来要机器复检**：模型最常见的错是漏 key、把 `<strong>` 翻成中文、把数字改了。`qc.py` 就是干这个的。

## 规模化建议（200 篇以上）

- 翻译是唯一的重活。按 task 分派子智能体，**一个子智能体 10–20 个 task**，每个只读自己的输入、只写自己的 `data/zh/T####.json`，返回 `OK tasks=... segments=...`；全部回来后再跑 `qc.py`。
- 全量抓取前先 `--only-categories 2` 试跑，确认图片、提示框、表格都正常再放开。
- 图片多时先跑 `build_blocks.py` 看 `images/` 体积，必要时把 `max_width` 降到 900。

## 目录结构

```
<skill>/
  SKILL.md
  harvest.config.example.json     # noon 实例，改字段即可复用
  scripts/
    hc.py            # 配置/路径解析（所有脚本共用）
    harvest.py       # recon + 全量抓取
    build_blocks.py  # HTML → blocks + 图片
    make_segments.py # blocks → 翻译任务
    nav_zh.py        # 板块/分类/阶段中文名脚手架
    qc.py            # 翻译质检
    audit.py         # 抓取/保真/覆盖度复核
    build_docx.py    # 成书
    docx_lib.py      # Word 排版底层（字体、边框、域、超链接）
    finalize.ps1     # Word COM 更新域 + 导 PDF
    translate-spec.md# 翻译规范模板（含术语表）
  references/
    noon-case.md     # noon 实跑数据、接口表、五个坑
```
