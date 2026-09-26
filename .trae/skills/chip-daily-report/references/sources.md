# 芯片行业新闻来源（分级动态源库）

> 最后更新: 2026-08-07
> 版本: v5.1（A 级表改为由 rules/rule_registry.yaml 单一注册表生成，X7 裁决）
> 维护规则：每月核查源可用性，发现失效源及时标注或替换
> **重要**：A 级来源表（下方 GEN 标记之间）由 `scripts/gen_rules.py` 从 `rules/rule_registry.yaml` 自动生成，**禁止手工编辑**；改域名只改注册表后重跑生成器。注册表↔脚本↔本表 双向差集必须为 0（X7）。Samsung 统一用父域 `samsung.com`（X8）。

## 使用规则

1. **A级优先**：搜索时优先使用A级源，确保A级占比≥30%
2. **B级追溯**：使用B级聚合源时，必须追溯到原始来源并标注（如"今日头条转载自财联社"）
3. **C级禁止**：C级来源一律不使用，发现即丢弃
4. **双语搜索**：每个环节至少查2个来源（1个中文源+1个英文源）
5. **失效处理**：标注"已停更"的源仅用于历史背景，不作为主要新闻来源

## A级来源（权威：官方/行业组织/权威媒体）

> 使用规则：优先使用，**至少30%新闻来自A级**

<!-- GEN:ALEVEL:START -->
| 来源 | 类型 | 网址 | 适用环节 | 备注 |
|------|------|------|----------|------|
| TSMC 官方 | 权威源 | https://www.tsmc.com | 制造 | 法说会纪要、投资者关系页 |
| Samsung 官方（父域） | 权威源 | https://www.samsung.com/semiconductor | 设计/制造/封测 | X8：父域匹配，覆盖 news.samsung.com 与 semiconductor.samsung.com |
| SK hynix 官方 | 权威源 | https://www.skhynix.com | 制造/封测 | HBM 相关官方公告 |
| SK hynix 新闻室 | 权威源 | https://news.skhynix.com | 制造/封测 | HBM 相关官方新闻 |
| Intel Newsroom | 权威源 | https://www.intel.com | 设计/制造 | 英特尔官方新闻 |
| ASML 官方 | 权威源 | https://www.asml.com | 材料/设备 | 光刻设备官方新闻稿（2026-09-26 评审回路补录：唯一 EUV 厂商一手来源） |
| Amkor 官方（父域，公告含 ir.amkor.com） | 权威源 | https://www.amkor.com | 封测 | 封测厂官方公告/投资者关系页（2026-09-26 评审回路补录，与 tsmc.com 同类一手来源） |
| NVIDIA 官方 | 权威源 | https://www.nvidia.com | 设计 | GPU/AI 芯片官方发布 |
| NVIDIA Newsroom | 权威源 | https://nvidianews.nvidia.com | 设计 | NVIDIA 官方新闻室 |
| SEMI | 权威源 | https://www.semi.org | 材料/设备 | 设备销售预测、行业数据 |
| SEMI 大半导体产业网 | 权威源 | https://www.semi.org.cn | 材料/设备 | SEMI 中国官方 |
| TechInsights | 权威源 | https://www.techinsights.com | 综合 | 拆解分析、技术情报 |
| SemiAnalysis | 权威源 | https://www.semianalysis.com | 综合 | 深度行业分析 |
| EDN | 权威源 | https://www.edn.com | 设计/EDA | 电子设计技术媒体 |
| Semiconductor Engineering | 权威源 | https://semiengineering.com | EDA/材料/设备 | 半导体工程媒体 |
| EET-China | 权威源 | https://www.eet-china.com | 综合 | 电子工程专辑中文版 |
| 中国新闻网 | 权威源 | https://www.chinanews.com.cn | 综合 | 封测/产业政策 |
| 财联社 | 权威源 | https://www.cls.cn | 制造/综合 | 快讯、公司动态 |
| 新华社 | 权威源 | https://www.news.cn | 综合 | 产业政策、重大动态 |
| 上海证券报 | 权威源 | https://www.cnstock.com | 综合 | 上市公司公告 |
| 证券时报 | 权威源 | https://www.stcn.com | 综合 | 上市公司公告 |
| 巨潮资讯 | 权威源 | https://www.cninfo.com.cn | 综合 | 上市公司官方公告 |
| 21世纪经济报道 | 权威源 | https://www.21jingji.com | 综合 | 产业分析、SEMI 等预测 |
| 界面新闻 | 权威源 | https://www.jiemian.com | 综合 | 封测/产业动态 |
| 经济日报 | 权威源 | http://www.ce.cn | 综合 | 产业经济政策 |
| 中国经济网 | 权威源 | http://www.cet.com.cn | 综合 | 产业经济报道 |
| 新华网 | 权威源 | https://www.xinhuanet.com | 综合 | 权威时政产业 |
| 人民网 | 权威源 | http://www.people.com.cn | 综合 | 权威综合媒体 |
| 央视网 | 权威源 | https://www.cctvl.com | 综合 | 权威视频/图文新闻 |
| 中国日报 | 权威源 | https://www.chinadaily.com.cn | 综合 | 英文权威对外媒体 |
| 第一财经 | 权威源 | https://www.yicai.com | 综合 | 财经产业报道 |
| 中国电子报 | 权威源 | https://www.cena.com.cn | 综合 | 电子信息产业权威媒体 |
| DigiTimes | 权威源 | https://www.digitimes.com | 制造/封测 | 台积电/代工产能独家 |
| 电子时报 DigiTimes | 权威源 | https://www.digitimes.com.tw | 制造/封测 | 台系代工/封测独家 |
| IEEE Xplore | 权威源 | https://ieeexplore.ieee.org | 设计/EDA | 学术论文 |
| Wiley Online Library | 权威源 | https://onlinelibrary.wiley.com | 封测/制造 | Engineering Reports 等工程研究成果 |
| ISSCC | 权威源 | https://www.isscc.org | 设计/制造 | X7：顶级会议，芯片设计领域顶级 |
| VLSI Symposium | 权威源 | https://www.vlsisymposium.org | 制造/设计 | X7：超大规模集成电路研讨会，制程技术发布重镇 |
| DAC | 权威源 | https://www.dac.com | EDA/设计 | X7：设计自动化大会，EDA 工具和设计方法学 |
| IEDM | 权威源 | https://www.ieee-iedm.org | 制造/材料/设备 | X7：国际电子器件大会，器件和工艺技术突破 |
| Nature | 权威源 | https://www.nature.com | 综合 | X7：Nature Electronics 等前沿半导体研究 |
| Nikkei Asia | 权威源 | https://asia.nikkei.com | 制造/综合 | 台积电/代工独家报道 |
| Reuters | 权威源 | https://www.reuters.com | 综合 | 国际权威通讯社 |
| Bloomberg | 权威源 | https://www.bloomberg.com | 综合 | 国际财经权威 |
| Chosun Ilbo | 权威源 | https://www.chosun.com | 综合 | 韩国权威媒体（半导体独家） |
| Korea Times | 权威源 | https://www.koreatimes.co.kr | 综合 | 韩国英文权威媒体 |
<!-- GEN:ALEVEL:END -->

