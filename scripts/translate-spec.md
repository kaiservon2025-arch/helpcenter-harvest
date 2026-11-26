# 翻译规范（帮助中心英文 → 简体中文）

> 这是**模板**。每接一个新站点，复制一份到工作目录（如 `translate-spec.<site>.md`），
> 把第 5 节的术语表换成本站点的术语，其余规则不动。

## 任务
把 `data/tasks/T####.json` 里的英文培训内容翻译成**简体中文**，输出到 `data/zh/T####.json`。
一个 task 一次翻译，不要把多个 task 合并处理（长文会截断、漏段）。

## 输入结构
```json
{"task":1,"items":[{"n":1,"title":"Who can sell here?",
  "segments":[{"k":"1-0","html":"...英文HTML..."},{"k":"1-1","html":"<strong>...</strong>"}]}]}
```

## 输出结构（严格）
```json
{"titles":{"1":"中文标题","2":"..."},
 "segments":{"1-0":"译文HTML","1-1":"<strong>译文</strong>"}}
```
- `titles`：每个 item 的中文标题（item 的 `title` 字段）。
- `segments`：**必须覆盖输入里每一个 `k`**，一个都不能少，key 原样保留。
- 只输出这一个 JSON 文件，不要附加任何说明文字、不要包裹 markdown 代码块。

## 翻译要求
1. **只翻译可读文本，不翻译 HTML 标签**。保持标签结构、嵌套、属性（如 `<a href>`、`<br>`、`<strong>`、`<em>`、`<u>`、`<li>`、`<p>`）原样，只替换标签之间的文字。
2. 语言：简体中文，电商运营口吻，准确、简洁、可执行；不要口语化，不要文学化。
3. 段落完整翻译，**禁止省略、合并、概括或用「……」代替**。数字、金额、百分比、日期、时间、URL、邮箱、代码、字段名一律保留原值。
4. 表格单元格、列表项、提示框（Note/Warning）、图注、按钮名称都要翻译。
5. 专有名词保留英文（不译），必要时首次出现可加中文说明。**下表按站点替换**。
6. 常见固定译法（保持一致）：
   - product listing → 商品上架；listing → 商品详情/上架商品
   - fulfillment → 履约；inbound shipment → 入库货件
   - return → 退货；removal → 移除库存；stock/inventory → 库存
   - price/offer price → 价格/报价；deals → 促销活动；coupon → 优惠券
   - payout/settlement → 打款/结算；invoice → 发票；statement → 对账单
   - warranty → 保修；claim → 索赔；reputation → 店铺评分
   - policy → 政策；compliance → 合规；guideline → 规范
   - dashboard → 仪表盘/看板；report → 报表；metric → 指标
   - Click here / Learn more → 点击此处 / 了解更多
   - Note: / Important: / Warning: → 注意：/ 重要：/ 警告：
7. 如果英文句子被截断（原文如此），照实翻译，不要脑补补全。
8. 保留原有的换行与段落切分；不要新增 HTML 标签。

## 5. 站点术语表（示例：noon 卖家帮助中心，按站点替换本节）
- 平台与产品：noon、noon Seller Lab、Seller Lab、noon Ads、Ad Manager、Price Engine、Supermall、noon Express、noon One、noon Minutes、noon Prime、noon Pay、noon Marketplace
- 业务术语：SKU、FBN、FBP、FBN fees、ASN、PO、Buy Box、RTV、GRN、DirectShip、Direct Delivery、Express、Easy Ship、COD、Catalogue/Catalog、Listing、Bundle、Raise a Ticket、Seller Score、Performance Score、Brand Registry
- 合规与证照：VAT、TRN、CR（Commercial Registration）、ZATCA、Emirates ID、IQAMA、Freelance Certificate、Data Certificate、Legal Entity、Authorised Signatory
- 后台名：Seller Lab/Store Dashboard → Seller Lab 后台/店铺后台

## 质检（写文件前自查）
- `len(segments)` 是否等于输入所有 `k` 的数量？
- 有没有 key 拼错、漏 key、多 key？
- 有没有把 `<strong>` 等标签翻成中文或丢掉？
- 有没有中文夹英文残句（除术语表内词外）？
- 数字、金额、URL 是否与原文一致？

写完后可以跑 `python qc.py` 做机器复检（查漏 key、空译文、标签结构不一致、漏译、过短）。

## 返回
写完后只回复一行：`OK tasks=T#### segments=<数量>`。若发现无法处理的条目，回复 `FAIL <原因>`。
