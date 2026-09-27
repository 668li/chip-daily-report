# CLAUDE.md — chip-daily-report skill

## 定位
生成带来源与时间戳的芯片行业日报的 skill，覆盖设计/制造/封测/EDA/材料设备全产业链。读者唯一且明确：微电子大二学生勇谚——v6.0 起核心目标是「让他真正吸收」（黑话三档翻译 + 四层新闻写法 + 今日一课），不再是行业事实播报。

## 怎么跑
- 生成日报：skill 触发词（"芯片日报"等）启动 SKILL.md 六步流程（v4.0 起 10 步合并为 6 步 + Step 7 周度复盘）；生成前先跑 `<系统Python> scripts/daily_runner.py --stage prepare`（含发现层 quick + 候选池；每周一 `discover.py --mode full`）刷新
- 校验日报：`C:/Users/李勇谚/AppData/Local/Programs/Python/Python312/python.exe scripts/daily_runner.py --stage verify --report <日报路径>`（串联 validate_report 26 项 + validate_understanding 理解层 + forecast_due 推演到期点名——**有逾期未判的推演会非零退出** + build_report_html；退出码 0=全过；一律用系统 Python 3.12，勿碰旧 venv）
- 跑测试：`<系统Python> -m pytest tests/ -q --ignore=tests/test_m1_crossvalidate.py --ignore=tests/test_m3_scenarios.py --ignore=tests/test_m4_m5_m6.py`（后三个是脚本式测试，独立跑 `python tests/test_mX.py`）
- ⚠ 跑 pytest 会污染真实 state（source_health.yaml / leak_report.*）——跑完必须 `git checkout --` 还原这几个文件（test_health_check 污染根因已于 v7 修复，但 leak_report 系仍会被写）
- 规则治理：改域名/环节只改 `rules/rule_registry.yaml` → 跑 `scripts/gen_rules.py` → 跑 `scripts/check_rules_consistency.py`（X7 硬门禁）；**禁止手工同步**注册表↔脚本↔sources.md
- 发现层运维：`discover.py --mode quick|full|status|rescore`——rescore 用于每次升级相关性门禁后对全池复判清洗；发现源人工定级唯一通道 = 录 rule_registry.yaml → gen_rules → X7

## 技术栈
- Markdown（SKILL.md 主控 + references/ 知识库）+ Python 3.12（scripts/ 全部本地脚本，系统 Python 已装 pyyaml/pytest/defusedxml）
- 私有远端备份：`github.com/668li/chip-daily-report`（推送需走本机代理 127.0.0.1:7897，仓库级 git proxy 已配）

## 目录与约定（关键件）
- `SKILL.md` — 主控（v8 现役：六步流程 + 无源声明不入正文/同题不复读写作纪律）；`references/` — sources/classification/rubric/glossary/jargon_bridge（黑话桥）/catalysts
- `scripts/validate_report.py` — 26 项硬校验（Mimosa 安全加固后 0 finding）；`scripts/validate_understanding.py` — 理解层存在性校验 v1（U1-U6，带第 1 期缺陷样本红灯，由 runner 串联强制，ADR-004）
- `scripts/daily_runner.py` — **每日心跳一条命令**（prepare=生成前发现+候选池 / verify=生成后校验+HTML；fatal 步失败非零退出指明炸哪步）；`scripts/multi_source/` — discover.py（v7 三引擎+生命周期）/collector/cleaner（含 v8 采中准入）/fusion/gate（G1-G7+official_primary）/leak_detector/value_score/health_check/gap_analyzer/prepare_candidates
- `scripts/build_report_html.py` + `report_viz/` — 视图 HTML 构建器；`archive_to_kb.py` — Obsidian 归档（`D:\我的知识库\07-芯片行业日报\`）
- `state/` — 跨日记忆与运行数据（report_state/signal_history/forecast_log/discovered_sources/gate_report 等）；`data/`（multi_source 下）是回归基线，online 抓取勿覆盖
- `.trae/skills/chip-daily-report/` — 镜像，须与根目录逐字节一致（X1/X2，`check_rules_consistency.py` 的 R1 段监督；同步一律 Read+Write，Bash 写源码/配置会被钩子拦）
- `.workbuddy/memory/MEMORY.md` — 项目长期约定与运行铁律的唯一权威（含用户画像、四条链路同步法）

## 当前状态（2026-09-27 护城河冲刺后）
- master = v7.1 + **v8 护城河冲刺（2026-09-26/27，已推送）**：心跳恢复 + 理解层门禁 + 采集准入 + 测试债清零 + 试产第 2 期
- **每日心跳已恢复**：`scripts/daily_runner.py`（`--stage prepare|verify`/`--all`，fatal 步失败非零退出指明炸哪步）+ 本 harness 定时任务 automation-fe364622（周一至五 08:00，工作日口径；删除方法=对 harness 说删除该 automation 或 CronDelete automation-fe364622-b7a5-4d6a-81de-e5650026c57d）；dry-run 全绿 9 步 exit 0（531s）；runner 只做机械链路，正文生成=定时会话按 SKILL.md 六步（ADR-002）
- **门禁族 = 26 项硬校验 + 理解层存在性校验**：`scripts/validate_understanding.py` v1（U1-U6：导师课/第一课非空/费曼节/推演块知识锚+成长含义+验证窗口）由 runner verify 串联强制，26 数不变（ADR-004）；带 9 个第 1 期缺陷样本回归红灯（tests/test_validate_understanding.py）
- **采中准入**：无文章级 URL 的候选不入池（cleaner.admit_article_level，口径同 [G-1]）+ gate G7 话题去重（overlap≥0.7 收窄网）+ G3 publisher_domain 消费（官方一手域标 official_primary，registry 运行时读取）——第 1 期「回填 9 处」成本归零的机制保证
- **测试真相（2026-09-27 实测）**：全量 pytest **196 passed + 0 failed**（历史首次全绿；--ignore 三脚本式测试后）；m1/m3 独立跑 ✓，m4_m5_m6 独立跑 1 败（状态依赖，ADR-003 记账不修）；跑 pytest 后照例 `git checkout --` 还原 state 污染
- **试产第 2 期（20260926）**：16 条全 72h 窗口、文章级 16/16（11 直链+6 gnews 分享链如实标注降级证据）、A 级 31.3%、26 门禁+理解层 exit 0；评审=主上下文自评（独立 critic 代理配额全程超限待补），自评判定「值得读」、P0=0、P1×3/P2×4 全部处置，全文见 `delivery/日报质量评审_20260926_第2期.md`
- **对标结论**（`delivery/对标报告_护城河_20260926.md`）：五论点判决——推演可问责/批评代谢=独占（开源零同类），诚实性工程=领先（最接近物 citation-check-skill 248★），教学层=独占（C 组搜索最高 5★），自主发现层=持平（TrendRadar 62.5k★/Horizon 9.5k★ 为规模天花板），心跳=持平（恢复后成立）。注意：本轮调研为 WebFetch 直读降级口径
- 台账：`delivery/迭代台账.md`（9 指标基线→终版，含 A 级占比负 delta 与 pytest 基线口径偏差的诚实注记）；交接：`delivery/会话交接_20260926.md`
- 已知债（更新）：①gnews 分享链 6 条未端到端验证+中文权威源直链化（下期优先）②A 级占比 31.3% 踩线（中文源域名定级走 rule_registry 通道）③m4_m5_m6 状态依赖 1 败 ④newsnow 自部署待拍板 ⑤「独立评审待补」——配额恢复会话补跑第 2 期独立评审 ⑥理解层 v2（语义一致性+课程清单 schema）未动
