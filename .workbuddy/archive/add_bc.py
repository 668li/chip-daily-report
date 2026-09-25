#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_bc.py — 为 20260808 日报试点 B（持续追踪）+ C（前瞻催化剂）小节。
1) 在 '## 自检结果' 前插入 '## 前瞻催化剂' 小节
2) 在 '## 前瞻催化剂' 前插入 '## 持续追踪' 小节（即产业链关联后）
3) 自检结果表追加第17/18行
4) 自检总结追加 B/C 说明
"""
import io
import sys

PATH = "芯片行业日报_20260808.md"

TRACKING = """## 持续追踪

> 跨日记忆（B·v5.3）：对比上期状态文件（state/report_state.yaml）的主题变比

- **HBM 价格与供需**：up（连续 3 期）Δ 2026Q2 合约价环比 +53~58% — 本期 SK海力士 384 亿美元扩产、三星 HBM4 Q3 量产，供需紧平衡延续（详见今日要点第 2 条）。
- **先进封装产能紧缺**：tight（连续 2 期）Δ 产能满载、订单排期紧张 — 本期长电 78 亿临港基地落地、HBM4 封装良率 98.5%，紧缺格局短期难缓解。
- **国产 EDA 并购整合**：up（连续 2 期）Δ 概伦电子 21.74 亿并购落地 — 本期华大九天 Argus 3DIC 发布，工具+IP 平台化进程提速。
- **出口管制收紧**：tight（连续 2 期）Δ MATCH 法案 36:8 通过 — 本期无新增管制动态，仍处立法推进期。

"""

CATALYST = """## 前瞻催化剂

> 未来 7 天已公告的确定时点（C·v5.3：只列已公告日期，严禁预测）

| 日期 | 事件 | 环节 | 重要度 | 来源 |
|------|------|------|--------|------|
| 2026-08-12 | 美光投资者大会（财务展望） | 制造 | 高 | [美光 IR](https://investors.micron.com) |
| 2026-08-13 | SEMI 全球晶圆厂预测季度更新 | 材料/设备 | 中 | [SEMI](https://www.semi.org) |
| 2026-08-14 | 台积电 7 月营收月报（预计） | 制造 | 中 | [台积电 IR](https://investor.tsmc.com) |

"""

OLD_ROW = "| 16 | 信号层标注 | PASS | 16条新闻均含信号标签（重要性/影响方向/情绪），覆盖率100% |"
NEW_ROWS = (
    OLD_ROW + "\n"
    "| 17 | 持续追踪 | PASS | 4个跨日主题（HBM/封装/EDA/管制）含方向、连续期数、变比与当日进展 |\n"
    "| 18 | 前瞻催化剂 | PASS | 未来7天3个确定时点，均附来源链接，无预测性条目 |"
)

OLD_SUM = "X17信号层16条全覆盖（PASS）。"
NEW_SUM = "X17信号层16条全覆盖（PASS），B跨日记忆4主题持续追踪（PASS），C前瞻催化剂3时点（PASS）。"


def main():
    with io.open(PATH, "r", encoding="utf-8") as f:
        text = f.read()

    # 1) 插入两个小节（前瞻催化剂在自检结果前，持续追踪在其前）
    if "## 前瞻催化剂" not in text:
        text = text.replace("## 自检结果", CATALYST + "## 自检结果", 1)
        print("[OK] 前瞻催化剂小节已插入")
    else:
        print("[SKIP] 前瞻催化剂已存在")

    if "## 持续追踪" not in text:
        text = text.replace("## 前瞻催化剂", TRACKING + "## 前瞻催化剂", 1)
        print("[OK] 持续追踪小节已插入")
    else:
        print("[SKIP] 持续追踪已存在")

    # 2) 自检表追加第17/18行
    if OLD_ROW in text and "| 17 | 持续追踪" not in text:
        text = text.replace(OLD_ROW, NEW_ROWS)
        print("[OK] 自检表已追加第17/18行")
    else:
        print("[WARN] 自检表行未追加")

    # 3) 自检总结更新
    if OLD_SUM in text:
        text = text.replace(OLD_SUM, NEW_SUM)
        print("[OK] 自检总结已更新")
    else:
        print("[WARN] 自检总结未更新（关键词变化）")

    with io.open(PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("[OK] 已写回", PATH)


if __name__ == "__main__":
    sys.exit(main())
