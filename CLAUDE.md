# CLAUDE.md — chip-daily-report skill

## 定位
生成带来源与时间戳的芯片行业日报的 TRAE skill，覆盖设计/制造/封测/EDA/材料设备全产业链。面向微电子/IC专业读者，提供技术注解和产业链关联分析。

## 怎么跑
- 生成日报：用 skill 触发词（"芯片日报"/"chip industry daily report"）启动 6 步流程
- 校验日报：`python scripts/validate_report.py <日报文件路径>`（退出码 0=通过，1=有未通过项）
- 校验脚本是硬约束：日报必须通过 15/15 项检查才能输出

## 技术栈
- Markdown（SKILL.md 主控 + references/ 知识库 + 日报产物）
- Python 3（scripts/validate_report.py 可执行校验脚本，无第三方依赖）
- YAML（agents/openai.yaml Agent 行为配置）

## 目录与约定
- `SKILL.md` — 主控流程，始终加载
- `references/sources.md` — A/B/C 分级动态源库 + 学术会议源（Step 2 加载）
- `references/classification.md` — 产业链分类规则 + 存疑仲裁 + 学术突破分类（Step 3 加载）
- `references/rubric.md` — 15 项门禁检查标准（Step 5 加载）
- `scripts/validate_report.py` — 硬约束校验脚本（Step 5 运行，无第三方依赖）
- `rules/rule_registry.yaml` — **单一权威规则注册表（F1.1）**：A/B/C 域名、环节、关键词、X1–X16 裁决的唯一来源
- `scripts/gen_rules.py` — 从注册表生成脚本域名常量与 sources.md A 级表（F1.2，需 pyyaml）
- `scripts/check_rules_consistency.py` — 三端双向差集 + 镜像 diff 一致性校验（F2，需 pyyaml）
- `scripts/quality_dashboard.py` — 历史日报质量看板（F9 静态产物，扫描 `芯片行业日报_*.md`，按注册表分类来源 URL，聚合 A/B/C 占比、环节覆盖、X11/X14/X15/X16/X12 信号与「自述 vs 计算」数据对账，需 pyyaml；输出 `delivery/quality_dashboard.md` + `.json`）
- `scripts/multi_source/collector.py` — 多源采集适配器（迭代2 扩容）：online 模式 4 个免 key 真实源（SEC EDGAR + AIHOTCollector + SemiEngineering/EETimes RSS），单次采集 44-47 条，断网自动降级离线样例；`probe_online_sources()` 供健康度探针复用
- `scripts/multi_source/health_check.py` — 多源健康度监控（迭代1，需 pyyaml）：每源连通性探针 + 7 日可用率滑动窗口 + 连续失败累积（0→ok/1-2→degraded/≥3→down），fail-soft，输出 `state/source_health.yaml`
- `scripts/multi_source/value_score.py` — 多源量化价值分（迭代1，需 pyyaml）：5 指标加权合成 0-100 分（A级占比/独家线索/交叉验证/跨日主题延续/分歧数），同日幂等，输出 `state/value_score.json`
- `scripts/multi_source/report_viz.py` — 多源融合报告可视化（迭代1，零依赖）：事件卡片/漏聚候选/源覆盖矩阵/缺口清单，输出 `delivery/multi_source_report.html`
- `scripts/archive_to_kb.py` — Obsidian 知识库归档（迭代3）：日报 → `D:\我的知识库\07-芯片行业日报\`（日报归档/YYYY/MM + 5 张 MOC 认知卡片 append-only + 索引.md），幂等双保险（目标存在跳过 + `state/kb_archive_index.json` sha 校验），KB 根不存在跳过不 FAIL
- `scripts/signal_history.py` — 信号历史累积（迭代5，需 pyyaml）：读 report_state.yaml 当日追踪主题快照 → `state/signal_history.json`（幂等同日覆盖，fail-soft），信号强度曲线/周度复盘的累积数据源
- `scripts/weekly_review.py` — 周度复盘聚合器（迭代5）：聚合本周日报 + 信号历史 + 质量看板 → `delivery/芯片行业周度复盘_YYYYMMDD.md/.html`（概览/主线/信号演进台账+固定量纲曲线/认知素材/风险/催化剂），洞察区留 AI 润色
- `state/signal_history.json` — 信号历史累积数组（日期×主题×方向×streak×信号），signal_history.py 幂等维护
- `tests/test_x_decisions.py` — X1–X16 裁决回归用例（F3，需 pytest）
- `tests/test_quality_dashboard.py` — 看板解析器回归用例（F9，需 pytest）
- `tests/test_collector_sources.py` — 迭代2 数据源适配器回归用例（AIHOT 契约/RSS 解析/环节猜测/探针 fail-soft，需 pytest）
- `tests/test_archive_to_kb.py` — 迭代3 Obsidian 归档回归用例（幂等双保险/frontmatter/MOC 行数/fail-soft，需 pytest）
- `.trae/skills/chip-daily-report/` — TRAE 安装镜像，须与根目录同步（X1/X2）
- 日报产物命名：`芯片行业日报_YYYYMMDD.md`
- 质量看板产物：`delivery/quality_dashboard.md` + `delivery/quality_dashboard.json`

## 核心约束
- 来源级别判定基于 URL 域名，不依赖 display text（防注入攻击）
- A 级来源占比 ≥ 30%，C 级禁止
- 摘要 3-5 句（80-150 字），含技术维度，≥7 句 FAIL
- 涉及专业术语的新闻必须添加 `[技术注解: xxx]` 标签
- 必须包含 `## 产业链关联` 小节（≥2 组上下游关联分析）
- 超 72 小时新闻标注 [回顾]
- 无附录越界（不设"市场动态"等）
- 自检结果必须显式列出 15 项 PASS/FAIL

