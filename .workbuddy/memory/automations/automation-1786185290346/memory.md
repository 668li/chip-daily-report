# 周质量看板自动化（automation-1786185290346）

## 执行记录

### 2026-09-11 22:43 运行
- 命令：`C:/Users/李勇谚/AppData/Local/Programs/Python/Python312/python.exe scripts/quality_dashboard.py`（按铁律用 system Python 3.12）
- 结果：成功，Exit 0，生成 delivery/quality_dashboard.{md,html,json}
- 本期覆盖 12 期（20260720~20260910）。
- 关键结论：
  - 平均 A 级来源占比（计算值）= 64.7%
  - 5 环节全覆盖 = 12/12
  - X 信号：X11=2、X14=1、X15=1、X16=1
  - 数据完整性对账：仅 20260727 含「来源分级统计」小节（计算 72.7% vs 自述 33.3%，偏差 39.4% 标为偏差过大）——该期为早期 v4.0 格式，其余期已无独立统计小节，故系统性对账风险低，但历史单期存在重大偏差。
- 产物路径：delivery/quality_dashboard.md / .html / .json
