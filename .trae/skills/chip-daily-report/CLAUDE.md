# CLAUDE.md — chip-daily-report skill

## 定位
生成带来源与时间戳的芯片行业日报的 skill，覆盖设计/制造/封测/EDA/材料设备全产业链。读者唯一且明确：微电子大二学生勇谚——v6.0 起核心目标是「让他真正吸收」（黑话三档翻译 + 四层新闻写法 + 今日一课），不再是行业事实播报。

## 怎么跑
- 生成日报：skill 触发词（"芯片日报"等）启动 SKILL.md 六步流程（v4.0 起 10 步合并为 6 步 + Step 7 周度复盘）；生成前先跑 `<系统Python> scripts/daily_runner.py --stage prepare`（含发现层 quick + 候选池；每周一 `discover.py --mode full`）刷新
- 校验日报：`C:/Users/李勇谚/AppData/Local/Programs/Python/Python312/python.exe scripts/daily_runner.py --stage verify --report <日报路径>`（串联 validate_report 26 项 + forecast_due 推演到期点名——**有逾期未判的推演会非零退出** + validate_understanding 理解层 + validate_claims **声明级对账：承重数字对照来源原文，对不上不出版**（v8 R2，首跑含真实网络抓取，缓存在 state/article_cache/） + build_report_html；退出码 0=全过；一律用系统 Python 3.12，勿碰旧 venv）
- 跑测试：`<系统Python> -m pytest tests/ -q --ignore=tests/test_m1_crossvalidate.py --ignore=tests/test_m3_scenarios.py --ignore=tests/test_m4_m5_m6.py`（后三个是脚本式测试，独立跑 `python tests/test_mX.py`）
- pytest 零污染（2026-09-28 对齐轮：leak_detector.main(out_dir) 参数化、测试写 tmp_path；实测全量 pytest 后 git status 干净，`git checkout --` 还原仪式废止）
- 规则治理：改域名/环节只改 `rules/rule_registry.yaml` → 跑 `scripts/gen_rules.py` → 跑 `scripts/check_rules_consistency.py`（X7 硬门禁）；**禁止手工同步**注册表↔脚本↔sources.md
- 发现层运维：`discover.py --mode quick|full|status|rescore`——rescore 用于每次升级相关性门禁后对全池复判清洗；发现源人工定级唯一通道 = 录 rule_registry.yaml → gen_rules → X7
- **心跳死亡开关（v8 R5-C）**：`state/heartbeat.json` 记录最后成功心跳（runner 两阶段自动刷新）；**任何会话启动时读它，>48h 无成功记录即亮红灯**（daily_runner prepare 开头自动验尸；其他会话手动读文件核对 last_ok_ts）

## 技术栈
- Markdown（SKILL.md 主控 + references/ 知识库）+ Python 3.12（scripts/ 全部本地脚本，系统 Python 已装 pyyaml/pytest/defusedxml）
- 私有远端备份：`github.com/668li/chip-daily-report`（推送需走本机代理 127.0.0.1:7897，仓库级 git proxy 已配）

