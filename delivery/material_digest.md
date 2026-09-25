# AICoding 架构设计 · 资料摘要

> 本文档做一件事：**精读主理人转交的全部原始资料，逐份、逐章节做出摘要**——后面任何人拿到这份摘要，都能通过章节号快速定位回原始文件的对应位置。

> 上游输入：主理人转交的全部原始资料（本次为 chip-daily-report skill 仓库的 md / py / yaml / 目录镜像）；
> 产出者：`knowledge-ingest-engineer`（知识摄入工程师 - 闻资料），经 G1 校验与人工审核通过后交付。

---

## 0. 元信息

```yaml
标题: chip-daily-report（芯片行业日报生成器 v5.0） - 资料摘要 v1.0
版本: v1.0
状态: Ready-for-Review
创建日期: 2026-08-07
整理人: knowledge-ingest-engineer（知识摄入工程师 - 闻资料）
审核人:
  - team-lead（AICoding 架构专家团主理人）

原始资料清单:
  - D:\创建skill\skills\chip-daily-report\SKILL.md: skill 主控文件，含设计哲学、6 步生成流程、输出格式模板、失败处理、边界与 18 条反例黑名单
  - D:\创建skill\skills\chip-daily-report\CLAUDE.md: 项目说明卡，含定位、运行方式、技术栈、目录约定、9 条核心约束与当前版本状态
  - D:\创建skill\skills\chip-daily-report\references\sources.md: A/B/C 三级动态源库，含国际/国内/学术权威源清单、来源级别判定规则与三类搜索关键词模板
  - D:\创建skill\skills\chip-daily-report\references\classification.md: 产业链 5 环节分类判定规则，含正反例、学术突破分类、不纳入清单与存疑仲裁表
  - D:\创建skill\skills\chip-daily-report\references\rubric.md: 15 项门禁检查清单，含逐项通过标准、PASS/FAIL 示例、自检结果输出格式与门禁规则
  - D:\创建skill\skills\chip-daily-report\scripts\validate_report.py: Python 3 硬约束校验脚本，含 A/C 级域名硬编码清单与 15 项校验函数，退出码 0/1
  - D:\创建skill\skills\chip-daily-report\scripts\__init__.py: scripts 包入口，导出 validate_report 并声明 __version__ = '5.0.0'
  - D:\创建skill\skills\chip-daily-report\agents\openai.yaml: Agent 行为配置，含工具权限、搜索策略、来源约束、输出约束、质量门禁与模块加载时机
  - D:\创建skill\skills\chip-daily-report\芯片行业日报_20260720.md: 样例产物 1，11 条新闻，13 项自检表（v4.0 风格，无技术注解/无产业链关联）
  - D:\创建skill\skills\chip-daily-report\芯片行业日报_20260722.md: 样例产物 2，9 条新闻，13 项自检表（v4.0 风格）
  - D:\创建skill\skills\chip-daily-report\芯片行业日报_20260727.md: 样例产物 3，22 条新闻，15 项自检表（v5.0 完整版，含技术注解与产业链关联）
  - D:\创建skill\skills\chip-daily-report\.trae\skills\chip-daily-report\: TRAE 安装镜像目录，8 个文件中 7 个与主目录逐字节一致、validate_report.py 的 A_LEVEL_DOMAINS 清单不一致
```

| 版本 | 日期 | 作者 | 变更内容 |
| --- | --- | --- | --- |
| v1.0 | 2026-08-07 | `knowledge-ingest-engineer` | 初稿：完成 D1~D12 全量精读、逐章摘要、交叉比对与 16 项冲突记录 |

---

## 1. 资料清单

> 列出全部原始资料，每份标注解析状态。解析失败或跳过的必须注明原因。

| 编号 | 文件名 | 类型 | 来源 | 解析状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| D1 | `SKILL.md` | md | 主理人转交（项目根目录） | 已解析 | 268 行，全文读取，无编码/截断问题 |
| D2 | `CLAUDE.md` | md | 主理人转交（项目根目录） | 已解析 | 39 行，全文读取 |
| D3 | `references/sources.md` | md | 主理人转交（references 目录） | 已解析 | 176 行，全文读取 |
| D4 | `references/classification.md` | md | 主理人转交（references 目录） | 已解析 | 215 行，全文读取 |
| D5 | `references/rubric.md` | md | 主理人转交（references 目录） | 已解析 | 353 行，全文读取 |
| D6 | `scripts/validate_report.py` | py | 主理人转交（scripts 目录） | 已解析 | 768 行，全文读取；未执行脚本（本阶段仅做静态阅读，不产出运行结论） |
| D7 | `scripts/__init__.py` | py | 主理人转交（scripts 目录） | 已解析 | 18 行，全文读取 |
| D8 | `agents/openai.yaml` | yaml | 主理人转交（agents 目录） | 已解析 | 99 行，全文读取 |
| D9 | `芯片行业日报_20260720.md` | md | 主理人转交（项目根目录，历史产物） | 已解析 | 70 行，全文读取 |
| D10 | `芯片行业日报_20260722.md` | md | 主理人转交（项目根目录，历史产物） | 已解析 | 66 行，全文读取 |
| D11 | `芯片行业日报_20260727.md` | md | 主理人转交（项目根目录，历史产物） | 已解析 | 134 行，全文读取 |
| D12 | `.trae/skills/chip-daily-report/`（镜像目录，8 文件） | dir | 主理人转交（TRAE 安装镜像） | 已解析 | 目录树 + 逐文件 `diff` 比对完成；`scripts/__pycache__/` 为编译缓存，**已跳过**——原因：非人工维护的源文件，无独立事实价值 |

**类型枚举**：`md` / `py` / `yaml` / `dir`

> 说明：模板默认列出的 `docx` / `pdf` / `pptx` / `xlsx` 四类办公文档在本次资料包中**均未出现**；本项目原始资料全部为代码仓库内的文本文件与目录，故类型枚举按实际扩展名如实登记。

**解析状态汇总**：已解析 12 / 12（100%）；解析失败 0；待补充 0；跳过 1 项子路径（D12 下的 `scripts/__pycache__/` 编译缓存，原因已注明）。

---

## 2. 资料内容摘要

> 逐份文档按自身章节结构做摘要。每条摘要标注章节号（`D编号，§章节`），后面任何人想核实某个点，直接定位回原文对应位置即可。

### D1：`SKILL.md`