## B级来源（聚合：新闻聚合平台/门户）

> 使用规则：可使用，但需追溯到原始来源并标注

| 来源 | 类型 | 网址 | 备注 |
|------|------|------|------|
| 今日头条 | 聚合平台 | https://www.toutiao.com | 需追溯原始来源 |
| 新浪财经 | 门户财经 | https://finance.sina.com.cn | 需追溯原始来源 |
| 网易科技 | 门户科技 | https://tech.163.com | 需追溯原始来源 |
| 搜狐科技 | 门户科技 | https://m.sohu.com | 需追溯原始来源 |
| 东方财富网 | 财经门户 | https://www.eastmoney.com | 需追溯原始来源 |
| 雪球 | 投资社区 | https://xueqiu.com | 需追溯原始来源 |
| 快科技 | 科技媒体 | https://www.mydrivers.com | 需追溯原始来源 |
| 腾讯新闻 | 门户 | https://news.qq.com | 需追溯原始来源 |

## C级来源（禁止：社交媒体/未验证）

> 使用规则：**一律禁止使用**

| 来源 | 类型 | 原因 |
|------|------|------|
| 微博 | 社交媒体 | 未经验证，可能是传言 |
| Twitter/X | 社交媒体 | 未经验证，可能是传言 |
| 抖音/快手 | 短视频 | 无法验证真实性 |
| 知乎帖文 | 社区问答 | 用户生成内容，未经验证 |
| 小红书 | 社交电商 | 用户生成内容，未经验证 |
| B站 | 视频社区 | 用户生成内容，未经验证 |

## 已停更/历史存档源

| 来源 | 原类型 | 状态 | 备注 |
|------|--------|------|------|
| AnandTech | 权威媒体 | **已停更**（2024年停站） | 仅用于历史背景，不作主要来源 |

## 来源级别判定规则

若遇到未列入本清单的来源，按以下规则判定级别：

| 特征 | 判定 |
|------|------|
| 域名含 .com 且为厂商官方/行业组织/权威媒体 | A级 |
| 域名含 .org 且为行业组织 | A级 |
| 域名含 .gov 且为政府机构 | A级 |
| 内容为上市公司公告（巨潮/交易所） | A级 |
| 内容为学术论文（IEEE/Nature等） | A级 |
| 聚合平台转载但标注了原始来源 | B级（追溯到原始A/B级源） |
| 个人博客/自媒体 | C级 |
| 社交媒体帖文 | C级 |

