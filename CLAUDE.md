# CLAUDE.md — chip-daily-report skill

## 定位
生成带来源与时间戳的芯片行业日报的 skill，覆盖设计/制造/封测/EDA/材料设备全产业链。读者唯一且明确：微电子大二学生勇谚——v6.0 起核心目标是「让他真正吸收」（黑话三档翻译 + 四层新闻写法 + 今日一课），不再是行业事实播报。

## 怎么跑
- 生成日报：skill 触发词（"芯片日报"等）启动 SKILL.md 六步流程（v4.0 起 10 步合并为 6 步 + Step 7 周度复盘）
- 校验日报：`C:/Users/李勇谚/AppData/Local/Programs/Python/Python312/python.exe scripts/validate_report.py <日报路径>`（退出码 0=26 项全过；一律用系统 Python 3.12，勿碰旧 venv）
- 跑测试：`<系统Python> -m pytest tests/ -q --ignore=tests/test_m1_crossvalidate.py --ignore=tests/test_m3_scenarios.py --ignore=tests/test_m4_m5_m6.py`（后三个是脚本式测试，独立跑 `python tests/test_mX.py`）
- ⚠ 跑 pytest 会污染真实 state（source_health.yaml / leak_report.* / 曾写 forecast_log.json）——跑完必须 `git checkout --` 还原这几个文件
- 规则治理：改域名/环节只改 `rules/rule_registry.yaml` → 跑 `scripts/gen_rules.py` → 跑 `scripts/check_rules_consistency.py`（X7 硬门禁）；**禁止手工同步**注册表↔脚本↔sources.md

## 技术栈
- Markdown（SKILL.md 主控 + references/ 知识库）+ Python 3.12（scripts/ 全部本地脚本，系统 Python 已装 pyyaml/pytest/defusedxml）
- 私有远端备份：`github.com/668li/chip-daily-report`（推送需走本机代理 127.0.0.1:7897，仓库级 git proxy 已配）

## 目录与约定（关键件）
- `SKILL.md` — 主控（v6.0 理解优先版草案）；`references/` — sources/classification/rubric/glossary/jargon_bridge（v6.0 黑话桥）/catalysts
- `scripts/validate_report.py` — 26 项硬校验（1218 行，Mimosa 安全加固后 0 finding）；`scripts/multi_source/` — collector/cleaner/fusion/gate/leak_detector/value_score/health_check/gap_analyzer/prepare_candidates（多为实验管线，daily 生产主要靠 LLM 搜索）
- `scripts/build_report_html.py` + `report_viz/` — 6 视图 HTML 构建器；`archive_to_kb.py` — Obsidian 归档（`D:\我的知识库\07-芯片行业日报\`）
- `state/` — 跨日记忆与运行数据（report_state/signal_history/forecast_log 等）；`data/`（multi_source 下）是回归基线，online 抓取勿覆盖
- `.trae/skills/chip-daily-report/` — 镜像，须与根目录逐字节一致（X1/X2，`check_rules_consistency.py` 的 R1 段监督）
- `.workbuddy/memory/MEMORY.md` — 项目长期约定与运行铁律的唯一权威（含用户画像、四条链路同步法）

## 当前状态（2026-09-25 洁癖收尾后）
- master = v5.13 + 安全加固（SSRF 白名单抓取/defusedxml/写入路径锚定，Mimosa 深扫 0 finding）+ v6.0 **理解优先版草案**（SKILL.md 写作层已实现、样例 26/26 过门禁+冷读 pass，**待用户拍板后才算启用**）
- v6.0 走「零门禁改动」路线：理解层全在写作层，validate_report.py 零改动；四条链路经实测确认无需改（parser 既有行为已兼容）；`scripts/validate_understanding.py` 为第二阶段规划占位，尚未创建
- 镜像已全量同步（X7 硬检查通过、R1 漂移清零）；改造产物在 `delivery/`（方案报告 / 规范 / 9-10 理解优先版样例）
- 自动化现状：**F4 每日生成已死**（原跑在 WorkBuddy，2026-09-10 后无产出），当前环境也无定时任务——日报停摆中
- 存量测试债（不阻塞）：pytest 4 个 weekly_review 失败（KeyError 'scenario_review'）；test_m4_m5_m6 独立跑 1 个状态依赖失败
- **待用户拍板**：① v6.0 落地启用（生成首期新格式日报）② 每日自动化在本环境重建（失败要响）③ multi_source 管线「真上线 or 归档」二选一 ④ 存量测试债是否修