> chip-daily-report skill 的主控文件，定义"什么是合格的芯片行业日报"以及"如何 6 步生成它"，是整个模块化系统的唯一入口 — 来源：项目根目录，v5.0 专业深度版

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D1，§YAML frontmatter | `name: chip-daily-report`；description 声明触发词 8 个（芯片日报 / 半导体新闻汇总 / chip industry daily report / 芯片行业动态 / 半导体产业链 / 芯片资讯 / 集成电路新闻 / semiconductor daily news），覆盖设计、制造、封测、EDA、材料、设备全产业链 | L1–L5 |
| D1，§标题与类型 | 自我标注为"类型 P4：产物生成型 · v5.0 专业深度版（微电子视角+技术解读+产业链关联）" | L7–L9 |
| D1，§设计哲学 | 7 条原则：①信源优先（可追溯至原始来源，拒绝未标注出处的二次转载）；②产业链完整性（宁可标"暂无动态"也不省略环节）；③时效性优先（默认最近一个工作日，超 72 小时标"回顾"）；④事实与技术分离（技术解读走 `[技术注解]` 标签，不是投资建议）；⑤来源分级（**基于 URL 域名判定，不依赖 display text**）；⑥执行闭环（Rubric 是门禁，校验脚本是硬约束）；⑦微电子专业视角（每条含技术节点/工艺/器件维度） | L11–L19 |
| D1，§文件结构 | 声明本 skill 是模块化系统而非单一文档，5 个文件各司其职：`SKILL.md`（始终加载）、`references/sources.md`（Step 2 加载）、`references/classification.md`（Step 3 加载）、`references/rubric.md`（Step 5 加载）、`scripts/validate_report.py`（Step 5 自检后运行）；关键说明"按需加载以降低注意力负担" | L23–L33 |
| D1，§生成流程 · 总述 | 6 步高效流程；标注 v3.2→v4.0 变更为"10 步→6 步，合并时效标注/去重/排序到搜索阶段，来源分级即时判定，目标单次通过门禁" | L35–L37 |
| D1，§生成流程 · Step 1 确认范围 | 耗时 5 秒；询问/确认日期范围（默认最近一个工作日）和关注领域；**非交互模式（定时任务）使用默认值，不等待用户输入**；输出 `[日期范围]`+`[关注领域]`+`[生成时间]`（作为 72 小时计算基准） | L39–L42 |
| D1，§生成流程 · Step 2 搜索+分级+筛选 | 耗时约 4 分钟；【强制】先读取 `references/sources.md`；v5.0 三层搜索：第一层 A 级 `site:` 限定搜索（确保 A 级 ≥30%）、第二层按 5 环节产业新闻搜索（每环节至少 1 中 + 1 英）、第三层技术突破搜索（ISSCC 2026 / VLSI Symposium 2026 / DAC 2026 / IEDM 2026 / chip breakthrough）；即时判定来源级别（只看 URL 域名）、即时去重（同事件多来源合并并标多链接）、即时时效标注（>3 天标 `[回顾]`）；A 级 低于30% 立即补搜；**目标 15-20 条候选**（v4.0 为 9-10 条） | L44–L57 |
| D1，§生成流程 · Step 3 分类+摘要+技术注解 | 耗时约 3 分钟；【强制】先读取 `references/classification.md`；摘要五要素 = 主体+事件+数据+影响+**技术维度**；**摘要长度 80-150 字（v4.0 为 50-100 字），3-5 句**；紧接着写"**句数控制：3-4 句 PASS，5 句 WARN，≥6 句 FAIL**"；`[技术注解: xxx]` 仅对非直观术语添加（GAA / HBM4 / CoWoS / NPO / Chiplet 等），内容为 1-2 句原理简述；软件平台/SaaS/市场分析不纳入；环节内排序 = 影响范围 > 技术突破 > 市场规模 > 企业动态；**目标 15-20 条（每环节 3-4 条）** | L59–L73 |
| D1，§生成流程 · Step 4 组装日报 | 耗时约 2 分钟；组装时一次性检查 10 项易错项（头部元信息/今日要点/5 环节标题全出现/[回顾] 标签/摘要 3-5 句含技术维度/技术注解/产业链关联小节/来源分级统计与实际 URL 域名一致/无附录越界/尾部免责声明+`---` 分隔线）；**产业链关联为 v5.0 新增**，置于自检结果前，选 2-3 组上下游关联事件，示例为"台积电涨价(制造) → AI芯片设计公司BOM成本上升(设计) → 先进封装需求可能受影响(封测)" | L75–L91 |
| D1，§生成流程 · Step 5 Rubric自检+脚本校验 | 耗时约 30 秒；【强制】先读取 `references/rubric.md`；逐项检查 15 项并**显式输出自检结果表格**；【强制】运行 `scripts/validate_report.py` 硬校验；有 FAIL 则按映射表修正→重新组装→再次校验，目标单次通过 | L93–L98 |
| D1，§生成流程 · Step 6 保存+同步 | 耗时约 5 秒；保存到工作目录，命名 `芯片行业日报_YYYYMMDD.md`；输出完成确认 | L100–L102 |
| D1，§v3.2→v4.0 合并对照表 | 10 行对照，说明旧 Step 2/3 合并入新 Step 2（分级+补搜即时化）、旧 Step 4/5/8 合并入新 Step 3（分类+摘要+排序同上下文）、旧 Step 6/7 前置到 Step 2（时效标注、去重）、旧 Step 9 → Step 4（加防抖清单）、旧 Step 10 → Step 5、新增 Step 6 保存步 | L104–L118 |
| D1，§Rubric-Step 映射表 | 15 行，规定每项 Rubric 失败时回到哪个 Step 修正：#1→Step4、#2→Step2、#3→Step2、**#4 摘要规范→Step 3（重新压缩摘要）**、#5→Step2、#6→Step2、#7→Step3、#8→Step2、#9→Step4、#10→Step4、#11→Step3、#12→Step4、#13→Step2（site: 限定搜索）、#14→Step3、#15→Step4 | L120–L138 |
| D1，§输出格式 | 给出完整 markdown 模板：一级标题 `# 芯片行业日报 — [日期]`；blockquote 三行元信息（`> 生成时间: [年-月-日 HH:MM]` / `> 覆盖范围:` / `> 新闻总数: [N]条`）；`## 今日要点`；5 个环节标题写作 **`## 设计` / `## 制造` / `## 封测` / `## EDA / 工具` / `## 材料 / 设备`**；可选 `## 综合 / 其他`（仅当有分类存疑新闻）；`## 产业链关联`；`## 自检结果`（15 行表格）；**来源分级统计置于自检结果小节内**；`---` + 免责声明 | L140–L198 |
| D1，§格式说明 | 12 条补充：头部必含 3 项元信息；今日要点 1-3 条；无新闻环节标"今日暂无重要动态"；每条摘要 80-150 字、3-5 句、必含技术维度；术语加 `[技术注解]`；多来源合并标多链接；`## 产业链关联` 必须出现；尾部必附自检结果（15 项 PASS/FAIL + 来源分级统计）；来源分级基于 URL 域名；最末免责声明；**"产业链关联"是正文组成部分不是附录** | L200–L211 |
| D1，§失败处理 | 17 行兜底表。要点：链接失效→标"链接待验证"保留标题摘要；无法确认时间→标"日期待确认"；无新闻环节→标"今日暂无重要动态"；搜索无结果→切备用引擎重试一次；**摘要过长（>150 字或 ≥7 句）→"回到 Step 5 重新压缩"，兜底保留原文前 3 句**；信息冲突→标注各方说法不做主观判断；非公开信息→自动跳过；`sources.md` 不存在→回退公开新闻源（SEMI/TechInsights/TSMC）；分类存疑→按 classification.md 仲裁，兜底归"综合/其他"；A 级 低于30%→补搜，兜底标"今日权威源不足"；**Rubric 循环超 5 次→保留最后一次结果并标注 FAIL 项**；未来日期→标"日期异常"；0 条新闻（节假日）→全环节标暂无，来源质量自动 PASS；负面新闻/安全事故→如实记录不隐瞒；争议事件→标"信息存在分歧"；未验证独家爆料→标"待验证"，除非有第二独立来源 | L213–L233 |
| D1，§边界 | 9 条：只汇总公开可访问来源、不引付费墙；**不做投资建议/市场预测，但允许技术解读**；**不做技术分析/深度评测，但允许技术注解**；不按股价/市值排序，按影响范围>技术突破>市场规模>企业动态；时间戳以来源页发布时间为准，**72 小时判定基于日期差（天数差 >3 标 [回顾]）**；不引社交媒体传言；不翻译外文标题（非英文可附中文译名标"译"）；产业链关联是事实传导逻辑不是投资建议；**不设"市场动态"等附录** | L235–L245 |
| D1，§反例黑名单 | 18 行"不要做/为什么/应该做"三列表。除常规项外，#12 明确"**SKILL.md 与配套文件（sources/classification/rubric/scripts）不一致**"为反例，理由是"模块化架构下文件间引用失效，LLM 加载到过时规则"，应对为"修改任何规则时同步更新所有相关文件"；#13 禁止依据 display text 判级（可注入 A 级关键词绕过 30% 门禁）；#14 禁止把【强制】加载变为可选；#15 禁止摘要缺技术维度；#16 禁止条数不足（少于10条）；#17 禁止完全不加技术注解；#18 禁止省略产业链关联小节 | L247–L268 |

### D2：`CLAUDE.md`

> 项目说明卡，用最短篇幅交代 chip-daily-report 是什么、怎么跑、技术栈、目录约定、核心约束与当前状态 — 来源：项目根目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D2，§定位 | 自我定位为"生成带来源与时间戳的芯片行业日报的 **TRAE skill**"，覆盖设计/制造/封测/EDA/材料设备全产业链，面向微电子/IC 专业读者，提供技术注解和产业链关联分析 | L3–L4 |
| D2，§怎么跑 | 生成：用触发词（"芯片日报"/"chip industry daily report"）启动 6 步流程；校验：`python scripts/validate_report.py 日报文件路径参数`，**退出码 0=通过，1=有未通过项**；明确"校验脚本是硬约束：日报必须通过 15/15 项检查才能输出" | L6–L9 |
| D2，§技术栈 | 三项：Markdown（SKILL.md 主控 + references/ 知识库 + 日报产物）、**Python 3（validate_report.py，无第三方依赖）**、YAML（agents/openai.yaml Agent 行为配置） | L11–L14 |
| D2，§目录与约定 | 7 条：`SKILL.md` 始终加载；`references/sources.md` Step 2 加载；`references/classification.md` Step 3 加载；`references/rubric.md` Step 5 加载；`scripts/validate_report.py` Step 5 运行；**`.trae/skills/chip-daily-report/` 为 TRAE 安装镜像，"必须与根目录同步"**；产物命名 `芯片行业日报_YYYYMMDD.md` | L16–L23 |
| D2，§核心约束 | 9 条：来源级别基于 URL 域名不依赖 display text（**注明目的是防注入攻击**）；A 级占比 ≥30%、C 级禁止；**摘要 3-5 句（80-150 字）含技术维度，≥7 句 FAIL**；术语必加 `[技术注解: xxx]`；必须含 `## 产业链关联`（≥2 组）；超 72 小时标 [回顾]；无附录越界；自检结果必须显式列出 15 项 PASS/FAIL | L25–L33 |
| D2，§当前状态 | 3 条：版本 v5.0 专业深度版；"**对抗审查 35 个漏洞已全部修复，脚本覆盖 15/15 项 Rubric**"；"**.trae 镜像需同步至 v5.0**" | L35–L38 |

### D3：`references/sources.md`

> A/B/C 三级动态源库 + 未列入来源的级别判定规则 + 三类搜索关键词模板，Step 2 搜索时加载 — 来源：references 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D3，§头部元信息 | 最后更新 2026-07-23；版本 v5.0（新增学术会议源+技术突破搜索模板）；维护规则"每月核查源可用性，发现失效源及时标注或替换" | L1–L5 |
| D3，§使用规则 | 5 条：A 级优先（占比 ≥30%）；B 级需追溯原始来源并标注（示例"今日头条转载自财联社"）；**C 级一律不使用，发现即丢弃**；双语搜索（每环节 ≥1 中 +1 英）；标注"已停更"的源仅用于历史背景 | L7–L13 |
| D3，§A级来源 · 国际权威源 | 11 个：TSMC 官方（tsmc.com/investorRelations，制造）、**Samsung Newsroom（news.samsung.com/global，设计/制造/封测）**、SK hynix（news.skhynix.com）、Intel Newsroom（intel.com）、NVIDIA Newsroom（nvidianews.nvidia.com）、SEMI（semi.org）、TechInsights、SemiAnalysis、EDN、Semiconductor Engineering、EET-China | L19–L33 |
| D3，§A级来源 · 国内权威源 | 11 个：中国新闻网（chinanews.com.cn）、财联社（cls.cn）、新华社（news.cn）、上海证券报（cnstock.com）、证券时报（stcn.com）、21 世纪经济报道（21jingji.com）、界面新闻（jiemian.com）、电子时报 DigiTimes（digitimes.com.tw）、Nikkei Asia（asia.nikkei.com）、SEMI 大半导体产业网（semi.org.cn）、巨潮资讯（cninfo.com.cn） | L35–L49 |
| D3，§A级来源 · 学术/期刊 | 7 个（用于技术突破类新闻）：IEEE Xplore（ieeexplore.ieee.org）、Engineering Reports（onlinelibrary.wiley.com）、**ISSCC（isscc.org）**、**VLSI Symposium（vlsisymposium.org）**、**DAC（dac.com）**、**IEDM（ieee-iedm.org）**、**Nature Electronics（nature.com/natelectron/）**，另重复列出 SEMI | L51–L62 |
| D3，§B级来源 | 8 个聚合/门户：今日头条（toutiao.com）、新浪财经（finance.sina.com.cn）、网易科技（tech.163.com）、搜狐科技（m.sohu.com）、东方财富网（eastmoney.com）、雪球（xueqiu.com）、快科技（mydrivers.com）、腾讯新闻（news.qq.com）；均备注"需追溯原始来源" | L64–L77 |
| D3，§C级来源 | 6 个禁止源：微博、Twitter/X、抖音/快手、知乎帖文、小红书、B 站；原因分别为"未经验证/无法验证真实性/用户生成内容" | L79–L90 |
| D3，§已停更/历史存档源 | 1 个：AnandTech（2024 年停站），"仅用于历史背景，不作主要来源" | L92–L96 |
| D3，§来源级别判定规则 | 8 行兜底规则表（未列入清单时）：厂商官方/行业组织/权威媒体的 `.com`→A；行业组织 `.org`→A；政府机构 `.gov`→A；上市公司公告（巨潮/交易所）→A；学术论文（IEEE/Nature 等）→A；聚合平台转载但标注原始来源→B（追溯到原始 A/B 级源）；个人博客/自媒体→C；社交媒体帖文→C | L98–L111 |
| D3，§搜索关键词模板 · A级限定搜索 | 核心策略"先搜 A 级域名站内新闻再补 B 级，一次性确保 A 级 ≥30%，避免事后回溯补搜"；中文 7 条（cls.cn / chinanews.com.cn / eet-china.com / 21jingji.com / jiemian.com / semi.org.cn / cninfo.com.cn）；英文 7 条（tsmc.com / **news.samsung.com** / semi.org / asia.nikkei.com / semianalysis.com / edn.com / semiengineering.com） | L115–L135 |
| D3，§搜索关键词模板 · 通用搜索 | 中英各 5 组，按环节给出关键词：设计（AI芯片 设计 发布 规格 性能 / chip design GPU AI semiconductor news）、制造（晶圆代工 制程 产能 HBM DRAM / foundry process node HBM wafer）、封测（先进封装 HBM封装 测试 封测厂 / advanced packaging HBM packaging test）、EDA（EDA工具 Synopsys Cadence 仿真 / EDA tools Synopsys Cadence simulation）、材料设备（半导体材料 光刻机 电子特气 光刻胶 / semiconductor materials lithography equipment） | L137–L151 |
| D3，§搜索关键词模板 · 技术突破搜索 | v5.0 新增。学术会议 5 组（ISSCC/VLSI/DAC/IEDM/Nature Electronics，均中英双语）；技术方向 6 组（晶体管结构 GAA/CFET、先进制程 2nm/1.4nm、先进封装 3D IC/Chiplet、存储 HBM4/存算一体、新材料 硅光/碳化硅/氮化镓、EDA 工具 AI 辅助设计）；学术源 `site:` 限定 3 条（ieeexplore.ieee.org / nature.com / semi.org） | L153–L176 |