## 搜索关键词模板

### A级限定搜索（优先使用，确保A级占比≥30%）

> **核心策略**：先搜索A级域名站内新闻，再补充B级聚合源。这样可以一次性确保A级≥30%，避免事后回溯补搜。

**中文 site:限定搜索**：
- 财联社：`site:cls.cn 芯片 半导体`
- 中国新闻网：`site:chinanews.com.cn 芯片 半导体`
- EET-China：`site:eet-china.com 芯片 EDA`
- 21世纪经济报道：`site:21jingji.com 半导体 设备`
- 界面新闻：`site:jiemian.com 封装 先进封装`
- SEMI中国：`site:semi.org.cn 设备 市场`
- 巨潮资讯：`site:cninfo.com.cn 芯片 业绩`

**英文 site:限定搜索**：
- TSMC：`site:tsmc.com investor relations earnings`
- Samsung：`site:news.samsung.com semiconductor foundry`
- SEMI：`site:semi.org equipment market forecast`
- Nikkei Asia：`site:asia.nikkei.com TSMC semiconductor`
- SemiAnalysis：`site:semianalysis.com AI chip`
- EDN：`site:edn.com chip design`
- Semiconductor Engineering：`site:semiengineering.com EDA packaging`

### 通用搜索（补充搜索，B级来源）

**中文关键词**
- 设计：`AI芯片 设计 发布 规格 性能`
- 制造：`晶圆代工 制程 产能 HBM DRAM`
- 封测：`先进封装 HBM封装 测试 封测厂`
- EDA：`EDA工具 Synopsys Cadence 仿真`
- 材料设备：`半导体材料 光刻机 电子特气 光刻胶`

**英文关键词**
- Design: `chip design GPU AI semiconductor news`
- Manufacturing: `foundry process node HBM wafer`
- Packaging: `advanced packaging HBM packaging test`
- EDA: `EDA tools Synopsys Cadence simulation`
- Materials: `semiconductor materials lithography equipment`

### 技术突破搜索（v5.0新增，捕获学术会议和前沿技术进展）

> **核心策略**：搜索近期顶级学术会议和技术突破，将课堂知识与产业实践连接。这类新闻往往包含制程节点、器件结构、工艺参数等技术维度信息，是技术注解的重要来源。

**学术会议搜索关键词**：
- ISSCC（芯片设计）: `ISSCC 2026 chip design processor` / `ISSCC 2026 论文 芯片`
- VLSI Symposium（制程技术）: `VLSI Symposium 2026 process node` / `VLSI 2026 制程 工艺`
- DAC（EDA/设计方法学）: `DAC 2026 EDA design automation` / `DAC 2026 设计自动化`
- IEDM（器件/工艺突破）: `IEDM 2026 device transistor` / `IEDM 2026 器件 工艺`
- Nature Electronics: `Nature Electronics semiconductor 2026` / `Nature Electronics 半导体 突破`

**技术突破搜索关键词**（按技术方向）：
- 晶体管结构: `GAA transistor breakthrough 2026` / `CFET 全环绕晶体管 突破`
- 先进制程: `2nm process node 2026` / `1.4nm 制程 进展`
- 先进封装: `3D IC packaging breakthrough` / `Chiplet 互连 突破`
- 存储技术: `HBM4 development 2026` / `存算一体 芯片 突破`
- 新材料: `silicon photonics breakthrough` / `碳化硅 氮化镓 进展`
- EDA工具: `AI chip design automation 2026` / `AI辅助 芯片设计 EDA`

**site:限定搜索（学术源）**：
- IEEE Xplore: `site:ieeexplore.ieee.org semiconductor 2026`
- Nature: `site:nature.com semiconductor chip 2026`
- SEMI: `site:semi.org equipment market forecast 2026`


---

## 信号来源分层（扩展池 · 手工维护）

> **作用**：本表是 A 级白名单之外、供 SKILL 生成步骤**主动调用**的「信号来源分层」。A 级白名单只管「能不能用」（校验），本表管「先去哪抓」（生成）。生成时必须按 Tier 从高到低优先，且每期至少纳入 Tier-0/1 的一手/英文信号，避免漂回中文聚合源。
> **类型标签**：`news`=行业新闻 / `ir`=公司投资者关系 / `earnings`=法说会·业绩 / `filing`=监管文件(8-K/公告) / `analysis`=深度分析
> **与白名单关系**：白名单↔本表不冲突——白名单裁掉 C 级，本表决定抓取优先级。改本表不影响 `scripts/gen_rules.py` 自动生成的 A 级表（X7）。

