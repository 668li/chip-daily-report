#!/usr/bin/env python3
"""
gen_rules.py —— 规则注册表 -> 执行/业务双端生成器（F1.2）

唯一权威源 rules/rule_registry.yaml 同时向两处生成，保证 X7「双向差集=0」：
  1. scripts/validate_report.py  的 A/B/C 域名常量（执行权威）
  2. references/sources.md        的 A 级来源表（业务权威）

用法：
  python gen_rules.py            # 实际写入两处文件
  python gen_rules.py --check    # 仅打印将要生成的 diff 概要，不写盘

约束（X7）：
  - 两处均由注册表生成，禁止手工同步
  - 生成的脚本常量与 sources.md A 级表必须完全一致（由 check_rules_consistency.py 校验）
"""
import sys
from pathlib import Path

import yaml

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "rules" / "rule_registry.yaml"
SCRIPT = ROOT / "scripts" / "validate_report.py"
SOURCES = ROOT / "references" / "sources.md"

# sentinel 标记（必须在目标文件中存在，否则拒绝写入以防误改）
SCRIPT_START = "# === GEN:RULES:START ==="
SCRIPT_END = "# === GEN:RULES:END ==="
SOURCES_START = "<!-- GEN:ALEVEL:START -->"
SOURCES_END = "<!-- GEN:ALEVEL:END -->"


def load_registry():
    with open(REGISTRY, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gen_python_block(reg):
    """生成 validate_report.py 内的 A/B/C 域名常量块（含 SEGMENTS）。"""
    a = reg["domains"]["a_level"]
    c = reg["domains"]["c_level"]
    segs = reg["segments"]

    lines = []
    lines.append("# 以下域名常量由 rules/rule_registry.yaml 自动生成（F1.2），DO NOT EDIT")
    lines.append("# A级来源域名（只检查URL域名，不检查display text）")
    lines.append("A_LEVEL_DOMAINS = [")
    for item in a:
        lines.append(f"    '{item['domain']}',  # {item['name']}")
    lines.append("]")
    lines.append("")
    lines.append("# C级来源域名（精确匹配，禁止使用）")
    lines.append("C_LEVEL_DOMAINS = [")
    for item in c:
        lines.append(f"    '{item['domain']}',  # {item['name']}")
    lines.append("]")
    lines.append("")
    lines.append("# 产业链5环节（章节标题关键词）")
    lines.append("SEGMENTS = [" + ", ".join(repr(s) for s in segs) + "]")
    return "\n".join(lines) + "\n"


def gen_sources_table(reg):
    """生成 sources.md 的 A 级来源表（Markdown）。"""
    a = reg["domains"]["a_level"]
    rows = ["| 来源 | 类型 | 网址 | 适用环节 | 备注 |",
            "|------|------|------|----------|------|"]
    for item in a:
        name = item["name"]
        url = item["url"]
        seg = item.get("segment", "综合")
        note = item.get("note", "")
        rows.append(f"| {name} | 权威源 | {url} | {seg} | {note} |")
    return "\n".join(rows) + "\n"


def replace_between(text, start, end, new_block):
    """在 start/end 标记之间替换内容；标记缺失则抛错。"""
    i = text.find(start)
    j = text.find(end)
    if i == -1 or j == -1:
        raise RuntimeError(
            f"未找到 sentinel 标记（需要 {start!r} 与 {end!r}）。"
            "请先在目标文件中放置标记后再运行生成器。"
        )
    if j < i:
        raise RuntimeError("sentinel 标记顺序错误（END 在 START 之前）。")
    head = text[: i + len(start)]
    tail = text[j:]
    return head + "\n" + new_block + tail


def main():
    check_only = "--check" in sys.argv

    reg = load_registry()
    a_count = len(reg["domains"]["a_level"])
    c_count = len(reg["domains"]["c_level"])
    print(f"[gen_rules] 注册表加载成功：A级 {a_count} 域 / C级 {c_count} 域")

    py_block = gen_python_block(reg)
    md_table = gen_sources_table(reg)

    # ---- 1. validate_report.py ----
    script_text = SCRIPT.read_text(encoding="utf-8")
    new_script = replace_between(script_text, SCRIPT_START, SCRIPT_END, py_block)
    if check_only:
        print(f"[gen_rules][CHECK] 将更新 {SCRIPT.name} 的域名常量块（{a_count} 个 A 级 + {c_count} 个 C 级）")
    else:
        SCRIPT.write_text(new_script, encoding="utf-8")
        print(f"[gen_rules][WRITE] 已写入 {SCRIPT.name} 域名常量块")

    # ---- 2. sources.md ----
    sources_text = SOURCES.read_text(encoding="utf-8")
    new_sources = replace_between(sources_text, SOURCES_START, SOURCES_END, md_table)
    if check_only:
        print(f"[gen_rules][CHECK] 将更新 {SOURCES.name} 的 A 级来源表（{a_count} 行）")
    else:
        SOURCES.write_text(new_sources, encoding="utf-8")
        print(f"[gen_rules][WRITE] 已写入 {SOURCES.name} A 级来源表（{a_count} 行）")

    print("[gen_rules] 完成。请随后运行 check_rules_consistency.py 验证双向差集=0。")


if __name__ == "__main__":
    main()