### D4：`references/classification.md`

> 产业链 5 环节的分类判定规则，含每个环节的"包含/不包含/正例/反例"、学术突破分类指导、不纳入清单与存疑仲裁表，Step 3 分类时加载 — 来源：references 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D4，§头部元信息 | 最后更新 2026-07-23；版本 v5.0（新增学术突破分类指导）；使用场景 Step 3 分类判定时加载 | L1–L5 |
| D4，§分类原则 | "每个新闻必须按以下定义归入对应环节。**分类存疑时归入'综合/其他'，不要强行塞入不相关环节**" | L7–L9 |
| D4，§设计 | 包含：GPU/CPU/AI 芯片产品设计、芯片架构（3D/Chiplet/小芯片）、IP 授权（ARM）、规格发布（核心数/频率/带宽）、性能基准（MLPerf）。不包含：制造工艺、封装、EDA 工具本身。正例 3（壁仞 NPO 光互连+自研 BR2xx GPU、NVIDIA Blackwell 架构、海光 DCU 适配 GLM）；反例 3（台积电 3nm 量产→制造、SK 海力士 HBM4 封装工艺→封测、Synopsys 新版 EDA→EDA） | L11–L33 |
| D4，§制造 | 包含：晶圆代工（台积电/三星/中芯/晶合集成）、先进制程 2nm/3nm/5nm、成熟制程 28nm 及以上、产能扩缩、代工价格调整、HBM/DRAM/NAND 存储芯片制造、**晶圆厂动态（新建/投产/上市）**。不包含：设计、封测、制造设备。**正例含"晶合集成港交所上市，全球第九大晶圆代工"→制造**；反例 3（壁仞发布 GPU→设计、马来西亚 HBM4 封装→封测、ASML 光刻机交付→材料/设备） | L35–L60 |
| D4，§封测 | 包含：封装技术（先进/传统/3D/Chiplet）、测试方案、HBM 封装工艺（MR-MUF/混合键合/热压键合）、封测厂动态（长电/通富/日月光）、封装材料（若侧重封装工艺）。不包含：晶圆制造、裸片设计。正例 3（马来西亚 HBM4 先进封装、SK 海力士 MR-MUF 良率、KITECH 芯片堆叠新工艺）；**反例含"SK海力士HBM4量产"→不是封测是制造**；⚠️"台积电 CoWoS 产能扩充"默认归封测 | L62–L82 |
| D4，§EDA / 工具 | 包含：EDA 软件（Synopsys/Cadence/Siemens EDA）、设计自动化工具、IP 库、TCAD 仿真、验证工具、**AI 辅助芯片设计工具（如 Kimi K3 自主芯片设计）**。不包含：芯片产品本身、制造设备。正例 3（Kimi K3 冲击 Cadence/Synopsys、芯和半导体 XAI 平台、Synopsys 收购 Ansys）；反例 1 + ⚠️"台积电 CoWoS 设计工具"默认归 EDA | L84–L105 |
| D4，§材料 / 设备 | 包含：硅片/晶圆材料、特气（氟化氢/氢氟酸/电子级气体）、光刻胶、靶材、CMP 材料、光刻机（ASML/Nikon/Canon/国产）、刻蚀机、沉积设备、量测设备、**设备市场预测（如 SEMI 预测）**。不包含：芯片产品、软件工具。正例 3（滨化 6N 高纯氟化氢、SEMI 预测 1659 亿美元、ASML EUV 交付）；反例 2（阿里 AI 办公平台→不纳入、台积电 3nm 量产→制造） | L107–L132 |
| D4，§学术/技术突破分类指导 | v5.0 新增。原则："学术突破新闻按其**技术实质**归入对应产业链环节，**不单设'学术'环节**"。5 行映射表：芯片架构/电路设计创新→设计；制程/工艺技术突破→制造；封装/互连技术创新→封测；EDA 工具/设计方法学→EDA；新材料/器件结构→材料/设备。技术注解要求 3 点（解释原理、说明产业链位置、关联课堂知识）。正例 2（IEDM 2026 台积电 2nm GAA→制造；ISSCC 2026 NVIDIA Blackwell 论文→设计）；反例 3（直接搬运论文标题、注解写成摘要翻译、纯理论无产业前景） | L134–L166 |
| D4，§不纳入日报的内容 | 6 类一律不纳入（无论重要性）：软件平台/SaaS（阿里秒悟）；**市场指数/股价/财经分析（费城半导体指数、SK 海力士股价）**；AI 大模型发布/应用（Kimi K3 发布，除非侧重对 EDA 影响）；二手交易平台/消费应用；人形机器人/具身智能；AI 眼镜/可穿戴 | L168–L179 |
| D4，§边界判定规则 | 3 级优先级：核心是芯片本身→纳入对应环节；核心是终端产品/应用→不纳入；核心是市场/金融/政策→不纳入（除非 SEMI 等行业组织的市场预测）。4 条示例对比（华为 Atlas 950 用自研昇腾→纳入设计 vs Atlas 950 算力性能→不纳入；Kimi K3 冲击 EDA→纳入 EDA vs Kimi K3 参数 2.8 万亿→不纳入） | L181–L192 |
| D4，§存疑仲裁规则 | 3 级判定依据（标题与核心内容指向 > 主体企业主营业务 > 归"综合/其他"）+ 7 行常见存疑场景默认归属表：CoWoS/InFO/3D 封装产能扩充→封测；CoWoS 设计/仿真工具→EDA；**HBM 相关新闻（制造 vs 封测）→制造**（理由"HBM 本质是存储芯片制造，封装工艺细节才归封测"）；Chiplet 架构设计→设计；晶圆厂设备采购→材料/设备；**AI 芯片公司融资/上市→不纳入**（理由"金融事件，非技术动态"）；政策/补贴/关税→不纳入 | L194–L215 |

### D5：`references/rubric.md`

> 15 项门禁检查清单的详细判定标准，每项含通过标准 + 判定方法 + PASS/FAIL 示例，Step 5 自检时加载 — 来源：references 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D5，§头部元信息 | 最后更新 2026-07-23；版本 v5.0（新增 #14 技术注解、#15 产业链关联）；门禁规则"所有'必须'项不通过 → 修正 → 重新组装 → 再次自检，**最多 5 次循环**" | L1–L6 |
| D5，§1 产业链完整性 | 必须项。5 环节全部出现，无新闻标"今日暂无重要动态"。PASS 示例给出 `## 设计`/`## 制造`/`## 封测`/`## EDA / 工具`/`## 材料 / 设备` 五个标题写法；FAIL：缺"封测"标题、直接跳过环节 | L10–L30 |
| D5，§2 来源可追溯 | 必须项。每条新闻附**可点击** URL（markdown 链接格式）。FAIL：无链接、纯文本 URL 不可点击、链接指向社交媒体（C 级） | L32–L44 |
| D5，§3 时间戳准确 | 必须项。每条标注发布时间（至少到日期），无法确认标"日期待确认"。FAIL：无时间戳、只有"近日""最近"等模糊表述 | L46–L59 |
| D5，§4 摘要规范 | 必须项。**每条 3-5 句（约 80-150 字）**，含五要素（主体+事件+数据+影响+技术维度）；v5.0 变更注明"从 3-4 句/50-100 字放宽至 3-5 句/80-150 字"；判定方法：以中英文句末标点 `。！？.!?` 计句，**排除小数点**；**判定标准：3-5 句 PASS / 6 句 WARN / ≥7 句 FAIL / 1-2 句 FAIL**；技术维度四选一（制程节点、工艺技术、器件结构、材料规格）；PASS 示例为 4 句约 120 字的台积电 Q2 法说会摘要 | L61–L91 |
| D5，§5 时效性 | 必须项。超 72 小时在**标题前**标 `[回顾]`；判定以日报生成时间为基准计算差值。FAIL：7/16 新闻在 7/20 日报中未标、**所有新闻都标 [回顾]（误标）** | L93–L107 |
| D5，§6 信源可靠性 | 必须项。仅引公开可访问正式新闻源，C 级禁止；判定方法为对照 `references/sources.md` 的来源分级表。FAIL：微博/Twitter/抖音/知乎、付费墙不可访问 | L109–L124 |
| D5，§7 中立性 | 必须项。只汇总事实，不含评论、预测、投资建议或技术分析。FAIL 如："台积电前景一片光明，值得投资"、"AI 泡沫论可以歇歇了"、"预计 2027 年 HBM 价格将翻倍"（除非引用来源中他人预测并标注） | L126–L138 |
| D5，§8 去重 | 必须项。同一事件多来源合并为一条并标多个链接。FAIL：同事件两条独立条目、合并后丢失部分链接 | L140–L151 |
| D5，§9 元信息完整 | 必须项。头部含生成时间、覆盖范围、新闻总数。FAIL：缺任一项、**新闻总数与实际条目数不符** | L153–L168 |
| D5，§10 今日要点 | 必须项。精选 1-3 条，一句话概括。特殊情况：0 条新闻（节假日）标"今日为节假日/休息日，无重要动态"自动 PASS；仅 1 条新闻则 1 条 PASS。FAIL：无章节、超 3 条、为空（有新闻可选）、与正文不符 | L170–L191 |
| D5，§11 分类正确 | 必须项。对照 `references/classification.md`。FAIL 如：阿里 AI 办公平台塞入材料/设备、费城半导体指数塞入任何环节、HBM4 封装工艺塞入 EDA、台积电 3nm 塞入设计 | L193–L209 |
| D5，§12 无附录越界 | 必须项。不出现"市场与政策动态"等越界附录。FAIL：`## 市场与政策动态（附录）`、`## 市场动态`、任何含股价/指数/财经分析的附录 | L211–L228 |
| D5，§13 来源质量 | 必须项。A 级 ≥30%。5 步判定方法：提取 URL 域名 → 对照 `references/sources.md` 域名分级表 → **只看 URL 域名不看 display text（防注入）** → **A 级占比 = A 级条数 /（A 级+B 级条数）** → C 级不应出现。PASS 示例 3/5=60%。特殊情况：0 条新闻自动 PASS；0 条可分级来源（全无 URL）标 WARN 不自动 FAIL | L230–L257 |
| D5，§14 技术注解 | v5.0 新增，必须项。涉及非直观术语必须加 `[技术注解: xxx]`（1-2 句原理）；扫描 6 类术语（晶体管结构 GAA/FinFET/TFET、封装 CoWoS/InFO/MR-MUF/Chiplet/2.5D/3D IC、存储 HBM3E/HBM4/DRAM/NAND/LPDDR、制程 EUV/DUV/SADP/SAQP、材料 6N/电子特气/光刻胶/碳化硅/氮化镓、架构 NPU/TPU/存算一体/RISC-V）；**整体判定：全部涉术语新闻均有注解→PASS，任意一条遗漏→FAIL**；无术语新闻不计入 FAIL。FAIL：涉及 CoWoS/GAA 无注解、注解内容是投资建议 | L259–L285 |
| D5，§15 产业链关联 | v5.0 新增，必须项。必须含 `## 产业链关联` 小节，选 2-3 组上下游联动事件；3 步判定（章节存在 → ≥2 组 → 每组涉及 ≥2 环节）；**判定标准：章节存在+≥2 组+每组 ≥2 环节 PASS；章节缺失 FAIL；仅 1 组 WARN；只说企业名字不涉环节 FAIL**；PASS 示例给出"AI 芯片需求→先进封装产能"与"HBM4 量产→封装材料"两组 | L287–L313 |
| D5，§自检结果输出格式 | 给出必须输出的 15 行表格模板（`| # | 检查项 | 结果 | 说明 |`）及**来源分级统计三行格式**（A 级列出具体来源=X 条 / B 级=Y 条 / A 级占比 X/(X+Y)=Z% ≥30% ✓） | L315–L344 |
| D5，§门禁规则 | 5 条：任何"必须"项不通过→修正→重组→再自检；最多 5 次循环；**自检结果必须显式输出，不允许笼统声称"已自检通过"**；**必须运行 `scripts/validate_report.py`**；5 次循环后仍 FAIL 则保留最后一次结果并标注 FAIL 项及原因 | L346–L353 |

