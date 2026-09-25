#!/usr/bin/env python3
"""
check_rules_consistency.py —— 规则一致性校验（F2 硬门禁）

校验三组一致性，任一组不一致则退出码 1：
  [H1] 注册表 A级域名  <->  validate_report.py A_LEVEL_DOMAINS（双向差集=0）
  [H2] 注册表 A级域名  <->  sources.md A级来源表（双向差集=0）
  [H3] 脚本 A级域名    <->  sources.md A级来源表（双向差集=0）
  [H4] 注册表 C级域名  <->  validate_report.py C_LEVEL_DOMAINS（双向差集=0）
  [H5] 注册表 环节     <->  validate_report.py SEGMENTS（完全一致）

附加报告（不阻断，仅输出差异清单）：
  [R1] 根目录  <->  .trae 镜像 逐文件 diff（X1/X2：应全部一致）

用法：
  python check_rules_consistency.py
"""
import difflib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "rules" / "rule_registry.yaml"
SCRIPT = ROOT / "scripts" / "validate_report.py"
SOURCES = ROOT / "references" / "sources.md"
MIRROR = ROOT / ".trae" / "skills" / "chip-daily-report"

SOURCES_START = "<!-- GEN:ALEVEL:START -->"
SOURCES_END = "<!-- GEN:ALEVEL:END -->"


def load_registry():
    with open(REGISTRY, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_script_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("validate_report", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_sources_alevel_domains():
    """从 sources.md 的 A 级来源表（GEN 标记之间）解析域名集合。"""
    text = SOURCES.read_text(encoding="utf-8")
    i = text.find(SOURCES_START)
    j = text.find(SOURCES_END)
    if i == -1 or j == -1:
        raise RuntimeError("sources.md 未找到 A 级表 GEN 标记")
    block = text[i:i + (j - i)]
    domains = set()
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # 去掉首尾空 cell
        cells = [c for c in cells if c != ""]
        if len(cells) < 3:
            continue
        # 跳过表头与分隔行
        if cells[0] in ("来源",) or set(cells[0]) <= set("-: "):
            continue
        url = cells[2]
        parsed = urlparse(url)
        host = parsed.netloc.lower().lstrip("www.")
        if not host:
            continue
        domains.add(host)
    return domains


def diff_sets(a, b):
    """返回 (仅在a, 仅在b)。"""
    only_a = sorted(a - b)
    only_b = sorted(b - a)
    return only_a, only_b


def mirror_files():
    """返回 [(rel_path, root_file, mirror_file), ...]，遍历镜像目录映射到根目录。

    镜像只包含 skill 分发文件（SKILL.md / CLAUDE.md / agents / references / scripts），
    不含根目录的 .git、delivery、rules、治理脚本等，故以镜像为基准遍历。
    """
    pairs = []
    if not MIRROR.exists():
        return pairs
    for m in MIRROR.rglob("*"):
        if not m.is_file():
            continue
        rel = m.relative_to(MIRROR)
        rel_str = str(rel).replace("\\", "/")
        # 跳过镜像自身元数据
        if rel_str.startswith(".git/"):
            continue
        root_file = ROOT / rel
        pairs.append((rel_str, root_file, m))
    return pairs


def main():
    fails = 0
    reg = load_registry()
    reg_a = {d["domain"].lower() for d in reg["domains"]["a_level"]}
    reg_c = {d["domain"].lower() for d in reg["domains"]["c_level"]}
    reg_seg = [s for s in reg["segments"]]

    mod = load_script_module()
    script_a = {d.lower() for d in mod.A_LEVEL_DOMAINS}
    script_c = {d.lower() for d in mod.C_LEVEL_DOMAINS}
    script_seg = list(mod.SEGMENTS)

    sources_a = parse_sources_alevel_domains()

    # [H1] registry <-> script A
    oa1, ob1 = diff_sets(reg_a, script_a)
    if oa1 or ob1:
        fails += 1
        print(f"[FAIL][H1] 注册表 vs 脚本 A级域名 不一致")
        if oa1:
            print(f"        仅注册表有: {oa1}")
        if ob1:
            print(f"        仅脚本有:   {ob1}")
    else:
        print(f"[PASS][H1] 注册表↔脚本 A级域名 一致（{len(reg_a)} 个）")

    # [H2] registry <-> sources A
    oa2, ob2 = diff_sets(reg_a, sources_a)
    if oa2 or ob2:
        fails += 1
        print(f"[FAIL][H2] 注册表 vs sources.md A级域名 不一致")
        if oa2:
            print(f"        仅注册表有: {oa2}")
        if ob2:
            print(f"        仅sources.md有: {ob2}")
    else:
        print(f"[PASS][H2] 注册表↔sources.md A级域名 一致（{len(reg_a)} 个）")

    # [H3] script <-> sources A
    oa3, ob3 = diff_sets(script_a, sources_a)
    if oa3 or ob3:
        fails += 1
        print(f"[FAIL][H3] 脚本 vs sources.md A级域名 不一致")
        if oa3:
            print(f"        仅脚本有: {oa3}")
        if ob3:
            print(f"        仅sources.md有: {ob3}")
    else:
        print(f"[PASS][H3] 脚本↔sources.md A级域名 一致")

    # [H4] C level
    oc1, oc2 = diff_sets(reg_c, script_c)
    if oc1 or oc2:
        fails += 1
        print(f"[FAIL][H4] 注册表 vs 脚本 C级域名 不一致: 仅注册表{oc1} 仅脚本{oc2}")
    else:
        print(f"[PASS][H4] 注册表↔脚本 C级域名 一致（{len(reg_c)} 个）")

    # [H5] segments
    if reg_seg == script_seg:
        print(f"[PASS][H5] 注册表↔脚本 环节 一致: {reg_seg}")
    else:
        fails += 1
        print(f"[FAIL][H5] 环节不一致: 注册表{reg_seg} vs 脚本{script_seg}")

    # [R1] mirror diff (informational)
    print("\n[R1] 根目录 ↔ .trae 镜像 逐文件 diff：")
    diff_count = 0
    for rel_str, root_file, mirror_file in sorted(mirror_files()):
        if not root_file.exists():
            # 镜像独有文件（如 scripts/__init__.py），不属于根目录 skill，跳过
            continue
        r = root_file.read_text(encoding="utf-8", errors="ignore")
        m = mirror_file.read_text(encoding="utf-8", errors="ignore")
        if r == m:
            continue
        diff_count += 1
        # 简要报告差异行数
        rlines = r.splitlines()
        mlines = m.splitlines()
        sm = difflib.unified_diff(mlines, rlines, lineterm="", n=0)
        changed = sum(1 for l in sm if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
        print(f"      [差异] {rel_str}（约 {changed} 行不同）")
    if diff_count == 0:
        print("      [一致] 所有镜像文件与根目录逐字节一致 ✓")
    else:
        print(f"      [提示] 共 {diff_count} 个文件存在差异（同步镜像后应为 0；见 X1/X2）")

    print()
    if fails:
        print(f"✗ 一致性校验未通过：{fails} 项硬检查失败")
        sys.exit(1)
    else:
        print("✓ 全部硬一致性检查通过（X7 双向差集=0）")
        sys.exit(0)


if __name__ == "__main__":
    main()
