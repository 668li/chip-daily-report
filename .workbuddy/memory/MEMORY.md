# chip-daily-report 项目长期约定（MEMORY.md，已精简 2026-08-14）

## 运行环境（铁律）
- 托管 venv 的 yaml/pip 损坏 → 治理/看板/校验脚本一律用 **system Python 3.12**：`C:/Users/李勇谚/AppData/Local/Programs/Python/Python312/python.exe`（yaml 6.0.3 + pytest 9.1.1）。勿碰旧 venv。

## 用户画像（长期，影响所有写作口径）
- 用户=**勇谚，微电子专业大二本科生**。已学/正在学：电路、模电、数电、半导体物理基础（PN 结、MOSFET、能带）。**未系统学**：产业链、市场、政策、财务/金融词汇。
- 行业黑话与金融词是主要卡点；器件/物理原理反而是现成搭桥材料。写「今日导师课」等教学内容时，**全程从课内已知（MOSFET/存储层次/模电）搭桥走向行业未知**，不引入超大纲数学/器件细节；出现术语必配类比。
- 对 AI 自主产出的质量满意，但需要"教得懂"。连接器/技能推荐一律只给**真实有用**项并说明契合点（见各次对话）。

## 规则治理核心
- `rules/rule_registry.yaml` = X1–X16 裁决与全部规则唯一权威源。改域名/规则只改它，再跑 `python scripts/gen_rules.py`（重写 validate_report.py 的 `GEN:RULES` 块 + sources.md `GEN:ALEVEL` 表）。**禁止手工同步两处**。
- X7 一致性：`check_rules_consistency.py` 是 CI 硬门禁（H1–H5 任一不一致退出码 1）。A 级域名=46（脚本 39+学术 5+官方一手 2：asml.com/amkor.com 为 v7.1 补录）；Samsung 统一 `samsung.com`。
- 镜像同步：`.trae/skills/chip-daily-report/` 为精选子集（CLAUDE.md/SKILL.md+references+运行时脚本），镜像已有的文件须与根目录逐字节一致、**勿新增文件**；同步一律 Read+Write 工具逐文件写（Bash cp/heredoc 写源码或配置会被安全钩子拦；注意 R1 段不覆盖 CLAUDE.md，该文件靠人工纪律保持一致）。

## 关键裁决速查
- X3 摘要 3-5 句 PASS/6 WARN/≥7 FAIL。X9 HBM 归制造。X10 产能 IPO 纳入/纯融资不纳。X11 股价仅一句佐证，不作主体/标题/今日要点。
- X12 条数 15-20 软（10-14/21-25 WARN，<10/>25 FAIL）。X15 环节全称。X16 标题附日期+blockquote 半角冒号。X17 信号层（每条 `| 信号: 重要性/影响方向/情绪`，覆盖≥80%）。B 持续追踪 / C 前瞻催化剂（Step2 只搜已公告，禁预测）。
- 校验器=26 项（15 Rubric+检查 16-26），后 8 项软 WARN 不破退出码。

## 日报格式规范（改规范走"四条链路"铁律）
- 新增小节必须同步改：①validate_report.py ②report_viz/parser.py ③views/report_view.py ④report_viz/__init__.py(CSS)。HTML 交付前 grep 断言新元素出现。
- 小节清单：费曼解释 / 深度解读（这意味着什么+未来影响+格局意义）/ 未来借鉴（趋势信号↑→↓弱+格局预判+可借鉴行动+风险提示+格局时间轴）/ 今日导师课（4 模块，独立第 6 视图 Tab）/ 持续追踪 / 前瞻催化剂。

## HTML 交付形态
- 权威构建器=`scripts/build_report_html.py`（基于 scripts/report_viz/ 模块包，5 视图 Tab：report/chain/dimensions/trend/weekly）。**禁止重写简化版**（曾误写 report_html.py 顶掉原版已删）。