### D6：`scripts/validate_report.py`

> Python 3 硬约束校验脚本（无第三方依赖），CLI 入口 `python validate_report.py 日报文件路径参数`，自称覆盖 15/15 项 Rubric — 来源：scripts 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D6，§模块 docstring | 标题"芯片行业日报校验脚本（硬约束校验器）v5.0"；列出三批修复记录：v3.1 共 11 项（C-1 自检表格正则 `\d+`→`[#\d]+`、A-3 只检查 URL 域名防注入、C-2 兼容英文标点排除小数点、C-3 0 条新闻跳过 A 级占比、C-4 兼容 4 种 dash、C-6 C 级域名精确匹配防 x.com 误匹配 fox.com、C-7 今日要点数量检查、C-8 中立性检查、B-5 A 级占比分母改为 a+b、B-9 未来日期检测、C-9 编码 fallback、C-10 路径检查、E-1 内联投资建议检测）；v3.2 共 4 项（B-7、E-4、A-4、"脚本覆盖 13/13 项 Rubric"）；v5.0 共 4 项（R-1 句数放宽 3-5、R-2 新增 #14 技术注解、R-3 新增 #15 产业链关联、R-4 章节顺序加"产业链关联"，"脚本覆盖 15/15 项 Rubric"）；**退出码 0=全部通过，1=存在未通过项** | L1–L37 |
| D6，§配置区 · A_LEVEL_DOMAINS | **硬编码 A 级域名 33 个**，分 7 组注释：国际厂商官方（`tsmc.com`、**`samsung.com`**、`skhynix.com`、`news.skhynix.com`、`intel.com`、`nvidia.com`、`nvidianews.nvidia.com`）；行业组织/权威分析（`semi.org`、`semi.org.cn`、`techinsights.com`、`semianalysis.com`）；权威媒体（`edn.com`、`semiengineering.com`、`eet-china.com`）；国内权威（`chinanews.com.cn`、`cls.cn`、`news.cn`、`cnstock.com`、`stcn.com`、`cninfo.com.cn`、`21jingji.com`、`jiemian.com`、**`ce.cn`、`cet.com.cn`、`xinhuanet.com`、`people.com.cn`、`cctvl.com`、`chinadaily.com.cn`、`yicai.com`、`cena.com.cn`**）；台港权威（`digitimes.com`、`digitimes.com.tw`）；学术（`ieeexplore.ieee.org`、`onlinelibrary.wiley.com`）；国际财经（`asia.nikkei.com`、**`reuters.com`、`bloomberg.com`**）；国际媒体（**`chosun.com`、`koreatimes.co.kr`**） | L49–L71 |
| D6，§配置区 · C_LEVEL_DOMAINS | 9 个禁止域名（精确匹配）：`weibo.com`、`weibo.cn`、`twitter.com`、`x.com`、`douyin.com`、`kuaishou.com`、`zhihu.com`、`xiaohongshu.com`、`bilibili.com` | L73–L78 |
| D6，§配置区 · 其他常量 | `SEGMENTS = ['设计','制造','封测','EDA','材料']`（5 环节标题关键词）；`FORBIDDEN_APPENDICES` 6 项（市场与政策动态/市场动态/市场分析/股价分析/财经动态/投资建议）；`INVESTMENT_ADVICE_KEYWORDS` 19 个（建议买入/值得投资/前景光明/看涨/看跌/强烈推荐/买入评级/目标价/预测涨/预计下跌/股价有望/建议卖出/增持/减持/建议加仓/建议减仓/投资价值/上涨空间/下跌空间） | L80–L95 |
| D6，§工具函数 | `read_file`：路径存在性 + 是否文件 + 编码 fallback（utf-8→gbk→utf-16），失败 `sys.exit(1)`；`domain_matches`：`domain.lower().lstrip('www.')` 后判断 `domain == pattern or domain.endswith('.'+pattern)`；`extract_urls`：正则 `https?://([^\s/)]+)` 提取域名；`count_sentences`：先把 `(\d)\.(\d)` 替换为 `\1DOT 占位符\2` 再计 `[。！？.!?]`，无标点时按长度估算（>20 字记 2 句，否则 1 句） | L102–L149 |
| D6，§校验函数 · 提取类 | `extract_generation_time`：正则 `生成时间[:：]\s*(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2})?`（兼容全/半角冒号，时分可缺省为 00:00）；`extract_news_items`：正则 `^-\s+\*\*(.+?)\*\*\s+[—–\-]+\s+(.+?)(?:\s*\|\s*来源[:：]\s*(.+?))?(?:\s*\|\s*(.+))?$`，产出 title/summary/source/timestamp 四字段；`count_actual_news`：排除标题含"今日暂无"的条目 | L156–L206, L399–L401 |
| D6，§校验函数 · 检查 1–5 | ①`check_metadata` 三项正则（生成时间/覆盖范围/`新闻总数[:：]\s*(\d+)\s*条`）；②`check_segments` 对 SEGMENTS 逐个用 `^##\s+{seg}` 多行匹配（**前缀匹配，故 `## EDA / 工具` 与 `## EDA` 均可命中**）；③`check_source_links` 要求 `\[.+?\]\(https?://.+?\)`；④`check_summary_sentences` 判定 `3 ≤ sent_count ≤ 5` 为 ok；⑤`check_timeliness` 跳过"日期待确认"与无时间戳条目，差值小于0 判未来日期 FAIL、大于72h 要求标题含 `[回顾]`、≤72h 若含 `[回顾]` 判"误标[回顾]" | L169–L272 |
| D6，§校验函数 · 检查 6–10 | ⑥`check_today_highlight`：定位 `^##\s+今日要点\s*$` 到下一个 `^##` 之间，数 `^-\s+` 条目，0 条新闻时自动 PASS，count>3 FAIL；⑦`check_self_check_section`：`^##\s+自检结果` + 表头正则 `\|\s*[#\d]+\s*\|\s*检查项\s*\|\s*结果`；⑧`check_forbidden_appendices` 扫 6 个越界关键词；⑨`check_neutrality` 扫 19 个投资建议关键词；⑩`classify_source_level`+`check_source_quality`：无 URL→unknown，先判 C 再判 A 否则 B，**A 级占比分母 = a_count + b_count** | L275–L396 |
| D6，§校验函数 · 检查 11–13 | ⑪`check_disclaimer`：正则 `chip-daily-report\s*skill\s*生成` + `^---\s*$`（缺分隔线仅 WARN 不 FAIL）；⑫`check_section_order`：`expected_order = ['今日要点','设计','制造','封测','EDA','材料','产业链关联','自检结果']`，用**子串包含**匹配已出现章节并要求索引非递减（**未列入 expected_order 的章节被忽略**）；⑬`check_dedup`：字符重合度 ≥70% 且长度 >5 判疑似重复，**仅 WARN 不影响 all_pass** | L404–L446 |
| D6，§TECH_TERM_KEYWORDS | v5.0 新增，**43 个术语关键词**分 7 组：晶体管结构（GAA/FinFET/TFET/Gate-All-Around）、封装（CoWoS/InFO/MR-MUF/Chiplet/2.5D/3D IC/3DIC/先进封装/混合键合/热压键合）、存储（HBM3E/HBM4/HBM3/LPDDR/DRAM/NAND）、制程（EUV/DUV/SADP/SAQP/极紫外）、材料（6N/电子特气/光刻胶/碳化硅/氮化镓/SiC/GaN）、架构（NPU/TPU/存算一体/RISC-V）、**制程节点（2nm/3nm/5nm/7nm/14nm/28nm）** | L450–L466 |
| D6，§校验函数 · 检查 14–15 | ⑭`check_tech_annotations`：对每条非"今日暂无"新闻，用 `title + ' ' + summary` 做大小写不敏感术语匹配，命中则要求 `'[技术注解' in summary or in title`，返回 needs/has/missing 三值；⑮`check_industry_chain`：定位 `^##\s+产业链关联\s*$`，数 `^-\s+\*\*` 组数，扫 6 个环节关键词（设计/制造/封测/EDA/材料/设备）；**≥2 组且 ≥2 环节→PASS；≥2 组但环节不足→仍 PASS 但打 WARN 文案；1 组→FAIL；0 组→FAIL** | L469–L527 |
| D6，§main | 顺序打印 15 个检查块 + 头部横幅 `芯片行业日报校验报告 v5.0`；额外做"新闻总数一致性"检查（声明值 vs 实际值不符则 FAIL）；**WARN 级项（摘要 6 句、无 URL 条目、缺 `---` 分隔线、疑似重复）不置 all_pass=False**；末尾按 all_pass 打印"✓ 全部检查通过"并 `sys.exit(0)`，否则打印"✗ 存在未通过项"并 `sys.exit(1)` | L534–L767 |

