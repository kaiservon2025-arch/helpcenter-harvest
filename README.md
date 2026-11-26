# helpcenter-harvest

把一个 **SPA 型帮助中心 / 卖家学院 / 知识库** 整站抓下来，解析成结构化内容，翻译成简体中文，质检后生成**带封面、目录、截图、提示框的 Word 培训手册**，并导出 PDF。

> 输入：一个首页 URL。输出：`xxx_中文培训手册.docx` + `.pdf`。

第一次跑通是在 noon 卖家帮助中心（helpcenter.noon.partners）：**233 篇文章、1494 张截图、50.5 MB Word、55.8 MB PDF**，从首页 URL 到成书全自动。

---

## 它解决什么问题

市面上的「网页转 Word」工具在这类站点上基本都失败，因为：

1. 页面是 SPA，HTML 里只有一个空 `<div id="root">`，正文靠 `/api/*` 返回；
2. 正文 HTML 里混着 `class`、`style`、营销组件，直接丢进 Word 会变成一坨；
3. 图片有防盗链，缺 Referer 就 403 或 0 字节；
4. 全英文，要人工翻译 200+ 篇，翻完还得校对有没有漏段、改数字、破坏标签。

这个项目把上面四件事拆成五段流水线，每段都有可复核的中间产物。

## 流水线

```
recon          harvest          build_blocks        segments        成书
首页/JS/sitemap → tree.json  →  blocks + images  →  tasks/*.json →  docx/pdf
   摸接口          抓全站         结构化+下图          切翻译任务      质检/复核/排版
```

| 阶段 | 脚本 | 产物 |
|---|---|---|
| 1. 摸接口 | `harvest.py --discover` / `--check` | 候选 API 列表、各接口条数与字段名 |
| 2. 抓取 | `harvest.py` | `data/tree.json`（含 meta 统计） |
| 3. 结构化 | `build_blocks.py` | `data/blocks/NNNN.json`、`data/index.json`、`images/` |
| 4. 切任务 | `make_segments.py` | `data/tasks/T####.json` |
| 5. 翻译 | 人或 LLM，按 `translate-spec.md` | `data/zh/T####.json` |
| 6. 质检 | `qc.py` | `qc_report.json` |
| 7. 成书 | `build_docx.py` | `out/*.docx` |
| 8. 复核 | `audit.py` | `audit_report.json`（回头重抓比对） |
| 9. 导 PDF | `finalize.ps1` | `out/*.pdf`（需要本机 Word） |

## 安装

### 作为 DSH Skill（推荐）

```powershell
# 全局：所有工作区可用
git clone https://github.com/kaiservon2025-arch/helpcenter-harvest "$env:USERPROFILE\.dsh\skills\helpcenter-harvest"

# 或者只给某个项目用
git clone https://github.com/kaiservon2025-arch/helpcenter-harvest "<项目>\.dsh\skills\helpcenter-harvest"
```

重启 DSH 后，技能目录里会出现 `helpcenter-harvest`；你也可以直接说「把这个帮助中心做成中文手册」，模型会自己加载它。

技能发现根（按优先级）：`<项目>/.dsh/skills` → `<项目>/.agents/skills` → 自定义目录 → `~/.dsh/skills` → `~/.agents/skills`。

### 不用 DSH，纯命令行

把仓库丢到任意目录，直接调 `scripts/*.py` 即可，不依赖 DSH 运行时。

### 依赖

- Python 3.10+：`python-docx`、`lxml`、`Pillow`
- Windows + Microsoft Word（仅 `finalize.ps1` 需要，用于更新目录域、算页码、导 PDF；没有 Word 就到 docx 为止，目录需在 Word 里按 F9 更新）

## 快速开始

```powershell
# 0) 建工作目录，放配置
mkdir D:\work\mysite
copy <repo>\harvest.config.example.json D:\work\mysite\harvest.config.json

# 1) 先探，不写数据
python <repo>\scripts\harvest.py --root D:\work\mysite --discover
python <repo>\scripts\harvest.py --root D:\work\mysite --check

# 2) 小样：只抓 2 个分类，确认图片/表格/提示框都正常
python <repo>\scripts\harvest.py --root D:\work\mysite --only-categories 2
python <repo>\scripts\build_blocks.py --root D:\work\mysite
python <repo>\scripts\make_segments.py --root D:\work\mysite

# 3) 全量抓取
python <repo>\scripts\harvest.py --root D:\work\mysite
python <repo>\scripts\build_blocks.py --root D:\work\mysite
python <repo>\scripts\make_segments.py --root D:\work\mysite

# 4) 目录中文化（半自动：先出脚手架，再补中文）
python <repo>\scripts\nav_zh.py --root D:\work\mysite

# 5) 翻译 data\tasks\T####.json → data\zh\T####.json
#    规则见 scripts\translate-spec.md；200 篇以上建议一批 10–20 个 task 派给子智能体

# 6) 质检 → 成书 → 复核 → PDF
python <repo>\scripts\qc.py --root D:\work\mysite
python <repo>\scripts\build_docx.py --root D:\work\mysite
python <repo>\scripts\audit.py --root D:\work\mysite
powershell -File <repo>\scripts\finalize.ps1 -Docx D:\work\mysite\out\手册.docx -Pdf D:\work\mysite\out\手册.pdf
```

