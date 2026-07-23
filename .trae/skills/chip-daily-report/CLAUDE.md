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
- `scripts/validate_report.py` — 硬约束校验脚本（Step 5 运行）
- `.trae/skills/chip-daily-report/` — TRAE 安装镜像，必须与根目录同步
- 日报产物命名：`芯片行业日报_YYYYMMDD.md`

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
- 版本：v5.0 专业深度版（微电子视角+技术解读+产业链关联）
- 对抗审查 35 个漏洞已全部修复，脚本覆盖 15/15 项 Rubric
- .trae 镜像需同步至 v5.0