### D7：`scripts/__init__.py`

> scripts 包入口，唯一职责是把 validate_report 暴露为可导入模块并声明版本号 — 来源：scripts 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D7，§模块 docstring | 说明"chip-daily-report scripts 模块，提供芯片行业日报的自动化校验工具"；给出两种用法：`from scripts import validate_report; validate_report.main()` 与命令行 `python scripts/validate_report.py 日报文件路径参数` | L1–L12 |
| D7，§导入与导出 | `from . import validate_report`；`__all__ = ['validate_report']` | L14–L16 |
| D7，§版本声明 | `__version__ = '5.0.0'` | L17 |

### D8：`agents/openai.yaml`

> Agent 行为配置文件，把 SKILL.md 的自然语言规则翻译成机器可读的约束项（工具权限/搜索策略/来源约束/输出约束/质量门禁/摘要约束/时效性/模块加载） — 来源：agents 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D8，§文件头注释 | "Chip Daily Report Agent 配置；版本: 5.0 专业深度版（微电子视角+技术解读+产业链关联）" | L1–L2 |
| D8，§interface | `display_name: "Chip Daily Report"`；short_description 强调"6 步高效流程，微电子专业视角"；long_description 说明覆盖全产业链、每条新闻含技术维度与 `[技术注解]`、新增产业链关联小节、三层搜索、15 项门禁；`default_prompt: "使用 $chip-daily-report 生成今天的芯片行业日报。"`；`version: "5.0.0"` | L4–L12 |
| D8，§behavior.tools | 5 项工具权限：`web_search`（必需）、`web_fetch`（必需）、`file_read`（加载 references）、`file_write`（保存日报）、`command_run`（执行校验脚本） | L16–L22 |
| D8，§behavior.search_strategy | `bilingual: true`；`min_sources_per_segment: 2`（1 中+1 英）；`cross_validation: true`；**`max_search_rounds: 3`**；`academic_search: true`（v5.0，ISSCC/VLSI/DAC/IEDM） | L24–L30 |
| D8，§behavior.source_constraints | `min_a_level_ratio: 0.30`；`c_level_forbidden: true`；`broken_link_handling: "标注'链接待验证'，保留标题和摘要"` | L32–L36 |
| D8，§behavior.output_constraints | `format: markdown`；`encoding: utf-8`；`filename_pattern: "芯片行业日报_YYYYMMDD.md"`；must_include 8 项（头部元信息 / 今日要点 1-3 条 / 5 环节 / `[技术注解]` / 产业链关联 ≥2 组 / 自检结果 15 项 / 来源分级统计 / 尾部免责声明）；must_not_include 3 项（市场动态与股价分析等越界附录 / 投资建议与市场预测 / C 级社媒来源） | L38–L55 |
| D8，§behavior.quality_gate | `rubric_items: 15`；**`max_retry: 5`**；`script_validation: true`；`script_path: "scripts/validate_report.py"`；`fail_action: "回到对应Step修正→重新组装→再次自检"` | L57–L63 |
| D8，§behavior.summary_constraints | `min_sentences: 3`；`max_sentences_pass: 5`；`warn_sentences: 6`；`fail_sentences: 7`；`target_word_count: "80-150字"`；五要素列表（主体/事件/数据/影响/技术维度） | L65–L77 |
| D8，§behavior.timeliness | `default_coverage: "最近一个工作日"`；`review_threshold_hours: 72`；`timezone: "Asia/Shanghai"` | L79–L83 |
| D8，§modules | 路径相对于 skill 根目录：main=SKILL.md、sources=references/sources.md、classification=references/classification.md、rubric=references/rubric.md、validator=scripts/validate_report.py；`load_on_demand` 声明 4 个加载时机（sources→Step 2 搜索时、classification→Step 3 分类时、rubric→Step 5 自检时、validator→Step 5 自检后运行） | L85–L98 |

### D9：`芯片行业日报_20260720.md`

> 样例产物 1（v4.0 风格）：11 条新闻、13 项自检表，**无 `## 产业链关联` 小节、无任何 `[技术注解]` 标签** — 来源：项目根目录历史产物

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D9，§标题与头部元信息 | `# 芯片行业日报 — 2026年7月20日`；blockquote 三行：生成时间 2026-07-20 17:15、覆盖范围 2026 年 7 月 15 日-20 日、新闻总数 11 条 | L1–L5 |
| D9，§今日要点 | 3 条：Kimi K3 模型 48 小时自主完成芯片设计（Cadence/Synopsys 股价分别跌 9.47%/7.85%）；台积电 CFO 称 AI 芯片需求"强劲且将持续多年"；台积电 CoWoS 产能 2027 年扩至月 20 万片、SoIC 上修至 5 万片 | L7–L11 |
| D9，§设计 | 1 条：`[回顾]` 中兴微电子 AI 芯片"铁三角"（凌云 51.2T 交换芯片 7nm Chiplet 36×800G、定海 DPU、珠峰 1.0），2026 年营收有望 320-340 亿元；来源 www.163.com（display text 写"21世纪经济报道/网易"），2026-07-15 | L13–L15 |
| D9，§制造 | 4 条：台积电 CFO AI 需求（cls.cn，07-20）；`[回顾]` 台积电 CoWoS 产能 100% 被预订、2027 年月产 ≥20 万片、SoIC 上修至 5 万片、CAGR 超 80%（digitimes.com.tw，07-10）；`[回顾]` 力积电存储代工报价涨 45%、三星/SK 海力士 Q3 合约价涨 20%+（cls.cn，07-16）；`[回顾]` SK 海力士向英伟达交付 12 层 HBM4、约 58% 份额（news.qq.com，07-15） | L17–L25 |
| D9，§封测 | 2 条：SEMI 报告先进封装 587 亿美元、占比首破 54%、中国市场 1700 亿元同比 +25.9%、高端 CoWoS/HBM 产线缺口超 30%（eastmoney.com，07-19）；`[回顾]` 三星/SK 海力士推迟混合键合、继续用热压键合、最早用于 16 层 HBM4E（jiemian.com，07-09） | L27–L31 |
| D9，§EDA / 工具 | 2 条：Kimi K3 参数 2.8 万亿、48 小时自主完成芯片设计、未用 Cadence/Synopsys、两家股价跌 7.85%/9.47%（k.sina.cn，07-19）；Kimi K3 技术细节——开源 EDA + Nangate 45nm 工艺库、面积约 4mm²、约 146 万标准单元、INT4 MAC 阵列、100MHz 时序收敛（news.qq.com，07-20） | L33–L37 |
| D9，§材料 / 设备 | 2 条：`[回顾]` SEMI 预测 2026 年设备销售 1659 亿美元同比 +23.2%、2028 年 2295 亿美元（m.21jingji.com，07-14）；`[回顾]` ASML Q2 净销售 93.3 亿欧元同比 +21%、毛利率 54.0%、上调全年指引至 430-450 亿欧元、订单排至 2028 年（m.toutiao.com，07-15） | L39–L43 |
| D9，§自检结果 | **13 行表格**（1 产业链完整性 … 13 来源质量），全部 PASS；第 4 项说明写"每条 3-4 短句，含主体+事件+数据+影响"（**未提技术维度**）；第 5 项"7 条超 72 小时新闻标注 [回顾]"；第 13 项"A 级 5 条/共 11 条 =45.5%" | L45–L61 |
| D9，§来源分级统计 | 置于自检结果小节内。A 级 5 条（cls.cn ×2、digitimes.com.tw、jiemian.com、21jingji.com）；B 级 6 条（163.com、news.qq.com ×2、k.sina.cn、eastmoney.com、m.toutiao.com）；A 级占比 5/11=45.5% ≥30% ✓ | L63–L66 |
| D9，§免责声明 | `---` 分隔线 + `*本日报由 chip-daily-report skill 生成，所有信息均来自公开可访问的新闻来源。*` | L68–L69 |

### D10：`芯片行业日报_20260722.md`

> 样例产物 2（v4.0 风格）：9 条新闻、13 项自检表，**无 `## 产业链关联` 小节、无任何 `[技术注解]` 标签** — 来源：项目根目录历史产物

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D10，§标题与头部元信息 | `# 芯片行业日报 — 2026年7月22日`；生成时间 2026-07-22 10:30、覆盖范围 2026 年 7 月 20 日-22 日、新闻总数 9 条 | L1–L5 |
| D10，§今日要点 | 3 条：台积电计划 2027 年起上调代工价最高 10%；长电/华天/太极/华工四大封测企业集体公告扩产与业绩预增；西门子收购 Precision Innovations 扩展 EDA 矩阵 | L7–L11 |
| D10，§设计 | 1 条：Anthropic 或引入 AMD 芯片（SemiAnalysis 解读 AMD 高管 GitHub 代码发现），此前已与谷歌 TPU、三星建立供应关系；来源 m.toutiao.com（display"快科技/今日头条"），2026-07-20 | L13–L15 |
| D10，§制造 | 3 条：台积电 2027 年起代工涨价（Nikkei Asia 独家，先进 7nm 及以下 + 成熟 12/16/28nm，基础涨幅 5-10%，HPC 追加订单额外加收 10-15% 溢价，6 月启动谈判 7 月敲定，asia.nikkei.com，07-21）；三星评估泰勒厂月产能 4 万→8 万片、定位 2nm GAA（cj.sina.cn，07-21）；`[回顾]` 三星拿下 Anthropic 制造大单 + 特斯拉 AI5 芯片流片、2nm 泰勒厂生产（m.sohu.com，07-15） | L17–L23 |
| D10，§封测 | 2 条：`[回顾]` 长电科技半年度业绩预增、拟投 78 亿建上海临港先进封测厂；太极实业 HBM 封装订单 +150%（海太半导体月产 12 万片、良率 99%）；华天净利预增 231%-275%；国内封测扩产总额近 400 亿元（**双来源：cninfo.com.cn + m.sohu.com**，07-15）；`[回顾]` 通富微电预增 288%-337%、华天 231%-275%、南亚新材 381%-473%（m.toutiao.com，07-15） | L25–L29 |
| D10，§EDA / 工具 | 2 条：西门子收购 Precision Innovations（2019 年成立、基于开源 OpenROAD 框架，交易 2026 Q3 完成，m.toutiao.com，07-21）；`[回顾]` 新思科技停更部分传统晶圆制造分析软件、转向 AI 芯片设计（被砍业务线 2025 营收占比 低于2%，AI 辅助 PPA 在海外头部厂商 7nm 以下渗透率 61%，m.toutiao.com，07-07） | L31–L35 |
| D10，§材料 / 设备 | 1 条：`[回顾]` SEMI 2026 年设备销售 1659 亿美元（+23.2%）、2028 年 2295 亿美元、WFE 2026 增长 23.1% 至 1439 亿美元、DRAM 设备 +39.0% 至 388 亿美元（semi.org.cn，07-14） | L37–L39 |
| D10，§自检结果 | **13 行表格**，全部 PASS；第 4 项同样写"每条 3-4 短句，含主体+事件+数据+影响"；第 5 项"5 条超 72 小时新闻标注 [回顾]"；第 13 项"A 级 3 条/共 9 条 =33.3% ≥30%" | L41–L57 |
| D10，§来源分级统计 | A 级 3 条（asia.nikkei.com、cninfo.com.cn、semi.org.cn）；B 级 6 条（m.toutiao.com ×4、cj.sina.cn、m.sohu.com）；A 级占比 3/9=33.3% ≥30% ✓ | L59–L62 |
| D10，§免责声明 | `---` + `*本日报由 chip-daily-report skill 生成，所有信息均来自公开可访问的新闻来源。*` | L64–L65 |