### Tier-0 公司一手（IR / 法说会 / 官方公告）— 最该扩、最缺的一类
| 公司 | 类型 | 入口 | 环节 |
|------|------|------|------|
| TSMC 台积电 | ir / earnings | https://ir.tsmc.com | 制造 |
| Samsung Semiconductor | ir | https://www.samsung.com/semiconductor | 设计/制造 |
| SK hynix | ir / earnings | https://news.skhynix.com | 制造/封测 |
| Intel | ir / earnings | https://www.intel.com/newsroom | 设计/制造 |
| NVIDIA | ir / earnings | https://nvidianews.nvidia.com | 设计 |
| AMD | ir / earnings | https://ir.amd.com | 设计 |
| ASML | ir / earnings | https://www.asml.com | 设备 |
| Applied Materials | ir | https://www.appliedmaterials.com | 设备 |
| Lam Research | ir | https://www.lamresearch.com | 设备 |
| KLA | ir | https://www.kla.com | 设备 |
| Micron 美光 | ir / earnings | https://investors.micron.com | 制造/封测 |
| Broadcom | ir | https://www.broadcom.com | 设计 |
| 中芯国际 SMIC | ir / earnings | https://www.smci.com | 制造 |
| 华虹半导体 | ir | https://www.huahong.com | 制造 |
| 北方华创 | ir | https://www.naura.com | 设备 |
| 中微公司 AMEC | ir | https://www.amec-inc.com | 设备 |
| 长电科技 | filing | 上交所/巨潮公告 | 封测 |
| 寒武纪 | filing | 上交所/巨潮公告 | 设计 |
| 盛美上海 | ir | 公司官网投资者关系 | 设备 |

### Tier-1 英文权威行业媒体 / 深度分析 — 当前最大缺口
| 来源 | 类型 | 网址 | 备注 |
|------|------|------|------|
| SemiAnalysis | analysis | https://www.semianalysis.com | 付费深度，全球行业风向标（同赛道 A 股映射关键） |
| DigiTimes（EN / TW） | news | https://www.digitimes.com | 台系代工/封测独家产能信号 |
| Semiconductor Engineering | news | https://semiengineering.com | EDA/材料/器件 |
| EE Times | news | https://www.eetimes.com | 全球电子工程 |
| TechInsights | analysis | https://www.techinsights.com | 拆解/技术情报 |
| TrendForce（EN） | analysis | https://www.trendforce.com | 存储/代工价格与产能数据 |
| The Elec | news | https://www.thelec.net | 韩国存储/面板一手 |
| Tom's Hardware | news | https://www.tomshardware.com | 消费级芯片动态 |
| AnandTech | analysis | https://www.anandtech.com | 架构深度（已停更，仅作背景） |

### Tier-2 监管 / 财报原始文件 — 一手事实，不转述
| 来源 | 类型 | 入口 | 适用 |
|------|------|------|------|
| SEC EDGAR | filing | https://www.sec.gov/cgi-bin/browse-edgar | 美股 8-K / 10-Q / 13F |
| 上交所 / 深交所 | filing | 巨潮/沪/深官方公告 | A 股公告 |
| 台湾公开资讯观测站 MOPS | filing | https://mops.twse.com.tw | 台股公告 |
| 韩国 DART | filing | https://dart.fss.or.kr | 韩股公告 |

### Tier-3 中文权威媒体 — 已有 A 级白名单，重申用于生成优先
财联社 / 证券时报 / 新华网 / 21 世纪经济报道 / 中国电子报 / EET-China — 生成时优先于 Tier-4。

### Tier-4 聚合 / 社媒 — 仅 B 级，须追溯原始来源
腾讯新闻 / 今日头条 / 网易 — 仅作线索，正文须标注「原始: X」（同 X14 原始出处规则），禁止作为唯一来源。

### 生成调用纪律（X17 新增）
1. 每期先从 **Tier-0/1** 取 ≥3 条一手/英文信号，再补 Tier-3 中文权威；Tier-4 仅作线索。
2. 每条 Tier-4 聚合源必须标注「原始: X」（X14 一致）。
3. 财报季（1/4/7/10 月及前后）必须将 Tier-0 法说会 + Tier-2 8-K 作为「重点企业动态」重点覆盖。
4. 英文源占比偏低时，优先补 Tier-1，而非堆 Tier-4 中文聚合。

---

## 常用数据源池（实战验证 · 每日优先检索，v5.4 新增）

> **作用**：把历次实战中**命中率高、验证可用的来源与搜索 query** 固化下来。每日生成 Step 2 时**先按本池检索**（命中即用、天然 A 级），池内不足再按上方 Tier 分层补搜。避免每次重复试错、节省搜索时间。
> **纪律**：池内来源全部经 `validate_report.py` 白名单验证（标 ✅ = A 级）；标 ⚠️ 的不在白名单、判 B 级，仅作线索需追溯或换 A 级源。