## 目录与约定（关键件）
- `SKILL.md` — 主控（v8 现役：六步流程 + 无源声明不入正文/同题不复读写作纪律）；`references/` — sources/classification/rubric/glossary/jargon_bridge（黑话桥）/catalysts
- `scripts/validate_report.py` — 26 项硬校验（Mimosa 安全加固后 0 finding）；`scripts/validate_understanding.py` — 理解层存在性校验 v1（U1-U6，带第 1 期缺陷样本红灯，由 runner 串联强制，ADR-004）
- `scripts/daily_runner.py` — **每日心跳一条命令**（prepare=生成前发现+候选池 / verify=生成后校验+HTML；fatal 步失败非零退出指明炸哪步）；`scripts/multi_source/` — discover.py（v7 三引擎+生命周期）/collector/cleaner（含 v8 采中准入）/fusion/gate（G1-G7+official_primary）/leak_detector/value_score/health_check/gap_analyzer/prepare_candidates
- `scripts/build_report_html.py` + `report_viz/` — 视图 HTML 构建器；`archive_to_kb.py` — Obsidian 归档（`D:\我的知识库\07-芯片行业日报\`）
- `state/` — 跨日记忆与运行数据（report_state/signal_history/forecast_log/discovered_sources/gate_report/heartbeat/claim_report/reader_feedback 等；运行更新属预期 git 噪音）；`data/`（multi_source 下）是回归基线，online 抓取勿覆盖
- `.trae/skills/chip-daily-report/` — 镜像，须与根目录逐字节一致（X1/X2，`check_rules_consistency.py` 的 R1 段监督；同步一律 Read+Write，Bash 写源码/配置会被钩子拦）
- `.workbuddy/memory/MEMORY.md` — 项目长期约定与运行铁律的唯一权威（含用户画像、四条链路同步法）

## 当前状态（2026-09-28 补课轮后）
- master = v7.1 + **v8 护城河冲刺（2026-09-26/27）** + **补课轮（2026-09-28，a43cc5b 已推送：声明级对账门禁/ithome 中文直链/发现层产出问责）**
- **每日心跳已恢复**：`scripts/daily_runner.py`（`--stage prepare|verify`/`--all`，fatal 步失败非零退出指明炸哪步）+ 本 harness 定时任务 automation-fe364622（周一至五 08:00，工作日口径；删除方法=对 harness 说删除该 automation 或 CronDelete automation-fe364622-b7a5-4d6a-81de-e5650026c57d）；dry-run 全绿 9 步 exit 0（531s）；runner 只做机械链路，正文生成=定时会话按 SKILL.md 六步（ADR-002）
- **门禁族 = 26 项硬校验 + 理解层存在性校验 + 声明级对账**：`scripts/validate_understanding.py` v1（U1-U6：导师课/第一课非空/费曼节/推演块知识锚+成长含义+验证窗口）由 runner verify 串联强制，26 数不变（ADR-004）；带 9 个第 1 期缺陷样本回归红灯（tests/test_validate_understanding.py）；`scripts/validate_claims.py`（v8 R2）：承重数字跨语言变体（640亿↔$64b）对照来源原文（article_fetch 安全抓取+缓存 state/article_cache/），取得原文而覆盖<50% = FAIL 不许出版，verify 第 4 步 fatal——首跑第 2 期 mismatch=0 但抓出「挂靠数字」（220% 不在被引原文），可对账率 25% 入台账
- **采中准入**：无文章级 URL 的候选不入池（cleaner.admit_article_level，口径同 [G-1]）+ gate G7 话题去重（overlap≥0.7 收窄网）+ G3 publisher_domain 消费（官方一手域标 official_primary，registry 运行时读取）——第 1 期「回填 9 处」成本归零的机制保证
- **测试真相（2026-09-29 对齐轮实测）**：全量 pytest **229 passed + 0 failed**（--ignore 三脚本式测试后；199 基线 + 补课轮 29 用例 + 对齐轮 TrendForce 直连单测 1；补课轮时点曾报 220/228 两个口径，228 为对齐轮修正的漏改值）；m1/m3/m4_m5_m6 独立跑 ✓（m4_m5_m6 断言去快照化 `≥7`，存量 1 败清零——债③闭账）；跑 pytest 零污染无需还原（见「怎么跑」）
- **试产第 2 期（20260926）**：16 条全 72h 窗口、文章级 16/16（11 直链+6 gnews 分享链如实标注降级证据）、A 级 31.3%、26 门禁+理解层 exit 0；评审=主上下文自评（判定「值得读」、P0=0、P1×3/P2×4 全部处置）+ **2026-09-28 补记**：独立评审探针两发仍败（project-critic=钉死供应商 bigmodel-start-plan 缺失——配置问题非配额，该通道需先修供应商配置；general-purpose=并发配额超限），机器侧声明级对账 mismatch=0 佐证 P0=0 但抓出挂靠数字，全文见 `delivery/日报质量评审_20260926_第2期.md`
- **中文源直链（v8 R3）**：ithome RSS（`www.ithome.com/rss/`）实测 200·60 条全文章级 → collector ITHomeCollector + registry **B 级**补录（引用须溯源权威原文）；财联社/证券时报免 key 通道不存在（404/JS 壳/签名墙），eet-china 本环境双路超时——见 `delivery/中文源直链调研_20260928.md`
- **路线 C 分层混合（2026-09-28 读者仲裁落地）**：新闻条目=承重层 3-5 条（◆，双源交叉+「→ 一句话」结论）+ 背景层 5-8 条（◇，单源行内标「⚠单源待证」）；X12 新区间 8-13 条（registry thresholds 已改+gen_rules 重生成+金测试 47 域断言已同步）；**交叉验证率基线 12.5%（2/16）为台账第 2 指标**；TrendForce 直连 RSS 已接入（A 级 47 域，feed pubDate 是列表缓存日须以文章页日期为准）；**220% 挂靠数字已回改**（外部口径 200%+ 并注明对账处置）；心跳死亡开关已装（state/heartbeat.json + 48h 红灯）——四维审查（delivery/四维对抗审查_子代理版_20260928.md）最优先项全部落地
- **发现层产出问责（v8 R4）**：discover.py `production_accounting`——validated 按 discovered_via 拆种子/非种子（缺失/未知渠道宁按种子计），quick/full/status 每次打印问责行，非种子=0 时横幅宣布「发现层=机制演示」；真实基线非种子=1（shattered.io）；prepare_candidates 给 top8 直链候选附 body_full（≤4000 字，生成读原文不看 160 字摘要）
- **对标结论**（`delivery/对标报告_护城河_20260926.md`）：五论点判决——推演可问责/批评代谢=独占（开源零同类），诚实性工程=领先（最接近物 citation-check-skill 248★），教学层=独占（C 组搜索最高 5★），自主发现层=持平（TrendRadar 62.5k★/Horizon 9.5k★ 为规模天花板），心跳=持平（恢复后成立）。注意：本轮调研为 WebFetch 直读降级口径
- 台账：`delivery/迭代台账.md`（9 指标基线→终版，含 A 级占比负 delta 与 pytest 基线口径偏差的诚实注记）；交接：`delivery/会话交接_20260926.md`
- **读者环（2026-09-28 启动，台账第 1 指标）**：定位判决=自用学习工具（勇谚拍板）——`state/reader_feedback.json` 四问提取测试（读几分钟/带走一概念/跳过哪节/对账自判）是读者价值唯一数据源；采集点=心跳汇报后+生成会话交付后，每期一次自然窗口、无反馈不追问。**数据点 #1**（推演节：少/传导链不明确/不知道意味着什么）→ SKILL 推演纪律三修订+推演 3 条起步（**该条同日撤销**：数据点 #2 澄清「少」指数据源少而非推演数量少，加量=加重病灶——现役口径见 SKILL.md 推演纪律行）；**数据点 #2**（修正「少」=数据源少；质量=交叉验证——"单源日报是给我干什么的"）→ **交叉验证率入台账第 2 指标（基线 12.5%=2/16）**+SKILL「承重事实双源优先+单源待证显式标注」+newsnow 自部署升级为数据支持项（推荐 Vercel 免费部署，待拍板）。**冻结窄修订**：供给与写作纪律解冻；新门禁/新校验器/理解层 v2 继续冻至 2026-10-12
- **AIHOT 对标与落地（2026-09-29）**：深挖 KKKKhazix/AIHOT 开源框架约 45 文件（`delivery/对标报告_AIHOT_20260929.md`——护城河四项不动摇；最大空白=金标选稿校准闭环；三视角拆解文在 ~/Documents/notes/）+ 落地三件（冻结期解冻范围）：①AIHOT 精选池直采通道（collector `scope.aihot_selected`，默认关 prepare_candidates 默认开；无关键词补「没想到去搜」的交叉发现）②SKILL 写作纪律「忠实原文五守则」（矛盾显式标注/相对时间照抄/排他性须原文明确/不强化语气/标题保型）③心跳告警四要素化（读者看到什么/会不会自愈/要做什么/排查线索）；pytest 232 绿；**冻结期满候选清单**（金标样本集/SelectBench 式 eval/承重实体守卫/抓取频率自适应）录台账 AIHOT 轮节
- 已知债（2026-09-29 对齐轮更新）：①中文权威源直链化**部分解决**（ithome 已接入；财联社 RSS 404 证实死亡，stcn 直达通道实测不存在——newsnow 自部署 vs RSSHub 决策材料在调研文档，**挂起至 2026-10-12 冻结期满**；RSSHub localhost feed 豁免涉 SSRF 白名单变更须单独评审）②A 级占比 31.3% 踩线（对策=ithome/TrendForce 直链供给 + 期刊域名定级走 rule_registry 通道，下期看 delta）③~~m4_m5_m6 状态依赖 1 败~~**已闭账**（2026-09-28 收编轮去快照化，独立跑 exit 0） ④newsnow 自部署挂起（见①）⑤~~「独立评审待补」~~**已闭账**：2026-09-28 fd50686 四维对抗审查+六维评审（general-purpose 通道）判定值得读；2026-09-29 对齐工作流独立评审复核（值得读/P0=0/P1×3→已转内容修复）；待办仅剩评审全文归档（T3）⑥理解层 v2（语义一致性+课程清单 schema）冻结期内不动 ⑦心跳首跳执行记录待验证（automation-fe364622 runCount=0，下一次窗口 09-29 08:00；伪造测试值已于 2026-09-28 删除——heartbeat.json 现不存在，死亡开关如实亮「从未成功」红灯，首跳成功即写入首颗真实心跳，属设计内）⑧~~X12 四方口径矛盾~~**已闭账**（2026-09-28 对齐轮）：registry thresholds.news_count 为唯一权威（目标 8-13 / WARN 14-20 / FAIL <8、>20），validate_report+quality_dashboard+validate_ir 运行时读取不再硬编码，测试断言同步，golden 0925（18 条）按现役口径回望为 WARN 不 FAIL；**校验器侧已全部收编**（2026-09-28 延伸轮：X3 句数 thresholds.summary_sentences 接线+forbidden_appendices 纠偏为 3 词现役口径+investment_advice/tech_terms 关键词表运行时读取+validate_ir X17 恢复 v5.2 [R-5] 的 WARN/0 条 PASS 裁决）；**管线侧阈值族留 10-12 首批**（gate conf_min/G4/G6/G7/stale_days、discover 相关性 3-2-0.30 与生命周期、fusion 权重/freshness 阶梯、value_score 权重、TARGET_GRID、segments 五处副本、G2-vs-72h 共享时效字段）