### D11：`芯片行业日报_20260727.md`

> 样例产物 3（v5.0 完整版）：22 条新闻、15 项自检表、3 组产业链关联、大量 `[技术注解]`；同时也是三份样例中与 v5.0 规则贴合度最高、但内部数据与格式最不一致的一份 — 来源：项目根目录历史产物

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D11，§标题与头部元信息 | `# 芯片行业日报`（**标题未附日期**）；元信息**不是 blockquote 而是普通行 + 全角冒号 + 行尾双空格**：生成时间：2026-07-27 09:00（北京时间）／覆盖范围：2026-07-20 至 2026-07-27（最近一个工作日周期）／新闻总数：22 条 | L1–L5 |
| D11，§今日要点 | 3 条（每条为**加粗标题+破折号+详述**的长条目）：长鑫科技科创板挂牌、募资 579 亿元创科创板纪录（首日流通 45.03 亿股、申购户数超 942 万、上半年预计净利 500-570 亿元同比涨超 24 倍）；华为发布韬定律 V2 + 麒麟 2026 量产实测（LogicFolding 三维架构，密度 +53.5% 至 238 MTr/mm²，功耗 -41%）；HBM4 进入量产交付、三大存储巨头格局分化（SK 海力士 12 层 HBM4 出货、三星良率近 70%、美光产能锁定，单颗带宽超 2TB/s） | L9–L13 |
| D11，§设计 | **6 条**（全部 `[回顾]`）：①华为韬定律 V2 论文 + 麒麟 2026（155→238 MTr/mm²、功耗 -41%、主频 2.75→3.1GHz、1.5μm 间距混合键合，`[技术注解: LogicFolding…]`，eet-china.com，07-05）；②国产 AI 芯片产能分配（需求 420 万颗 vs 中芯 N+2 供给 260 万颗、华为占 43%、寒武纪 11%、月产能目标 7 万片、良率 >95%、DUV 多重曝光成本贵 40-50%，`[技术注解: N+2工艺…]`，news.qq.com，07-05）；③昇腾 950 超节点量产（8192 卡、算力为 NVL144 的 6.7 倍、互联 16.3PB/s，`[技术注解: NPU…]`，cls.cn，07-16）；④寒武纪思元 690 量产（196GB HBM3、FP16 >700 TFLOPS、市值破万亿，`[技术注解: HBM3…]`，cls.cn，07-16）；⑤9 款国产 AI 芯片纳入信创安全认证 I 级（**本条无 `[技术注解]`**，cet.com.cn，07-14）；⑥三星 VLSI 2026 发布 3D Stacked FET 获最佳论文（42nm 栅距三层堆叠纳米片、评分 8.29/10，`[技术注解: 3D Stacked FET…]`，semiconductor.samsung.com，07-16） | L17–L29 |
| D11，§制造 | **8 条**：①长鑫科技科创板上市（688825.SH、发行价 8.66 元、总股本 668.81 亿股、募资 579.19 亿元超中芯 532 亿元纪录、3 座 12 英寸 DRAM 厂、产能中国第一全球第四，`[技术注解: DRAM…]`，ce.cn，07-27，**唯一未标 [回顾] 的当日新闻之一**）；②`[回顾]` 台积电 Q2 净利 7066 亿新台币 +77.4%、Capex 上调 600-640 亿美元、亚利桑那追加 1000 亿美元（cls.cn，07-20）；③SK 海力士 Q2 营业利润预计 64.1 万亿韩元 +596%（sina.cn，07-26，**无 [回顾]**）；④`[回顾]` 中芯 N+2 月产能 >5 万片、良率 >95%、HBM 封装良率仅 35-40% vs 三星/SK >85%（cls.cn，07-22）；⑤`[回顾]` 三星泰勒厂 4nm→2nm、月产能 2 万→5 万→10 万片、特斯拉 23 万亿韩元合同（chosun.com，07-24）；⑥`[回顾]` 英特尔 18A 良率 65%→85%、率先导入 High-NA EUV 量产（toutiao.com，07-24）；⑦`[回顾]` ASML 上调全年指引 430-450 亿欧元、毛利率 54-56%（cj.sina.cn，07-21）；⑧`[回顾]` ASML+台积电+Imec 2D 材料晶体管 300mm 量产、良率 94%、栅极-源漏间距 50nm（trustexporter.com，07-12） | L33–L49 |
| D11，§封测 | **3 条**（全部 `[回顾]`）：①HBM4 进入量产交付、三巨头路径分化（SK 海力士约 54% 份额、三星良率近 70% 走 TC-NCF+1C DRAM、美光产能锁定，`[技术注解: HBM4…]`，stcn.com，07-22）；②长电/通富 HBM4 封装良率 98.5%（长电 XDFOI 对标 CoWoS、8 层 HBM3E 量产良率 98.5%、盛合晶微 2.5D 中介层市占 85%，`[技术注解: CoWoS + Chiplet]`，stcn.com，07-15）；③三星/英特尔 GAA+背面供电追赶台积电（英特尔 18A PowerVia、三星 SF2Z BSPDN、台积电 A16 才用背面供电，`[技术注解: GAA + 背面供电]`，chosun.com，07-09） | L53–L59 |
| D11，§EDA | **1 条**（章节标题写作 `## EDA`，非 `## EDA / 工具`）：`[回顾]` 华大九天 Argus 3DIC 物理验证平台 + 概伦电子收购锐成芯微补齐 IP 壁垒（SPICE 已进入全球五大晶圆厂中的三家，`[技术注解: 3DIC…]`，eet-china.com，07-06） | L63–L65 |
| D11，§材料 | **4 条**（章节标题写作 `## 材料`，非 `## 材料 / 设备`；全部 `[回顾]`）：①南大光电 ArF 浸没式光刻胶量产、核心树脂国产化率 >80%、良率 99.7%、14nm 完成验证（`[技术注解: ArF 浸没式…]`，toutiao.com，07-19）；②6N 级高纯氟化氢投产打破日本 30 年垄断 + 中船特气六氟化钨产能 2000 吨/年全球第一、价格同比涨超 230%（`[技术注解: 6N 级高纯氟化氢…]`，cena.com.cn，07-19）；③全球首条氧化镓量产线（6/8 英寸同质外延、成本比海外低 80%、击穿电压 9kV、全球专利中国占 64%、材料国产化率突破 32%，`[技术注解: 碳化硅…]`——**注解主题为碳化硅而非正文主题氧化镓**，cena.com.cn，07-19）；④全球设备交付周期拉长、国产替代窗口（北方华创订单 +50%、中微 5nm 刻蚀进入验证、拓荆科技，`[技术注解: 5nm 制程节点…]`，cls.cn，07-24） | L69–L77 |
| D11，§产业链关联 | **3 组**，每组为"`- **关联组N：A → B → C**`"标题行 + 独立段落正文（**正文不在同一 markdown 列表项内**）：①华为韬定律架构创新→EDA 工具链重构→先进封装工艺升级→国产设备需求放量；②长鑫科技 IPO→存储产能扩张→国产设备与材料导入→封测配套需求；③AI 算力需求爆发→HBM4 量产→先进封装产能紧缺→上游材料与设备景气 | L81–L93 |
| D11，§自检结果 | **15 行表格，全部 PASS**，但**检查项名称与顺序采用脚本口径而非 rubric.md 口径**（1 元信息完整性、2 产业链完整性、3 来源可追溯、4 摘要句数、5 时效性、6 今日要点、7 自检结果小节、8 无越界附录、9 中立性、**10 A级来源占比**、11 免责声明、12 章节顺序、13 去重检查、14 技术注解、15 产业链关联）；第 5 项"3 条在 72h 内，19 条超 72h 已标注 [回顾]"；**第 10 项"A 级来源 16 条（72.7%），B 级 6 条（27.3%）"**；末尾"自检总结：15 项检查全部 PASS" | L97–L117 |
| D11，§来源分级统计 | **独立的 `## 来源分级统计` 一级章节**（不在自检结果小节内），采用 4 列表格：**A 级 5 条 33.3%、B 级 10 条 66.7%、C 级 0 条**，代表来源列出"21 世纪经济报道、Samsung Semiconductor、朝鲜日报、证券时报、中国经济新闻网"与"钛媒体、东方财富、同壁财经、国投证券、鲸融360" | L121–L127 |
| D11，§免责声明 | `---` + **三行 blockquote**：`> 本报告由 chip-daily-report skill 生成，面向微电子/IC专业读者。`／`> 报告内容仅供信息参考，不构成任何投资建议。数据来源均为公开报道，均已标注来源链接和时间戳。`／`> 技术注解基于公开技术资料整理，如有疏漏请以官方技术文档为准。` | L129–L133 |

### D12：`.trae/skills/chip-daily-report/`（TRAE 安装镜像目录）

> TRAE 安装镜像，D2 明确要求"必须与根目录同步"。逐文件 `diff` 结果：8 个文件中 7 个逐字节一致，仅 `scripts/validate_report.py` 的 A 级域名清单存在同步缺陷 — 来源：项目 `.trae` 目录