### 按环节首选来源矩阵（每日第一优先）

| 环节 | Tier-0/1 首选源（A级✅） | Tier-3 中文首选源（A级✅） | 已验证搜索 query | 命中内容 |
|------|------------------------|---------------------------|-----------------|---------|
| 制造·存储 | [SK hynix 新闻室](https://news.skhynix.com) ✅ / [Samsung Semiconductor](https://semiconductor.samsung.com) ✅ | 证券时报 stcn.com ✅ / 财联社 cls.cn ✅ | `SK hynix HBM news` / `site:news.skhynix.com` / `site:semiconductor.samsung.com memory` / `长鑫 存储 DRAM 扩产` | HBM/HBF 官方公告、存储厂财报、扩产 |
| 制造·代工 | [TSMC IR](https://ir.tsmc.com) ✅ / [DigiTimes](https://www.digitimes.com) ✅ | 财联社 cls.cn ✅ | `TSMC monthly sales` / `site:tsmc.com investor relations` / `台积电 法说会 营收` | 台积电月营收、法说会 |
| 设计 | [AMD Newsroom](https://www.amd.com) ⚠️B / [NVIDIA](https://nvidianews.nvidia.com) ✅ | 财联社 cls.cn ✅ | `AMD EPYC production ramp` / `site:cls.cn Anthropic 芯片` / `AI芯片 自研 定制` | CPU/GPU 量产、AI 公司自研芯片 |
| 封测 | [Brief Asia](https://www.briefasia.com) ⚠️B / [DigiTimes](https://www.digitimes.com.tw) ✅ | 新浪财经引上海证券报 sina.com.cn ⚠️B | `STATS ChipPAC price` / `OSAT advanced packaging price increase` / `日月光 先进封装 涨价` | OSAT 涨价、先进封装产能 |
| EDA | [SemiEngineering](https://semiengineering.com) ✅ | 财联社/21 世纪经济报道 ✅ | `EDA acquisition AI` / `site:eet-china.com EDA` / `国产EDA 并购` | EDA 并购、AI-EDA |
| 材料/设备 | [EET-China](https://www.eet-china.com) ✅ | 中国新闻网 chinanews.com.cn ✅ | `site:eet-china.com 光刻胶` / `光刻胶 产线 投产` / `电子特气 国产化` | 光刻胶、特气、材料国产化 |
| 政策 | [EET-China](https://www.eet-china.com) ✅ | 新华网 news.cn ✅ | `Japan semiconductor export control effective` / `site:eet-china.com 出口管制` / `半导体 管制 生效` | 出口管制、政策生效 |
| 催化剂 | [TSMC 投资者日历](https://www.tsmc.com/schinese/investorRelations/financial_calendar.htm) ✅ | 新浪财经（转载公告）sina.com.cn ⚠️B | `中芯国际 业绩说明会 公告` / `earnings date semiconductor` | 法说会、财报日、月营收日 |

### 韩国/存储一手新闻（英文，A级 ✅）

| 来源 | 入口 | 覆盖 | 验证结论 |
|------|------|------|---------|
| 朝鲜日报英文版 | https://www.chosun.com/english | 三星/SK hynix 存储、FMS | ✅ A 级，韩国一手报道命中率高 |
| SK hynix 新闻室 | https://news.skhynix.com | HBM/HBF 官方公告 | ✅ A 级，官方信源首选 |
| Samsung Semiconductor | https://semiconductor.samsung.com | zHBM/V-NAND 官方新闻 | ✅ A 级，注意用此域名（父域 samsung.com 匹配），**勿用** news.samsung.com 之外的镜像站 |

### AIHOT 聚合 API（首个新增数据源，v5.7 接入）— Tier-4 线索源（B 级）

> **定位**：AIHOT（https://aihot.virxact.com）提供中文 AI 资讯聚合 API，**匿名只读、无需 API Key、无需 MCP server**（Skill 1.4.1，MIT License）。对芯片日报的价值 = **线索发现 + 热点捕捉 + 漏检补充**：用关键词查出候选新闻后，按 `links.original` 追溯第三方原文（或换 A 级中文源承载）。aihot.virxact.com 不在 A 级白名单 → 直接引用判 B 级，**不可作为唯一来源**。
> **安装**：已安装至用户级 `~/.workbuddy/skills/aihot`（SKILL.md + references/，SHA-256 已对照官方 manifest 校验通过）。
> **许可边界**：个人非商业/公益非商业/组织内部使用免费；面向外部的商业产品、数据转售、公开镜像、批量再分发须事先取得书面授权。日报引用时链接第三方原文，不批量镜像。

| 端点 | 参数示例（已验证） | 命中内容（2026-08-09 实测） |
|------|------------------|----------------------------|
| 资讯/搜索 | `GET /api/v1/items?mode=all&window=7d&q=半导体&limit=8` | SK hynix 龙仁/清州 54 万亿韩元投资、Anthropic 自研芯片、阿里达摩院 15 项芯片课题 |
| 资讯/搜索 | `GET /api/v1/items?mode=all&window=7d&q=英伟达&limit=8` | 美审查中国公司获取英伟达芯片、英伟达投 Lancium 30 亿美元、**HBM 短缺致 Rubin Ultra 降配** |
| 资讯/搜索 | `GET /api/v1/items?mode=all&window=7d&q=存储&limit=8` | 三星/SK/美光 2027 存储产能售罄给 AI 公司 |
| 热点榜 | `GET /api/v1/hot-topics` | 当前最热 Top10（rank 排序，含站内 story 事件页链接） |
| 日报 | `GET /api/v1/dailies/latest` 或 `GET /api/v1/dailies/{YYYY-MM-DD}` | AIHOT 编辑成品日报（lead/sections/flashes） |
| 分类 | `GET /api/v1/items?mode=selected&category=industry&window=7d` | 行业分类资讯 |

**使用纪律（沿用 Skill 规则）**：
1. **中文关键词必须 URL 编码**（`urllib.parse.urlencode`），否则 400。
2. **精选池（mode=selected）关键词空集时 → 用相同参数再查 mode=all**，并注明"未进入精选"（冷门公司常只在全量池）。两次都空才回答未找到。
3. 时间窗只支持 `24h` / `7d`；超过 7 天不承诺。`publishedAt` 为空时用 `discoveredAt` 并标注"AIHOT 收录时间"。
4. 日报引用：标题默认链 `links.aihot`（中文阅读页），出处核对 `links.original`；**重要数字/政策引用回第三方原文核对**。
5. 只做线索：最终日报每条仍须有 A/B 级来源链接（AIHOT 链接本身判 B 级），A 级占比 ≥30% 纪律不变。

### RSS 免 key 真实源（迭代2 新增，2026-08-09 实测 4 源全通；迭代3 扩至 6 源，2026-08-15）

> **定位**：`scripts/multi_source/collector.py` online 模式已接入 **6 个免 key 真实采集源**（SEC EDGAR + AIHOT + SemiEngineering + EE Times + CNBC + SemiAnalysis），单次采集 60-90 条。每日生成前先跑 `collector.collect(mode='online')` 做真实多源快照，再经 `gate.py` 选择性纳入（G1 置信度 / G2 时效 / G4 环节配额 / G5 主题关键词）得到日报候选池，作为 Step 2 检索之外的机器采集补充（漏检补充 + 交叉验证素材）。

| 源 | 端点（已验证 200） | 层级 | 白名单 | 单次产量 | 备注 |
|----|-------------------|------|--------|---------|------|
| SEC EDGAR | `browse-edgar?action=getcompany&type=8-K&output=atom` | Tier-2 | ✅ A 级 | ~10 条 | 8-K 备案条目，一手监管文件 |
| AIHOT | `/api/v1/items?mode=all&window=7d&q=<URL编码>&limit=N` | Tier-4 | ⚠️ B 级 | ~14 条 | 中文聚合线索，按 `links.original` 追溯原文 |
| Semiconductor Engineering | `https://semiengineering.com/feed/` | Tier-1 | ✅ A 级 | ~10 条 | RSS 2.0，EDA/材料/设计深度技术稿 |
| EE Times | `https://www.eetimes.com/feed/` | Tier-1 | ⚠️ B 级（未注册白名单） | ~10 条 | 英文权威行业媒体，设计/EDA 为主 |
| CNBC Tech（迭代3） | `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001054` | Tier-1 | ⚠️ B 级 | ~30 条 | 英文权威财经，设计/综合；含大量非芯片主题，靠 gate G5 过滤 |
| SemiAnalysis（迭代3） | `https://semianalysis.com/feed/` | Tier-1 | ✅ A 级 | ~10 条 | 全球行业风向标深度分析；付费墙文章仅标题作线索 |

**调用**：`python -c "import sys; sys.path.insert(0,'scripts/multi_source'); import collector; [print(i.source_id, i.title) for i in collector.collect(mode='online')]"`（断网自动降级离线样例，不阻塞）。

**门禁调用**：`python scripts/multi_source/gate.py`（读 `data/fused_events.json` → 写 `state/gate_report.json`）。端到端（2026-08-15 实测）：86 条原始 → 候选 7 条 / 拒 79 条（low_confidence 60 + irrelevant 19），候选池全部为芯片/AI/EDA 主题。

### 踩坑记录（已实证，避免重蹈）

1. **hani.co.kr（韩民族日报）、briefasia.com、ajupress.com、amd.com 均不在 A 级白名单** → 脚本判 B 级。三星新闻必须用 `semiconductor.samsung.com`，韩国报道优先 `chosun.com`，否则 A 级占比会跌破 30%。
2. **AMD 官方新闻**（amd.com）判 B 级 → 用财联社等 A 级中文源承载，或标注多源。
3. **时效基准 = 系统当日日期**：生成日报前先确认系统日期，超 72h 的新闻（如周五生成、本周一/二新闻）必须标 `[回顾]`，校验脚本会按日期差硬查。
4. **催化剂时点**：台积电月营收日固定每月 10 日（节假日顺延），TSMC 投资者日历有完整列表，直接引用即可；中芯国际 Q2 业绩说明会公告在巨潮/上交所，可搜"中芯国际 业绩说明会 预告公告"。
5. **DigiTimes 反爬不可自动化抓取**（迭代3 实测 2026-08-15）：`/rss/news.xml` HTTP 200 但内容是 HTML 反爬壳，`/rss/` 403 Forbidden，**未接入在线采集器**。台系产能信号继续用 `site:digitimes.com` WebSearch 兜底（实战命中率高），白名单域名 digitimes.com 保留不浪费 A 级名额。
6. **RSS 实体容错**（迭代3 修复 2026-08-15）：部分 feed（如 SemiEngineering/SemiAnalysis）含裸 `&` 或未定义 HTML 实体（`&nbsp;`），XML 解析会 not well-formed / undefined entity。collector 已做预处理（裸 `&` → `&amp;` + html5 实体注册进 XMLParser.entity）。
7. **health_check CLI 直跑只探 2 源**（迭代3 修复 2026-08-15）：`python scripts/multi_source/health_check.py` 时模块为 `__main__`，`from . import collector` 相对导入失败，旧实现静默走 fallback 只探 SEC EDGAR + AIHOT。已改双路径导入（相对 → 绝对），自动化场景可探到全部 6 源。
8. **gate 关键词短英文词必须词边界匹配**（迭代3 修复 2026-08-15）：`INCLUDE_KW` 里 "ai"、"sic" 等 ≤4 字符英文词做子串匹配会误命中 "again"、"basic" 等单词，导致 CNBC 跑车新闻混入候选池。已改 `_kw_in()` 词边界匹配（ASCII 短词 `(?<![a-z0-9])kw(?![a-z0-9])`）。

---

## 自主源发现层（2026-09-25 接入）

> **作用**：打破「人工供源」信息茧房——`scripts/multi_source/discover.py` 让系统自己 发现→验证→纳入 新数据源，状态落 `state/discovered_sources.json`；已验证（trial/active）源由 collector online 采集动态纳入（`dynamic_rss_collectors()`，一律 tier=4 线索级，过 gate G3 打 single_low_tier 降级线）。
> **⚠ 白名单纪律**：**采集层新源不自动进 A 级白名单**——发现层只解决「能不能抓」，引用分级仍按本文件「来源级别判定规则」与 `rules/rule_registry.yaml` 白名单执行；零人工审核的自动源引用时按线索（B 级以下）处理，人工核实定级后方可录入注册表升级。

### 发现引擎（3 个，fail-soft，单引擎失败跳过）

| 引擎 | 做法 | 备注 |
|------|------|------|
| gnews_domains（Google News RSS 中英） | zh `(半导体 OR 芯片 OR 晶圆厂) when:7d` / en `(semiconductor OR chip OR wafer fab) when:7d`（full 模式追加先进封装/出口管制、TSMC/Samsung/SK hynix、HBM/chiplet、硬件垂类共 3 组），从条目 `<source url="出版方域名">` 直接提取域名计频 | 万能发现源：无需解重定向链；相邻 query 间隔 ≥2s |
| opml_candidates（OPML 种子） | 公开 OPML 订阅清单（awesome-rss-feeds-list / tidings-rss）按文档序采样 xmlUrl 上限 60 条，作候选域的 feed 提示 | 仅 `--mode full` 启用 |
| newsnow_domains（newsnow 热榜） | 热榜 3 个 id（cls-hot / wallstreetcn-hot / gelonghui）的 items[].url 提取域名，no_proxy 直连 | 仅 `--mode full` 启用 |

### 本轮内置新增源（collector.py，2026-09-25 实测可活，随 v7 一并接入）

| 源 | 端点（已验证） | tier | 备注 |
|----|--------------|------|------|
| IEEE Spectrum | `https://spectrum.ieee.org/feeds/topic/semiconductors.rss` | 1 | 半导体专题，英文权威 |
| Tom's Hardware | `https://www.tomshardware.com/feeds/all` | 1 | 设计/消费硬件环节 |
| Nikkei Asia | `https://asia.nikkei.com/rss/feed/nar` | 1 | **RDF/RSS1.0 格式，日期在 dc:date 命名空间**（collector/discover 均已按本地名兼容） |
| Korea Herald | `https://www.koreaherald.com/rss/allCh.xml` | 1 | 韩媒英文，存储/韩厂视角 |
| Yonhap EN | `https://en.yna.co.kr/RSS/news.xml` | 1 | 韩联社英文，通讯社口径 |
| Yahoo Finance | `https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US`（TSM 同形换 `s=`） | 3 | 个股新闻，仅标的命中芯片词才相关，线索级 |
| 巨潮资讯 GET 全文搜索 | `GET https://www.cninfo.com.cn/new/fulltextSearch/full?searchkey=芯片&pageNum=1` | 3 | type=filing 公告；**响应 GBK**（容错解码）；**必须绕系统代理直连**；announcementTime 为毫秒时间戳；PDF 链拼 `https://static.cninfo.com.cn/` 前缀；标题含 `<em>` 高亮需清洗 |
| newsnow 热榜 | `GET https://newsnow.busiyi.world/api/s?id=<id>`（cls-hot / wallstreetcn-hot / gelonghui） | 4 | 线索级；先直连、失败走系统代理重试一次 |

> 同批还接入 Google News 线索 collector（`https://news.google.com/rss/search?q=…&ceid=…`，tier=4）：条目出版方域名存 `raw_payload.publisher_domain`（管线暂无消费点，发现层计频由 discover 独立提取）；发现层专用探测无静态白名单，防线 = https-only + 解析 IP 拒私网/回环 + 重定向逐跳校验 + 响应体上限 + 每域礼貌间隔 ≥0.8s。

### 生命周期规则（抄 Miniflux 设计）

- **状态机**：`candidate --探测通过--> trial --连续 2 次通过--> active`；frozen 重探通过 → 复活回 trial。探测四道门：feed 自动发现（首页 `<link rel="alternate">` → `/feed/` `/rss` 等路径清单兜底）→ 合法性（HTML 反爬壳/非 feed/无条目拒绝）→ 新鲜度（最新条目 90 天内）→ 相关性（三条件缺一不可：不同芯片关键词命中 ≥3 且有命中条目 ≥2 且**命中条目占比 ≥30%**——密度线防全站消防水管 feed 靠绝对数刷过，0.30 依据 2026-09-26 实测谱：真垂类 0.35-0.5，芯片强相关综合站 0.3，businesskorea 类全站混排仅 0.25）。英文关键词按词边界匹配（chiptune 不命中 chip），中文按子串；国产链/政策词已补齐（台积电/中芯国际/北方华创/实体清单/大基金/靶材/载板等）。
- **门禁升级复判**：`--mode rescore` 用当前门禁对全池 trial/active 复判，确定性不达标降回 candidate（计数归零），瞬时失败不动——每次升级相关性门禁后跑一次，池子即被新门禁清洗，无需等待自然退避。
- **确定性失败**（html_shell / not_a_feed / no_entries / low_relevance / stale_feed）：error_count+1，指数退避 `30min×2^n` **封顶 7 天**；**连续 3 败 → frozen 冻结**（池保留不删除，到期重探通过即翻案）。
- **瞬时失败**（fetch_failed / probe_error：断网/超时/WAF 抖动）：单独计数，退避封顶 24h，**不冻结、不改变 state**——断网一个下午不冻死全池。
- 探测通过后 12h 复查；状态文件原子写回（先写 .tmp 再 os.replace）。

### 运行命令

```bash
python scripts/multi_source/discover.py --mode quick    # 每日生成前：gnews 2 组 query + 新域探测上限 8
python scripts/multi_source/discover.py --mode full     # 每周一：全引擎（+OPML +newsnow）+ 新域上限 18
python scripts/multi_source/discover.py --mode status   # 只打印现有状态表，不联网
```

结尾固定打印 `[discover] SUMMARY net_new=X validated=Y promoted=A state_total=T known_domains=K`（供门禁 grep）；任何异常 fail-soft，进程 exit 0。

### 实测黑名单（2026-09-25 调研，勿再接入，省探测预算）

| 源 | 死因 |
|----|------|
| TrendForce RSS | 404 |
| The Elec | 403 / 502 |
| AnandTech | 已关站；HTTP 200 + HTML 反爬壳陷阱（200 ≠ 活 feed 的教训，探测须验内容形态） |
| 36kr `/feed` | 实测不可用（黑名单清单在列，未注明具体错误码） |
| 虎嗅 `/rss/0.xml` | 实测不可用（同上） |
| Bing News RSS | 仅返回 12 条，池太小 |
| RSSHub / DailyHotApi / 60s API 公共实例 | 均被 Cloudflare 拦截 |