## multi_source 融合模块
- `scripts/multi_source/`：collector→cleaner→fusion→gap_analyzer。聚类仅从标题实体共现；分歧检测只抓带单位数字无交集。
- 漏聚探测器 leak_detector.py：只建议候选锚词不自动改码。
- 三件套（挂 F4 Step6 fail-soft）：health_check→source_health.yaml；value_score→value_score.json（47.6 首跑）；report_viz→multi_source_report.html。
- **迭代3（2026-08-15）：online 采集扩至 6 源**（+CNBC B级 / +SemiAnalysis A级；DigiTimes 反爬未接入）。新增 **gate.py 选择性纳入门禁**（G1 置信度/G2 时效/G3 单源/G4 环节配额/G5 主题关键词/G6 数量上限）→ state/gate_report.json，Step2 搜索前先看候选池。**prepare_candidates.py 一键流水线**（online→clean→fusion→gate，不落盘 data/ 基线）已接入 F4 自动化生成前步骤。测试 **134 passed**。
- **v5.9（2026-08-15）：英文一律译中文纪律 + 前瞻催化剂升级**。写作纪律固化 SKILL.md：机构名/来源标签必中文、术语首现「中文（缩写）」、产品型号首现加中文说明、URL 不翻；新建 `references/glossary.md` 中英文术语对照表（机构30+/术语40+）。前瞻催化剂从裸表升级为「速览表 + 高/中重要度前瞻解读块（看点/关注信号/潜在影响）」，每日必给，与「深度解读」对称。F4 自动化 prompt 已加 v5.9 硬性段，日后每日自动遵守。
- 数据源扩容：4 免 key 源（SEC EDGAR / SemiEngineering / EETimes / AIHOT）。`python -m pytest tests/ -q`=**132 passed**（改 fusion/leak/collector/health/value_score/report_viz/gate 必跑）。**data/ 是回归基线，跑 online 会覆盖致测试挂 → online 快照另建目录**。

## 认知深化
- signal_history.py（Step6 每日跑）→ state/signal_history.json；weekly_review.py（Step7 周五）→ delivery/芯片行业周度复盘_YYYYMMDD.md/.html（需 state/weekly_insights_*.txt 注入）。信号曲线 svg Y=-2..2。测试 113 passed。

## 自动化落地
- ⚠ **2026-09-25 现状：以下两个 automation 均已停摆**（最后产出 2026-09-10；WorkBuddy 环境不再运行，当前 ZCode 环境也无定时任务）——日报停摆中，待重建（需求：失败要响）。**（2026-09-27 更新：心跳已在 ZCode harness 重建为 daily_runner+定时任务，见文末 v8 快照；F4/F9 历史形态仍停摆）**
- F4=automation-1786184607023（周一至五 08:00）：生成→validate→build_report_html→quality_dashboard→multi_source 三件套→archive_to_kb→中文汇报。
- F9=quality_dashboard.py → delivery/quality_dashboard.md/.json（计算 A 占比+5 环节覆盖+X 信号+自述 vs 计算对账）。
- 周质量看板=automation-1786185290346（每周五 18:00）。