| 章节 | 内容摘要 | 原文定位 |
| --- | --- | --- |
| D12，§目录结构 | 镜像根为 `.trae/skills/chip-daily-report/`，含 8 个文件：`SKILL.md`(18851B)、`CLAUDE.md`(2046B)、`agents/openai.yaml`(4063B)、`references/classification.md`(9718B)、`references/rubric.md`(12235B)、`references/sources.md`(9804B)、`scripts/validate_report.py`(28445B)、`scripts/__init__.py`(325B)；镜像**不含** `芯片行业日报_*.md` 产物文件，也不含 `scripts/__pycache__/` | `ls -laR .trae` |
| D12，§同步状态 · 一致文件 | `diff` 判定**逐字节一致（IDENTICAL）**共 7 个：`SKILL.md`、`CLAUDE.md`、`references/sources.md`、`references/classification.md`、`references/rubric.md`、`agents/openai.yaml`、`scripts/__init__.py` | `diff` 逐文件比对 |
| D12，§同步状态 · 差异文件 | 仅 `scripts/validate_report.py` **DIFFERENT**（主目录 28656B / 镜像 28445B，差 211B），差异**全部集中在 `A_LEVEL_DOMAINS` 常量**，模块 docstring 仍为 v5.0、其余 700+ 行逻辑完全一致 | `diff scripts/validate_report.py .trae/.../validate_report.py` |
| D12，§差异明细 · L52 域名替换 | 主目录：`'tsmc.com', 'samsung.com', 'skhynix.com', 'news.skhynix.com',`；镜像：`'tsmc.com', 'news.samsung.com', 'skhynix.com', 'news.skhynix.com',`。即镜像用 `news.samsung.com` 替代主目录的 `samsung.com` | diff hunk `52c52` |
| D12，§差异明细 · L61-62 缺失 8 域名 | 镜像**缺少**主目录的国内权威源两行：`'ce.cn', 'cet.com.cn', 'xinhuanet.com', 'people.com.cn',` 与 `'cctvl.com', 'chinadaily.com.cn', 'yicai.com', 'cena.com.cn',` | diff hunk `61,62d60` |
| D12，§差异明细 · L68-70 缺失 4 域名 | 主目录：`'asia.nikkei.com', 'reuters.com', 'bloomberg.com',` + 注释 `# 国际媒体` + `'chosun.com', 'koreatimes.co.kr',`；镜像仅保留 `'asia.nikkei.com',`。即镜像**缺少** `reuters.com`、`bloomberg.com`、`chosun.com`、`koreatimes.co.kr` 4 个域名及"国际媒体"分组注释 | diff hunk `68,70c66` |
| D12，§差异影响（数据提取，非裁决） | 镜像 A 级清单共 21 个域名，主目录 33 个，**净差 12 个**（缺 12，另 `samsung.com`→`news.samsung.com` 收窄匹配范围）。以 D11 的 22 条来源域名为输入做集合比对：按主目录清单判定 A 级 16 条 / B 级 6 条 → 72.7%；按镜像清单判定，`cet.com.cn`(1 条)、`ce.cn`(1 条)、`chosun.com`(2 条)、`cena.com.cn`(2 条)、`semiconductor.samsung.com`(1 条，因 `samsung.com`→`news.samsung.com` 后不再匹配) 共 7 条降级为 B 级，A 级 9 条 / B 级 13 条 → 40.9%。两者均 ≥30%，但 **A 级占比数值相差 31.8 个百分点**。此为集合比对得出的数据事实，是否判定为缺陷、如何修复由下游裁决 | D6 §A_LEVEL_DOMAINS + D11 全部来源 URL + D12 §差异明细 |

---

## 3. 冲突记录

> 不同资料对同一事实描述矛盾时，**并列保留两个版本**，不做裁决。

| 编号 | 冲突主题 | 版本 A | 出处 A | 版本 B | 出处 B | 差异说明 |
| --- | --- | --- | --- | --- | --- | --- |
| X1 | 主目录与 TRAE 镜像的 A 级域名清单 | A_LEVEL_DOMAINS 共 33 个域名，含 `samsung.com`、`ce.cn`、`cet.com.cn`、`xinhuanet.com`、`people.com.cn`、`cctvl.com`、`chinadaily.com.cn`、`yicai.com`、`cena.com.cn`、`reuters.com`、`bloomberg.com`、`chosun.com`、`koreatimes.co.kr` | `D6，§配置区 · A_LEVEL_DOMAINS`（L49–L71） | A_LEVEL_DOMAINS 共 21 个域名，用 `news.samsung.com` 替代 `samsung.com`，且不含上述 12 个域名 | `D12，§差异明细 · L52/L61-62/L68-70` | 同一文件在两处副本中清单不同；同一份日报按两套清单校验会得到不同 A 级占比（D11 为例如：72.7% vs 40.9%）。D2 §目录与约定要求"必须与根目录同步"，D1 §反例黑名单 #12 亦禁止配套文件不一致 |
| X2 | TRAE 镜像的同步状态 | "**.trae 镜像需同步至 v5.0**"（表述为整体待同步） | `D2，§当前状态`（L38） | 镜像 8 个文件中 7 个与主目录逐字节一致且内容均为 v5.0；仅 `validate_report.py` 的域名常量不一致，其 docstring 仍标 v5.0 | `D12，§同步状态 · 一致文件 / 差异文件` | 一份说"整体需同步"，一份实测"仅一个常量不同"；镜像滞后范围的描述不一致 |
| X3 | 摘要句数的 PASS/WARN/FAIL 阈值 | "**句数控制：3-4 句 PASS，5 句 WARN，≥6 句 FAIL**" | `D1，§生成流程 · Step 3`（L65） | "**3-5 句 PASS / 6 句 WARN / ≥7 句 FAIL / 1-2 句 FAIL**"；脚本 `3 ≤ sent_count ≤ 5` 为 ok、6 句 WARN、≥7 句 FAIL；YAML `min_sentences:3 / max_sentences_pass:5 / warn_sentences:6 / fail_sentences:7` | `D5，§4 摘要规范`（L69–L73）／`D6，§校验函数 · 检查 4`（L219–L227, L599–L616）／`D8，§behavior.summary_constraints`（L65–L77） | 整体差 1 句。同一份 5 句摘要：按 D1 判 WARN，按 D5/D6/D8 判 PASS；6 句摘要：按 D1 判 FAIL，按 D5/D6/D8 判 WARN。且 D1 同一段落上一行已写"3-5 句"，D1 §输出格式说明（L204）亦写"3-5 句"，与本条自相矛盾 |
| X4 | 摘要过长时回到哪个 Step 修正 | 失败处理表："摘要过长（>150 字或 ≥7 句）→ **回到 Step 5** 重新压缩，按句数控制" | `D1，§失败处理`（L221） | Rubric-Step 映射表："#4 摘要规范 → **Step 3** → 重新压缩摘要" | `D1，§Rubric-Step 映射表`（L126） | 同一文件内两张表对同一动作给出不同回退目标（Step 5 = 自检步，Step 3 = 摘要生成步） |
| X5 | 15 项 Rubric 的编号与项目名 | 编号顺序：1 产业链完整性、2 来源可追溯、3 时间戳准确、4 摘要规范、5 时效性、6 信源可靠性、7 中立性、8 去重、9 元信息完整、10 今日要点、11 分类正确、12 无附录越界、13 来源质量、14 技术注解、15 产业链关联 | `D5，§检查项详情`（L10–L313）／`D1，§Rubric-Step 映射表`（L120–L138） | 脚本输出顺序：检查 1 元信息完整性、2 产业链完整性、3 来源可追溯、4 摘要规范、5 时效性、6 今日要点、7 自检结果小节、8 无附录越界、9 中立性、10 来源质量、11 免责声明与结构完整性、12 章节顺序、13 去重、14 技术注解、15 产业链关联 | `D6，§main`（L550–L752） | 两套均为 15 项但编号映射不同，且**项目集合不完全相同**：脚本独有"自检结果小节""免责声明与结构完整性""章节顺序"3 项；rubric 独有"时间戳准确""信源可靠性""分类正确"3 项。D2 §怎么跑称"必须通过 15/15 项检查"、D6 docstring 称"脚本覆盖 15/15 项 Rubric"，但两份 15 项并非同一集合 |
| X6 | 样例日报自检表采用哪套编号 | D9/D10 自检表为 **13 行**，采用 rubric 口径（1 产业链完整性 … 13 来源质量） | `D9，§自检结果`（L45–L61）／`D10，§自检结果`（L41–L57） | D11 自检表为 **15 行**，采用脚本口径（1 元信息完整性 … 15 产业链关联） | `D11，§自检结果`（L97–L117） | 三份样例产物使用了两套不同的自检表口径与项数；D5 §自检结果输出格式 与 D1 §输出格式 均要求 15 行 |
| X7 | A 级来源清单的权威定义源 | Rubric 判定方法明确"对照 `references/sources.md` 的域名分级表判定级别"；sources.md A 级共 29 个来源，含 `isscc.org`、`vlsisymposium.org`、`dac.com`、`ieee-iedm.org`、`nature.com/natelectron/` 等学术会议/期刊域名，**不含** `ce.cn`、`cet.com.cn`、`cena.com.cn`、`chosun.com`、`reuters.com`、`bloomberg.com` 等 | `D5，§13 来源质量`（L234–L238）／`D3，§A级来源`（L15–L62） | 脚本实际使用硬编码 `A_LEVEL_DOMAINS`（33 个），**不含** 5 个学术会议/期刊域名，但**额外含** 12 个 sources.md 未收录的国内外媒体域名 | `D6，§配置区 · A_LEVEL_DOMAINS`（L49–L71） | 双向差集：sources.md 有而脚本无 5 个（引用 ISSCC/VLSI/DAC/IEDM/Nature 官网将被脚本判为 B 级）；脚本有而 sources.md 无 12 个（引用 ce.cn 等按 sources.md 需走 §来源级别判定规则兜底）。同一条新闻的级别可能因判定依据不同而不同 |
| X8 | Samsung 官方源的 A 级域名写法 | `news.samsung.com/global`（A 级来源表）与 `site:news.samsung.com`（英文 site: 搜索模板） | `D3，§A级来源 · 国际权威源`（L24）／`D3，§搜索关键词模板 · A级限定搜索`（L130） | 主目录脚本用 `samsung.com`（可匹配 `semiconductor.samsung.com` 等全部子域）；镜像脚本用 `news.samsung.com`（仅匹配该子域及其子域） | `D6，§配置区 · A_LEVEL_DOMAINS`（L52）／`D12，§差异明细 · L52 域名替换` | 三个版本并列。D11 §设计第 6 条实际引用 `semiconductor.samsung.com`：按主目录脚本判 A 级，按镜像脚本与 sources.md 字面写法均不匹配 |
| X9 | HBM 量产类新闻归属环节 | 存疑仲裁表："**HBM 相关新闻（制造 vs 封测）→ 制造**"，理由"HBM 本质是存储芯片制造，封装工艺细节才归封测"；§封测反例亦写"❌ SK 海力士 HBM4 量产 → 不是封测，是制造"；D9 §制造收录"SK 海力士向英伟达交付 12 层 HBM4" | `D4，§存疑仲裁规则`（L210）／`D4，§封测 · 反例`（L81）／`D9，§制造`（L25） | D11 将"**HBM4 正式进入量产交付阶段，三大存储巨头差异化路径分化**"归入 **§封测** | `D11，§封测`（L55） | 规则文件与 D9 一致归"制造"，D11 归"封测"；同类事件在两份样例中归属相反 |
| X10 | 企业上市/IPO 类新闻是否纳入 | §制造 · 包含项列有"**晶圆厂动态（新建/投产/上市）**"，正例"✅ 晶合集成港交所上市，全球第九大晶圆代工 → 制造" | `D4，§制造`（L45, L54） | §存疑仲裁表"**AI 芯片公司融资/上市 → 不纳入**"，理由"融资/上市是金融事件，非芯片产业链技术动态"；§不纳入日报的内容列"市场指数/股价/财经分析" | `D4，§存疑仲裁规则`（L213）／`D4，§不纳入日报的内容`（L174） | 同一文件内两处规则冲突。D11 §制造第 1 条"长鑫科技科创板上市募资 579 亿元"并作为今日要点第 1 条（`D11，§今日要点` L11 / `D11，§制造` L35），按 A 版可纳入、按 B 版应排除 |
| X11 | 股价信息是否可出现在日报中 | "市场指数/股价/财经分析"一律不纳入（如：费城半导体指数、SK 海力士股价）；D5 §11 FAIL 示例"费城半导体指数塞入任何环节" | `D4，§不纳入日报的内容`（L174）／`D5，§11 分类正确`（L207） | D9 §EDA 条目标题为"Kimi K3 模型 48 小时自主完成芯片设计，**Cadence/Synopsys 股价重挫**"，摘要含"两家 EDA 龙头股价分别下跌 7.85% 和 9.47%"，并被列为今日要点第 1 条；D9 §自检结果第 7 项"中立性 PASS"、第 11 项"分类正确 PASS" | `D9，§今日要点`（L9）／`D9，§EDA / 工具`（L35）／`D9，§自检结果`（L55, L59） | 规则禁止股价类内容，样例产物含具体股价跌幅并自评 PASS。另 D4 §EDA 正例本身即写"✅ Kimi K3 模型 48 小时自主完成芯片设计，Cadence/Synopsys **股价重挫** → EDA"（L99），与 §不纳入清单同样构成文件内冲突 |
| X12 | 单期日报的新闻条数区间 | Step 2/Step 3 均写"目标条数：15-20 条"；反例黑名单 #16"新闻条数不足（少于10条）… 目标 15-20 条，每环节 3-4 条" | `D1，§生成流程 · Step 2`（L56）／`D1，§生成流程 · Step 3`（L72）／`D1，§反例黑名单`（L266） | 实际样例如：D9 = 11 条、D10 = **9 条**（低于 10 条下限）、D11 = **22 条**（高于 20 条上限）；三份样例自检表均判全项 PASS | `D9，§标题与头部元信息`（L5）／`D10，§标题与头部元信息`（L5）／`D11，§标题与头部元信息`（L5） | 三份样例无一落在 15-20 条目标区间；且 D6 脚本未实现条数区间校验（`D6，§main` 仅校验声明值与实际值一致性，L576–L583） |
| X13 | D11 自身的 A/B 级来源统计数据 | 自检表第 10 项："**A 级来源 16 条（72.7%），B 级 6 条（27.3%），达标**"（合计 22 条，与声明的新闻总数一致） | `D11，§自检结果`（L110） | 来源分级统计表："**A 级 5 条 33.3%、B 级 10 条 66.7%、C 级 0 条**"（合计 15 条，与声明的 22 条不符） | `D11，§来源分级统计`（L121–L127） | 同一文件两处统计相互矛盾（16 vs 5、72.7% vs 33.3%、总数 22 vs 15）。按 D6 主目录脚本对 D11 的 22 条 URL 域名逐条判定得 A 级 16 / B 级 6，与版本 A 数值一致；按 D12 镜像清单判定得 A 级 9 / B 级 13。三个数值并列保留，不做裁决 |
| X14 | 来源分级统计的位置与格式 | 置于 `## 自检结果` 小节**内部**，三行文本格式（A 级列出来源=X 条 / B 级=Y 条 / A 级占比 X/(X+Y)=Z% ≥30% ✓）；D9/D10 依此执行 | `D1，§输出格式`（L191–L194）／`D5，§自检结果输出格式`（L340–L343）／`D9，§来源分级统计`（L63–L66）／`D10，§来源分级统计`（L59–L62） | D11 将其提升为**独立的 `## 来源分级统计` 一级章节**，位于 `## 自检结果` 之后，采用「级别/数量/占比/代表来源」4 列表格 | `D11，§来源分级统计`（L121–L127） | 位置与格式两处不同。D6 §check_section_order 的 `expected_order` 不含"来源分级统计"，该章节在顺序校验中被忽略（L413–L419） |
| X15 | 环节章节标题的写法 | 输出格式模板与 rubric PASS 示例均写 `## EDA / 工具` 与 `## 材料 / 设备`；D9/D10 依此执行 | `D1，§输出格式`（L164, L167）／`D5，§1 产业链完整性`（L22, L24）／`D9，§EDA / 工具`（L33）／`D10，§材料 / 设备`（L37） | D11 写作 `## EDA` 与 `## 材料`（无"/ 工具"与"/ 设备"后缀） | `D11，§EDA`（L63）／`D11，§材料`（L69） | 两种写法并存。D6 §check_segments 用 `^##\s+{seg}` 前缀匹配、`SEGMENTS=['设计','制造','封测','EDA','材料']`，两种写法均可命中（L179–L186），故脚本层面不区分 |
| X16 | 头部元信息的书写格式 | blockquote 三行：`> 生成时间: [年-月-日 HH:MM]` / `> 覆盖范围: …` / `> 新闻总数: [N]条`（半角冒号）；D9/D10 依此执行 | `D1，§输出格式`（L145–L147）／`D5，§9 元信息完整`（L159–L161）／`D9，§标题与头部元信息`（L3–L5）／`D10，§标题与头部元信息`（L3–L5） | D11 用普通文本行 + **全角冒号** + 行尾双空格：`生成时间：2026-07-27 09:00（北京时间）` / `覆盖范围：…` / `新闻总数：22 条`，且一级标题未附日期 | `D11，§标题与头部元信息`（L1–L5） | 格式不一致。D6 §check_metadata 正则用 `[:：]` 兼容全半角冒号，两种写法均可通过（L169–L176），但与 D1/D5 的模板字面要求不符 |

