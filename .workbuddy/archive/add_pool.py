#!/usr/bin/env python3
# 追加「信号来源分层（扩展池）」到 references/sources.md 末尾（不破坏自动生成区）。
import io, os

path = r"D:/创建skill/skills/chip-daily-report/references/sources.md"
with io.open(path, encoding="utf-8") as f:
    content = f.read()

APPEND = """

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
"""

if APPEND.strip() in content:
    print("already present, skip")
else:
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(content.rstrip() + "\n" + APPEND)
    print("appended. new size =", os.path.getsize(path))
