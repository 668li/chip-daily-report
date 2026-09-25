#!/usr/bin/env python3
"""m5_rewrite_skill.py — M5 周度复盘自动反写（抗遗忘回路，P2）。

设计目标（见 references/evolution_plan.md M5）：
  把本周「学到的规律」自动 diff 进 SKILL.md 的「注意点」段——闭环：
  跑（M3 校准 / M4 规则生长 / 剧本复盘）→ 学（提炼信号）→ 改说明书 → 下次跑用新版。

输入（全部为已有产物，零新增采集）：
  - state/forecast_calibration.json  → M3 预判校准建议
  - state/rule_growth.json            → M4 规则自生长建议
  - state/forecast_log.json           → M5 剧本立场命中率（升级/淘汰信号）

输出：
  - 在 SKILL.md 的锚点段（## 自动沉淀的注意点（M5 抗遗忘回路））下，追加一条
     dated「规律沉淀」块；保留最近 N 条（默认 8），旧的就地裁剪，绝不改动其它内容。
  - 默认仅打印预览（human-in-loop）；--apply 才落盘。
fail-soft：任一输入缺失/损坏 → 该项标「无信号」，不阻塞。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"
ANCHOR = "## 自动沉淀的注意点（M5 抗遗忘回路）"
MAX_BLOCKS = 8

SECTION_TEMPLATE = """{anchor}

> 本段由 m5_rewrite_skill.py 自动追加（抗遗忘回路），保留最近 {max} 条规律沉淀；
> 人工可在此之上补充，脚本裁剪时只删最旧的 dated 块、不碰本说明与锚点之上内容。

"""


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def gather() -> dict:
    out = {"m3": [], "m4": [], "scenario": None}
    cal = _load(ROOT / "state" / "forecast_calibration.json")
    if cal:
        out["m3"] = cal.get("suggestions", []) or []
    rg = _load(ROOT / "state" / "rule_growth.json")
    if rg:
        out["m4"] = rg.get("suggestions", []) or []
    # 剧本立场信号
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from forecast_calibrator import calibrate

        log = _load(ROOT / "state" / "forecast_log.json")
        if log:
            r = calibrate(log)
            w = r.get("scenario_weights", {})
            active = {k: v for k, v in w.items() if v is not None}
            if active:
                best = max(active, key=active.get)
                worst = min(active, key=active.get)
                out["scenario"] = (
                    f"剧本命中率：升级信号=`{best}`({active[best]:.0%})；"
                    f"淘汰信号=`{worst}`({active[worst]:.0%})"
                )
    except Exception:
        pass
    return out


def _bullet_m3(sug: dict) -> str:
    if sug.get("kind") == "scenario":
        return f"剧本·{sug.get('stance')}：{sug.get('issue')}（{sug.get('recommendation','')[:60]}…）"
    return f"确定性·{sug.get('certainty')}：{sug.get('issue')}（{sug.get('recommendation','')[:60]}…）"


def build_block(data: dict, today: str) -> str:
    lines = [f"### 规律沉淀 · {today}", ""]
    # M3
    lines.append("- **预判校准（M3）**：")
    if data["m3"]:
        for s in data["m3"][:4]:
            lines.append(f"  - {_bullet_m3(s)}")
    else:
        lines.append("  - 本期无新校准建议（各档位偏差率/剧本命中率在合理区间）")
    # M4
    lines.append("- **规则自生长（M4）**：")
    if data["m4"]:
        for s in data["m4"][:4]:
            lines.append(f"  - #{s.get('num')} {s.get('name')}（{s.get('kind')}）：{s.get('recommendation','')[:70]}…")
    else:
        lines.append("  - 本期各规则 FAIL/WARN 频率均在阈值内，rubric 暂无需自生长")
    # M5 剧本
    lines.append("- **剧本复盘（M5）**：")
    lines.append(f"  - {data['scenario'] or '本期无互斥剧本数据'}")
    lines.append("")
    return "\n".join(lines)


def rewrite(skill: Path, block: str, max_blocks: int = MAX_BLOCKS) -> str:
    """把 block 插入 SKILL.md 锚点段下；裁剪最旧块。返回新全文。"""
    text = skill.read_text(encoding="utf-8")
    # 锚点按「独立标题行」匹配（(?m)^…$），避免误命中正文里引用锚点标题的行内文本
    m = re.search(r"(?m)^" + re.escape(ANCHOR) + r"[ \t]*$", text)
    if not m:
        # 锚点缺失：在文末补一段
        text = text.rstrip() + "\n\n" + SECTION_TEMPLATE.format(anchor=ANCHOR, max=max_blocks)
        m = re.search(r"(?m)^" + re.escape(ANCHOR) + r"[ \t]*$", text)
        if not m:
            raise RuntimeError("锚点段无法定位")
    # 切分锚点段：锚点行之后、下一个 '## ' 之前
    idx = m.start()
    head = text[: idx + len(ANCHOR)]
    rest = text[idx + len(ANCHOR):]
    # rest 里找下一个二级标题起点（作为段尾）
    m = re.search(r"\n## ", rest)
    if m:
        seg_body = rest[: m.start()]
        tail = rest[m.start():]
    else:
        seg_body = rest
        tail = ""
    # 收集已有 dated 块（以 '### 规律沉淀 ·' 开头）
    blocks = re.findall(r"### 规律沉淀 · .*?(?=\n### 规律沉淀 · |\Z)", seg_body, re.S)
    blocks = [b.strip() for b in blocks if b.strip()]
    # 同日去重：若已存在当天块，替换之（保证 M6 每日可重跑、不产生重复）
    day = block.splitlines()[0].replace("### 规律沉淀 · ", "").strip()
    blocks = [b for b in blocks if not b.startswith(f"### 规律沉淀 · {day}")]
    blocks.append(block.strip())
    # 裁剪最旧
    if len(blocks) > max_blocks:
        blocks = blocks[-max_blocks:]
    # 重建段体：说明 + 块
    intro_m = re.match(r"\n*>.*?\n", seg_body)
    intro = intro_m.group(0) if intro_m else "\n"
    new_seg = intro + "\n" + "\n\n".join(blocks) + "\n"
    return head + new_seg + tail


def main() -> int:
    ap = argparse.ArgumentParser(description="M5 自动反写 SKILL.md 注意点段（抗遗忘回路）")
    ap.add_argument("--apply", action="store_true", help="实际写入 SKILL.md（默认仅预览）")
    ap.add_argument("--max-blocks", type=int, default=MAX_BLOCKS)
    args = ap.parse_args()

    data = gather()
    today = date.today().isoformat()
    block = build_block(data, today)

    print("=== [M5 预览] 将写入 SKILL.md 的规律沉淀块 ===\n")
    print(block)
    print("\n--- 输入信号统计 ---")
    print(f"  M3 校准建议：{len(data['m3'])} 条")
    print(f"  M4 规则建议：{len(data['m4'])} 条")
    print(f"  M5 剧本信号：{data['scenario'] or '无'}")

    if not args.apply:
        print("\n（预览模式，未写入。加 --apply 落盘——非破坏性地追加到锚点段、保留最近"
              f" {args.max_blocks} 条）")
        return 0

    new_text = rewrite(SKILL, block, args.max_blocks)
    SKILL.write_text(new_text, encoding="utf-8")
    print(f"\n[M5] 已追加规律沉淀块到 {SKILL.name}（保留最近 {args.max_blocks} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
