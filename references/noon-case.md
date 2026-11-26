# 案例：noon 卖家帮助中心（2026-11-25 实跑）

## 目标站点
- 入口：`https://helpcenter.noon.partners/en?project=PRJ580249`
- 性质：SPA（`#root` 空壳），页面内容全部由 XHR 从 `/api/*` 拉取，直接抓 HTML 只能拿到空壳。
- 语言：`/en` 与 `/ar` 内容一致，本次只做英文 → 简体中文。

## 规模与产物（真实数字）
| 项目 | 数量/大小 |
|---|---|
| 板块 groups | 5 |
| 分类 categories | 15 |
| 学习阶段 stages | 47（首版误抓 20；2026-11-26 复核为 47，原 49 因站点下线一个分类） |
| 文章 articles | 233（2026-11-25 为 232，次日新增 1 篇） |
| 解析后的 blocks 文件 | 232（`data/blocks/NNNN.json`） |
| 翻译任务 tasks | 215（长文被拆成多段，故少于 233 篇） |
| 图片 | 1494 张（`images/`） |
| `data/tree.json` | 19.4 MB |
| `data/index.json` | 130 KB |
| 成品 docx | 50,575,912 B（约 48 MB） |
| 成品 pdf | 55,755,619 B（约 53 MB） |
| 翻译质检 | 215 个 task，`qc_report.json` 40 KB |

## 接口（POST JSON，均返回 `{...}` 包裹的数组）
| 用途 | 路径 | body | 取数键 |
|---|---|---|---|
| 板块 | `/api/category-group/list` | `{"locale":"en","per_page":100}` | `groups` |
| 分类 | `/api/category/list` | `{"locale":"en"}` | `categories` |
| 阶段 | `/api/stage/list` | `{"locale":"en","per_page":200,"id_category":<分类id>}` | `stages` |
| 文章 | `/api/article/list` | `{"id_category":<id>,"locale":"en","per_page":100,"page":N,"order_by_sort":true}` | `articles` |

## 六个坑（这是本案例最值钱的部分）
1. **服务端把每页压到 20 条**。请求 `per_page=100`，返回仍是 20 条。写死 `page <= 20` 或按 `per_page` 判断结束都会漏数据。正确做法：以首页实际条数作为 `expect`，`len(batch) < expect` 才停（`harvest.py` 的 `paged()` 已这么做）。
2. **文章正文内联在列表接口里**（`articles[].content` 就是完整 HTML），不需要再请求详情接口。所以 232 篇文章只需 15 个分类 × 若干页的列表请求。
3. **图片必须带 Referer**，否则 403/空图。`images.referer` 设为站点根，下载时带上。
4. **阶段接口必须按分类过滤**：`/api/stage/list` 不带 `id_category` 只返回 20 条（看起来像"全站只有 20 个阶段"），带上后每分类 1–6 条，合计 47–49 条。第一版漏了这条，文档目录缺了 2/3 的阶段。
5. **`page` 参数会被忽略**：`page=31` 仍然返回第 1 页的同样 20 条，循环能把 20 条抓成 4000 条。现在 `paged()` 按 `id_*` 去重，整页无新数据即停。
6. **SPA 的接口路径藏在 JS bundle 里**。`assets/home-*.js`、`category-*.js`、`article-*.js` 里能正则出 `/api/...` 字符串；`--discover` 就是干这个的。另有 `/sitemap.xml` 可用来交叉核对分类数量与 URL 形态。

## 结构特征
- 层级：`group → category → stage → article`，排序键分别是四层的 `sort_order`，最后按 `id` 兜底。
- 提示框：`div.hc-callout` + `hc-callout-<variant>`，variant 有 `note / info / idea / warning / alert`，渲染时映射成不同底色与中文标签（注意/说明/思路/警告/警示）。
- 表格：`<table>` 带 `colspan/rowspan`，其余表现属性（style/class/width/height/align/bgcolor）在解析时剥掉，交给 Word 统一排版。
- 图片：多为后台截图，宽度普遍 >1100px，统一缩到 1100 宽、JPEG q86，1494 张压到约 200 MB 以内。

## 翻译与成书
- 每 task ≤12000 字符；超长文章按 `part=true` 拆段，标题只在第一段出现。
- 术语表见 `scripts/translate-spec.md` 第 5 节（noon 版）：SKU/FBN/FBP/ASN/PO/RTV/GRN/COD/VAT/TRN/ZATCA 等保留英文。
- 成书：封面 + 使用说明 + 目录（TOC 域，四级标题）+ 正文；正文按 group/category/stage 三层写 Heading1–4，每篇开头给原文超链接与阅读分钟。
- `finalize.ps1` 用 Word COM 更新域、重排页码、另存 PDF；50 MB 的 docx 转 PDF 约 1–2 分钟。

## 复现命令（本案例）
```powershell
$env:HC_ROOT="D:\DeepSeekHarness\noonhelp"
$env:HC_CONFIG="...\harvest.config.example.json"   # 或复制成 noonhelp\harvest.config.json
python harvest.py --check          # 先确认接口与字段没错
python harvest.py                  # 全量抓取 -> data/tree.json
python build_blocks.py             # -> data/blocks + data/index.json + images
python make_segments.py            # -> data/tasks
python nav_zh.py                   # -> data/nav_zh.json（板块/分类/阶段中文名）
# 逐 task 翻译（人或子智能体，按 translate-spec.md）-> data/zh
python qc.py                       # -> qc_report.json
python build_docx.py               # -> out/<out_name>
python audit.py                    # 覆盖度/保真度复核 -> audit_report.json
powershell -File finalize.ps1 -Docx out\xxx.docx -Pdf out\xxx.pdf
```