所有脚本都支持 `--root <dir>` / `--config <file>`，也认环境变量 `HC_ROOT` / `HC_CONFIG`；都不给就用当前目录。

只想看效果：`python scripts\build_docx.py --root <dir> 5` 只渲染前 5 篇，几秒出一份小样。

## 接一个新站点

核心只有一步：**把接口和字段名翻译成规范名**。

1. 打开目标站点，F12 → Network → 过滤 `api`，翻几页，找到 4 个接口：分类组、分类、阶段（可选）、文章列表。
2. 抄进 `harvest.config.json` 的 `endpoints`：`path`、`body`（可含 `{locale}` `{category_id}` `{page}` 占位）、`key`（取数键，支持 `a.b`）、`paginated`。
3. 把站点字段名写进 `map`，映射到规范名：

   `id_category_group`、`id_category`、`id_journey_stage`、`id_article`、`name`、`slug`、`title`、`content`、`sort_order`、`description`

   下游脚本只认规范名，站点字段再怪也只改 `map`。
4. `--check` 跑一遍。看到各接口条数正常、`articles` 的 `content` 有长度，就说明配对了。

配置字段完整说明见 [SKILL.md](SKILL.md#配置字段harvestconfigjson)。

## 已知坑（都是真踩过的）

1. **服务端页大小 ≠ 你请求的 `per_page`**。要拿首页返回条数当基准，`len(batch) < 首页条数` 才停；写死 20 或按 `per_page` 判断都会漏。
2. **正文常内联在列表接口里**。别想当然再请求详情接口——多一倍请求，还可能 404。
3. **图片要 Referer**，否则 403 或下载到 0 字节。
4. **阶段列表通常要按分类过滤**。不带 `id_category` 只返回第一页那些，看起来"全站只有 20 个阶段"。配置里写 `{category_id}`，脚本会自动逐分类拉取并去重。
5. **`page` 参数可能被服务端忽略**。页码超范围时一直重复返回最后一页，翻页循环会把 20 条抓成 4000 条。`paged()` 现在按 `id_*` 去重，整页都是旧数据就停。
6. **接口藏在 JS bundle 里**。`--discover` 的正则是起点不是万能，找不到就看 DevTools。
7. **长文必须切段**。单任务超 12000 字符，模型容易截断或漏段。
8. **翻译回来必须机器复检**。模型最常见的三种错：漏 key、把 `<strong>` 翻成中文、偷偷改数字。`qc.py` 就是干这个的。

## 产出长什么样

- 封面：书名、副标题、资料范围统计、原文入口
- 使用说明页：5 段口径说明 + 内容清单表
- 目录：Word TOC 域，四级（板块 / 分类 / 阶段 / 文章）
- 正文：Heading 1–4 分级、原文链接、阅读时长、截图、表格、五色提示框（注意/说明/提示/警告/重要）
- 页眉页脚：书名 + 页码

> 想先看效果，别急着翻 200 篇：`build_docx.py --root <dir> 5` 只渲染前 5 篇，几十秒就能出一份带封面和目录的小样。

## 目录结构

```
.
├── SKILL.md                      # DSH 技能说明（触发条件、验收清单、坑位）
├── harvest.config.example.json   # noon 实例，改字段即可复用
├── scripts/
│   ├── hc.py                     # 配置/路径解析（所有脚本共用）
│   ├── harvest.py                # recon + 全量抓取
│   ├── build_blocks.py           # HTML → blocks + 图片
│   ├── make_segments.py          # blocks → 翻译任务
│   ├── nav_zh.py                 # 板块/分类/阶段中文名脚手架
│   ├── qc.py                     # 翻译质检
│   ├── audit.py                  # 抓取/保真/覆盖度复核
│   ├── build_docx.py             # 成书
│   ├── docx_lib.py               # Word 排版底层（字体、边框、域、超链接）
│   ├── finalize.ps1              # Word COM 更新域 + 导 PDF
│   └── translate-spec.md         # 翻译规范模板（含术语表）
└── references/
    └── noon-case.md              # noon 实跑数据、接口表、踩坑记录
```

## 边界与免责

- 只抓**你已有权访问**的公开/授权内容；请遵守目标站点的 robots.txt 与服务条款，控制并发（默认 sleep 0.2s）。
- 翻译质量取决于所用模型；本项目只保证**不丢内容、不破结构**，不保证译文的业务准确性。费率、政策类条款请以原文为准。
- 站点改版后接口会变，`--check` 是最快的体检手段。

## License

MIT