## 知识库归档
- archive_to_kb.py：`--report <md> --kb-root D:\我的知识库` → `07-芯片行业日报\`（归档+MOC 卡片+索引），内容 sha256 幂等+fail-soft。

## 未决
- F5 LangGraph / F8 控制台本环境不可行 → 6 步 skill 即编排、WorkBuddy 界面即控制台（用户已接受等价）。

## 全权委托授权（2026-08-17 13:16 起生效，持续有效直至用户明确撤销）
- 用户将 chip-daily-report 项目的**完整规划与执行**全权委托给小谕（AI 搭档），无需询问/确认/汇报/等待。
- 权限范围：自主决定技术方案与实施步骤、自行设计测试与比对方案、可调用 Karpathy 等已有技能、可自行安装所需工具、可全权主导项目演进。
- 用户声明"现已离线休息"，故不再期待交互式回复；但仍应产出可验证的落地结果并写入项目记忆。
- 执行基线：可进化架构优化（M0–M6，详见 `references/evolution_plan.md`）。已落地 M3 预判校准器 + 规划文档；M0 结构化中间表示为下一优先地基。
- 约束不变：仍须遵守既有铁律（system Python 3.12、X7 一致性、data/ 不污染、26 项校验不破、禁止手工同步规则源、HTML 用 build_report_html.py）。

## 已集成外部技能/连接器（v5.12，用户安装，全 fail-soft）
- 财联社实时电报：`cls-custom-news` 技能（agent-browser 浏览器渲染）抓芯片关键词快讯，作 Tier-3 实时线索，需 A 级交叉确认，浏览器不可用则跳过。
- 多引擎搜索：`multi-search-pro` 技能，财经新闻用 新浪财经/东方财富新闻/财联社 URL + 时间过滤 `tbs=qdr:w` + 百度+Google 双语交叉。
- 东方财富妙想MCP（`mcp__mx-ds-mcp__mx_macro_data`）：市场章节量化数据，**已验证可用**（短关键词 DRAM合约价格/NAND闪存价格/半导体设备销售额/集成电路产量；长句返回空），fail-soft 回退新闻引用。
- ima 知识库（`mcp__ima-mcp`）：导师课云镜像，`create_media`→COS→`add_knowledge`，`knowledge_base_id` 由用户配，fail-soft。
- 铁律：任一外部通道不可用，静默回退既有 WebSearch+AIHOT+多源采集，绝不阻塞交付。

## 2026-09-25 洁癖收尾快照（ZCode 会话，勇谚在场）
- **版本终态**：master = v5.13 + 安全加固 + **v6.0 理解优先版草案**（写作层已实现，样例 26/26 过门禁 + 学生冷读 pass，**待用户拍板启用**）。产物：`delivery/日报理解优先改造方案.md`（决策文档）、`delivery/日报理解优先改造方案_规范.md`、`delivery/芯片行业日报_20260910_理解优先版.md`。
- **v6.0 核心**（响应勇谚原话"谁涨价谁降价我根本理解不了"）：四层新闻写法（主行事实不动 + 🧠课内搭桥 + 🎯对你意味着什么 + 🎓💼考研/就业双视角）；黑话三档治理（`references/jargon_bridge.md`，C 档正文禁裸用）；今日一课前移第一屏；条数收紧 15-16；主线必读 11.5 分钟。零门禁改动路线：validate_report.py 零改动，四条链路实测无需改；`validate_understanding.py` 是第二阶段规划占位（尚未创建）。
- **安全加固（本轮，Mimosa 深扫 9→0）**：collector/health_check = https+域名白名单+私网IP拦截+5MB上限；RSS 解析 defusedxml 禁 DTD/实体；forecast_audit/tracker/cross_validate 写入路径锚定 `__file__` 派生常量。安全钩子写法教训：路径类修复只有"写入位置完全固定"能过判定器。
- **远端备份**：`github.com/668li/chip-daily-report`（私有），master+evolve 双分支；推送走本机代理 127.0.0.1:7897，仓库级 git proxy 已配；evolve/20260719-2130 为历史演化分支（含 12 期日报）。
- **测试真相（修正旧记载）**：上文"132/134 passed"是 2026-08-15 时代数值，已失真。现状：全量 pytest 因 3 个脚本式测试（test_m1_crossvalidate/test_m3_scenarios/test_m4_m5_m6，模块顶层 sys.exit）收集即 INTERNALERROR → 需 --ignore 三文件后跑（当前 136 passed + 4 failed 存量：weekly_review KeyError 'scenario_review'）；m1/m3 独立跑全过，m4_m5_m6 独立跑 1 个状态依赖失败。**跑 pytest 必污染真实 state**（source_health.yaml/leak_report.*），跑完 `git checkout --` 还原。
- **镜像**：5 个脚本（build_report_html/report_viz/__init__/parser/views/__init__/weekly_review）历史漂移已清零；references 补齐（evolution_plan/forecast_timeline_v2/glossary/schema.json/jargon_bridge）。X7 硬检查通过。
- **待拍板**：① v6.0 启用（生成首期）② 每日自动化在 ZCode 重建 ③ multi_source 上线 or 归档 ④ 存量测试债。

## 2026-09-26 v7 自主源发现层快照（ZCode 会话，勇谚睡梦中全权执行）
- **版本终态**：master = v6.2 + **v7 自主源发现层（106e311 已推送）**。v6.0/v6.1/v6.2 均已落地（待拍板①已了结，③部分了结：发现层+采集层上线，gate→日报候选链路仍未接入日常生成）。
- **v7 核心**（响应勇谚"打破信息茧房，不要总我喂你"）：`scripts/multi_source/discover.py` 三引擎（Google News RSS 中英 / OPML 种子 / newsnow 热榜）自动发现新域→四道验证（HTML 壳拒/90 天新鲜度/相关性三条件：词边界关键词≥3+命中条目≥2+**密度≥30%**/重定向逐跳校验）→ Miniflux 式生命周期（candidate→trial→active，确定性 3 败冻结，瞬时失败不惩罚退避 24h）；状态 `state/discovered_sources.json` 已入库（运行更新属预期噪音）。终池 6 active 全部实测密度≥0.30。
- **collector**：online 6→16 源（+IEEE Spectrum/Tom's Hardware(用 /feeds.xml，/feeds/all 会 301 到 http)/Nikkei RDF(dc:date)/KoreaHerald/Yonhap/Yahoo NVDA+TSM/GoogleNews/巨潮 GBK 绕代理/newsnow）+ 动态白名单（trial/active 并入、**www 变体互补**）；动态源一律 tier=4 走 gate G3 降级线；人工定级唯一通道=录 rule_registry→gen_rules→X7。
- **对抗审查四轮**：workflow 内对抗审查员 13 发现（5 high：词边界/OPML 搬运伪装发现/tier 同级/302 重定向 SSRF/冻结参数）9 修复；主会话第 4 轮验证修复真身+新增 rescore 模式（门禁升级全池复判）+密度门禁 0.30（实测谱：真垂类 0.35-0.5）+www 变体+tomshardware 修复。Mimosa 深扫 0 finding。
- **测试**：tests/test_discover.py 40 用例全离线；全量 176 passed + 4 存量（weekly_review）；test_health_check 污染真实 state 的根因已修（HEALTH_FILE 指 tmp），leak_report 系仍需还原。
- **新待拍板**：① 每日自动化重建（quick 发现已可挂每日流程）② gate 候选链路接入日常生成 ③ newsnow 自部署（公共实例 403）④ 存量测试债。

## 2026-09-27 v8 护城河冲刺快照（ZCode 会话，勇谚发射提示词全自动执行）
- **版本终态**：master = v7.1 + **v8 冲刺（推送至 c5b9449）**。上文 v7 快照「新待拍板」①②④ 已了结，③ newsnow 自部署仍待；评审优化版回填类工作此后由机制承担。
- **心跳已恢复**：`scripts/daily_runner.py`（prepare=发现+候选池+到期点名预警 / verify=26 门禁+理解层+到期点名+HTML，fatal 非零退出指明炸哪步）+ ZCode 定时任务 automation-fe364622（周一至五 08:00，首跳 2026-09-28；删除=CronDelete 该 id）。runner 只做机械链路，正文生成=定时 LLM 会话按 SKILL.md 六步（ADR-002）。**推演到期点名 forecast_due.py 已接 verify 强制链：有逾期未判推演则日报不许收工。**
- **门禁族**：26 项硬校验 + `validate_understanding.py` v1（U1-U6 存在性，带第 1 期缺陷样本 9 红灯，26 数不变）+ 采中准入（无文章级 URL 不入候选池）+ gate G7 话题去重 + G3 official_primary（publisher_domain 消费）。
- **测试真相**：全量 pytest **199 绿 0 败（历史首次全绿）**；m1/m3 独立跑 ✓；m4_m5_m6 独立跑 1 败（状态依赖）记账不修。跑 pytest 后照例还原 state 污染。**教训：交接时点必须现场复跑门禁再报数**（v7.1 会话曾报绿但实际遗留 3 败）。
- **试产第 2 期（20260926）**：16 条全 72h 窗口/文章级 16/16/A 级 31.3%，26+理解层 exit 0，自评 P0=0；**独立 critic 评审待补**（当日子代理配额全程超限，对标调研同因降级为 WebFetch 直读——ADR-007）。
- **现役待办**（详见 delivery/会话交接_20260926.md）：周一首跳验证、补独立评审、gnews 分享链降级证据治理+中文权威源直链化（A 级占比 31.3% 踩线，负 delta 已记台账）、理解层 v2 语义校验、加时池②-⑤。
- 权威文档：台账 delivery/迭代台账.md；对标 delivery/对标报告_护城河_20260926.md（五论点判决：推演问责/批评代谢独占、诚实性领先、教学层独占、发现层持平）；ADR-001~007 在 delivery/ADR_20260926.md。