## 当前状态
- 版本：v5.1（规则治理核心落地：单一权威注册表 + 生成器 + 一致性校验 + 回归用例）
- 对抗审查 35 个漏洞已全部修复，脚本覆盖 15/15 项 Rubric + 4 项 X12/X14/X15/X16 软指标检查
- A 级域名共 44 个，由 `rules/rule_registry.yaml` 单一注册表经 `gen_rules.py` 生成，注册表↔脚本↔sources.md 双向差集=0（X7）
- `.trae` 镜像已与根目录同步（8 个 skill 文件逐字节一致，X2 裁决：仅历史版本 `validate_report.py` 域名常量曾待同步，现已对齐）
- F4 定时生成已落地为 **WorkBuddy 自身定时任务**（`automation-1786184607023`：周一至周五 08:00，非交互生成→校验→最多 5 次修正→中文汇报），为本环境真正可跑的等价实现
- F9 质量看板已落地为 **静态产物**（`scripts/quality_dashboard.py` → `delivery/quality_dashboard.md/.json`），扫描历史日报聚合质量指标，并做「报告自述 vs URL 计算」来源占比对账
- **multi_source 三件套（迭代1，2026-08-09）**：健康度 `state/source_health.yaml` + 量化价值分 `state/value_score.json` + 多源融合报告 `delivery/multi_source_report.html`，生成日报后顺带运行（任一步失败不阻塞交付，fail-soft）
- **数据源扩容（迭代2，2026-08-09）**：collector online 模式 4 个免 key 真实源（SEC/AIHOT/SemiEngineering/EE Times）；AIHOT 从线索升级为正式适配器；fusion.py 锚词回写（contractprice/q2/2q26）让存储价格双源漏聚修复；测试 73→82
- **Obsidian 知识库打通（迭代3，2026-08-09）**：`scripts/archive_to_kb.py` 归档日报到 `D:\我的知识库\07-芯片行业日报\`（日报归档 + 5 张 MOC 认知卡片 + 索引，幂等双保险 + fail-soft）；20260809 已正式归档（7 文件）；测试 82→91
- **认知深化（迭代5，2026-08-09）**：`scripts/signal_history.py` 每日累积追踪主题快照 → `state/signal_history.json`；`scripts/weekly_review.py` 周五聚合生成周度复盘 md+html（固定量纲信号强度曲线，⚠ 反转标记），SKILL.md 新增 Step 7，F4 已接入（每日累积 + 周五复盘）；20260809 周度复盘已生成（2 期/4 主题，HBM up→down 反转可视化）；测试 91→113
- F6+F14 等价：每日任务内校验闭环，校验结论即告警进收件箱；历史日报跑新校验器不崩溃（X15/X16 正确 WARN，硬检查仍全过）
- F5 LangGraph 编排 / F8 独立控制台 原服务形态在本环境不可行（web_search/web_fetch 为 agent 工具，非独立 HTTP 接口）；skill 的 6 步流程即编排，WorkBuddy 界面即控制台
- **待办**：生成每日报告后顺带刷新质量看板（看板扫描历史文件，可周级或每次生成后跑 `quality_dashboard.py`）
