# CLAUDE.md — chip-daily-report skill

## 定位
生成带来源与时间戳的芯片行业日报的 skill，覆盖设计/制造/封测/EDA/材料设备全产业链。读者唯一且明确：微电子大二学生勇谚——v6.0 起核心目标是「让他真正吸收」（黑话三档翻译 + 四层新闻写法 + 今日一课），不再是行业事实播报。

## 怎么跑
- 生成日报：skill 触发词（"芯片日报"等）启动 SKILL.md 六步流程（v4.0 起 10 步合并为 6 步 + Step 7 周度复盘）；生成前先跑 `<系统Python> scripts/multi_source/discover.py --mode quick`（每周一 `full`）刷新发现层
- 校验日报：`C:/Users/李勇谚/AppData/Local/Programs/Python/Python312/python.exe scripts/validate_report.py <日报路径>`（退出码 0=26 项全过；一律用系统 Python 3.12，勿碰旧 venv）
- 跑测试：`<系统Python> -m pytest tests/ -q --ignore=tests/test_m1_crossvalidate.py --ignore=tests/test_m3_scenarios.py --ignore=tests/test_m4_m5_m6.py`（后三个是脚本式测试，独立跑 `python tests/test_mX.py`）
- ⚠ 跑 pytest 会污染真实 state（source_health.yaml / leak_report.*）——跑完必须 `git checkout --` 还原这几个文件（test_health_check 污染根因已于 v7 修复，但 leak_report 系仍会被写）
- 规则治理：改域名/环节只改 `rules/rule_registry.yaml` → 跑 `scripts/gen_rules.py` → 跑 `scripts/check_rules_consistency.py`（X7 硬门禁）；**禁止手工同步**注册表↔脚本↔sources.md
- 发现层运维：`discover.py --mode quick|full|status|rescore`——rescore 用于每次升级相关性门禁后对全池复判清洗；发现源人工定级唯一通道 = 录 rule_registry.yaml → gen_rules → X7

## 技术栈
- Markdown（SKILL.md 主控 + references/ 知识库）+ Python 3.12（scripts/ 全部本地脚本，系统 Python 已装 pyyaml/pytest/defusedxml）
- 私有远端备份：`github.com/668li/chip-daily-report`（推送需走本机代理 127.0.0.1:7897，仓库级 git proxy 已配）

## 目录与约定（关键件）
- `SKILL.md` — 主控（v6.2 现役：理解优先写作层 + 未来推演身份化）；`references/` — sources/classification/rubric/glossary/jargon_bridge（v6.0 黑话桥）/catalysts
- `scripts/validate_report.py` — 26 项硬校验（1218 行，Mimosa 安全加固后 0 finding）；`scripts/multi_source/` — **discover.py（v7 自主源发现层，三引擎+生命周期）**/collector/cleaner/fusion/gate/leak_detector/value_score/health_check/gap_analyzer/prepare_candidates（daily 生产 = LLM 搜索 + 发现层 active 池机器采集，gate 候选链路待接入）
- `scripts/build_report_html.py` + `report_viz/` — 6 视图 HTML 构建器；`archive_to_kb.py` — Obsidian 归档（`D:\我的知识库\07-芯片行业日报\`）
- `state/` — 跨日记忆与运行数据（report_state/signal_history/forecast_log 等）；`data/`（multi_source 下）是回归基线，online 抓取勿覆盖
- `.trae/skills/chip-daily-report/` — 镜像，须与根目录逐字节一致（X1/X2，`check_rules_consistency.py` 的 R1 段监督）
- `.workbuddy/memory/MEMORY.md` — 项目长期约定与运行铁律的唯一权威（含用户画像、四条链路同步法）

## 当前状态（2026-09-26 洁癖收尾后）
- master = v5.13 + 安全加固（Mimosa 深扫 0 finding）+ **v6.0/v6.1/v6.2 已落地**（46d7d02 试产第 1 期过 26 项门禁；77252ad 前瞻三词分立；25326cb 推演知识锚+成长含义）+ **v7 自主源发现层（106e311，2026-09-26 推送）**
- v7 发现层：discover.py 三引擎（Google News 中英 / OPML 种子 / newsnow）自动发现→四道验证（拒 HTML 壳/90 天新鲜度/相关性三条件含密度≥30%/重定向逐跳校验）→ Miniflux 式生命周期（candidate→trial→active，确定性 3 败冻结，瞬时失败不惩罚）；state/discovered_sources.json 已入库（每次运行更新属预期 git 噪音）；实测终池 6 active 全部密度≥0.30；collector online 6→16 源 + 动态白名单（trial/active 并入、www 变体互补），动态源 tier=4 走 gate G3 降级线
- 对抗审查四轮全部闭环（workflow 内 13 发现 9 修复 + 主会话第 4 轮 rescore 机制/密度门禁/www 变体/tomshardware http 重定向）；复盘见 `delivery/复盘_自主发现层_20260926.md`
- 自动化现状：**F4 每日生成已死**（原跑在 WorkBuddy，2026-09-10 后无产出），当前环境也无定时任务——日报停摆中（v7 的 quick 发现命令已可挂进每日流程，只差定时器）
- 存量测试债（不阻塞）：pytest 4 个 weekly_review 失败（KeyError 'scenario_review'）；test_m4_m5_m6 独立跑 1 个状态依赖失败
- **待用户拍板**：① 每日自动化在本环境重建（失败要响）② gate→日报候选链路接入日常生成（v7 只上线了发现+采集层）③ newsnow 自部署（公共实例已 403）④ 存量测试债是否修
- 已知债：gnews 中文组候选几乎全被 WAF 拒（国产链发现靠 cninfo+AIHOT 补）；publisher_domain 落盘但管线暂无消费点；`scripts/validate_understanding.py` 仍为规划占位