---

## 4. 硬指标清单

| 章节 | 硬指标 | 状态 |
| --- | --- | --- |
| §1 | 每份资料有解析状态，失败/跳过注明原因 | ✅ 12/12 均标注解析状态；1 项跳过子路径（`scripts/__pycache__/`）已注明原因 |
| §2 | 每份文档按章节逐条摘要，每条标注了 `D编号，§章节` | ✅ 12 份文档共 105 条章节级摘要，每条"章节"列均为 `D编号，§章节` 格式，并附"原文定位"行号/命令 |
| §3 | 冲突信息并列保留，不做裁决 | ✅ 记录 X1–X16 共 16 组冲突，每组均并列保留 ≥2 个版本并标注出处，无任何裁决性结论 |
| §0 | 元信息完整（标题/版本/状态/日期/整理人/审核人/原始资料清单） | ✅ 7 项齐备，原始资料清单列出 12 份全路径 |
| §2 | 引用粒度至少到"文件 + 章节"，关键事实精确到行号/表格行 | ✅ 全部摘要行附"原文定位"列（行号区间或比对命令） |
| §2 | 不跨文档主题重组，按文档自身结构组织 | ✅ 12 个小节严格按各文件自身标题/常量块/表格顺序展开 |
| §3 | 冲突条目区分事实提取与推断，推断类标注风险 | ✅ X1/X13 中的占比数值标注为"集合比对得出的数据事实"，并注明"是否判定为缺陷由下游裁决" |
| 全文 | 无占位符残留（`省略号`／`如：`／`年-月-日`／`n 条`／`[待补充]`） | ✅ 全文扫描通过，无残留 |
| 全文 | 覆盖模板全部核心章节 + 附录 A + 附录 B | ✅ §0/§1/§2/§3/§4 + 附录 A + 附录 B 共 7 个部分齐备 |
| 越权 | 不含业务/技术/架构判断与下游结论 | ✅ 全文仅陈述资料事实与差异，未给出选型、架构或修复决策 |

---

## 附录 A：生成流程

### 流程总览

| 步骤 | 动作 | 落入章节 |
| --- | --- | --- |
| Step0 | 读取模板 + 全部原始资料 | — |
| Step1 | 盘点资料清单，标注解析状态 | §1 |
| Step2 | 逐份打开资料，按自身章节结构逐条摘要 | §2 |
| Step3 | 交叉比对不同资料，发现并记录矛盾 | §3 |
| Step4 | 逐项核验硬指标 | §4 |

```mermaid
flowchart LR
    S0[读取模板与资料] --> S1[盘点资料清单]
    S1 --> S2[逐份精读逐章节摘要]
    S2 --> S3[交叉比对记录冲突]
    S3 --> S4[硬指标自检]
```

### 整理原则

1. **逐份精读，不跨文档归并**：摘要按文档自身章节结构组织，不做跨文档的主题重组（那是下游的事）
2. **出处即章节号**：每条摘要标注 `D编号，§章节`，直接映射回原文位置
3. **冲突保留**：矛盾信息并列保留两个版本，不擅自裁决
4. **事实驱动**：以原始资料中的事实为准，不添加主观推断

### 本次执行说明

- 代码类资料（D6/D7）无自然语言章节号，改以「模块 docstring / 配置区常量块 / 函数分组 / main」为章节切分单位，并在"原文定位"列给出行号区间。
- 目录类资料（D12）无章节，改以「目录结构 / 同步状态 / 差异明细 / 差异影响」为切分单位，"原文定位"列给出所用的 `ls`、`diff` 命令与 diff hunk 编号。
- D12 的差异结论均来自 `diff` 逐字节比对输出，未依赖文件名或体积推测。
- §3 中涉及占比数值的条目（X1、X13），数值由「D11 的 22 条来源 URL 域名」与「D6/D12 两份 A 级域名清单」做集合比对得出，属数据提取而非推断；是否构成缺陷、如何取舍留待下游裁决。

---

## 附录 B：解析 Skill

### 模板默认解析能力（本次未触发）

- `docx`：Word 类产品/业务文档 —— 本次资料包中无此类文件，未调用
- `pdf`：PDF 类规范、手册、报告 —— 本次资料包中无此类文件，未调用
- `pptx`：PPT 类方案/汇报 —— 本次资料包中无此类文件，未调用
- `xlsx`：Excel 类数据清单、指标表 —— 本次资料包中无此类文件，未调用

### 本次实际使用的解析手段

| 资料类型 | 解析手段 | 适用编号 |
| --- | --- | --- |
| Markdown 文本（`.md`） | `Read` 全文读取（带行号），按自身标题层级切分章节 | D1、D2、D3、D4、D5、D9、D10、D11 |
| Python 源码（`.py`） | `Read` 全文读取（带行号），按 docstring / 常量块 / 函数分组切分 | D6、D7 |
| YAML 配置（`.yaml`） | `Read` 全文读取（带行号），按顶层键切分 | D8 |
| 目录镜像（`dir`） | `ls -laR` 枚举目录树 + `diff` / `diff -q` 逐文件字节级比对 | D12 |
