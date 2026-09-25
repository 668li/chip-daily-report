#!/usr/bin/env python3
"""generate_report — M2 生成流水线：IR JSON → 前置校验 → 渲染 md → (可选)HTML/校验。

用法：
  python generate_report.py ir.json --out 芯片行业日报_YYYYMMDD.md [--html] [--validate] [--force]

流程（与 SKILL.md「M2 生成范式」一致）：
  1. 读取 IR JSON（LLM 直出，或 parse_report 产出）
  2. validate_ir 前置校验（字段级 26 项）：有 FAIL 且非 --force → 退出不落盘
  3. render_markdown(report) 渲染为 Markdown（唯一真相源 IR → 校验对象 md）
  4. 写入 --out 的 md 文件
  5. --validate：对渲染 md 跑 validate_report.py（最终文本安全网，交叉验证）
  6. --html：build_report_html(report) 直接出 HTML（不经过正则 parser）

设计：IR 是唯一真相源；md 与 HTML 都是它的序列化形态；validate_ir 是门禁、
validate_report 是兜底。任一步失败都不阻塞交付（fail-soft），但 FAIL 会显式报出。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_renderer import render_markdown  # noqa: E402
from validate_ir import validate  # noqa: E402


def build_html(report: dict, out_dir: Path, name_stem: str) -> str:
    from report_viz import build_report_html
    html = build_report_html(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (name_stem + ".html")
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def main():
    ap = argparse.ArgumentParser(description="M2 生成流水线：IR JSON → md/HTML")
    ap.add_argument("ir", help="IR JSON 文件路径")
    ap.add_argument("--out", required=True, help="输出 md 路径（如 芯片行业日报_20260818.md）")
    ap.add_argument("--html", action="store_true", help="同时生成 HTML（直接消费 IR，不过正则 parser）")
    ap.add_argument("--html-out", default=str(ROOT / "delivery"), help="HTML 输出目录（默认 delivery/）")
    ap.add_argument("--validate", action="store_true", help="渲染后跑 validate_report.py 做文本安全网交叉验证")
    ap.add_argument("--cross-validate", action="store_true",
                    help="M1 来源交叉验证：打印事实三角验证 verdict（advisory）")
    ap.add_argument("--apply-cross", action="store_true",
                    help="配合 --cross-validate：将单源 A 级新闻降 B + 标待核实（仅新生成报告用）")
    ap.add_argument("--force", action="store_true", help="即使前置校验有 FAIL 也强制落盘")
    args = ap.parse_args()

    ir_path = Path(args.ir)
    report = json.loads(ir_path.read_text(encoding="utf-8"))

    # 2. 前置校验
    rows, n_fail, n_warn = validate(report)
    print("=== [M2 前置校验] validate_ir ===")
    for num, name, res, note in rows:
        mark = "✓" if res == "PASS" else ("⚠" if res == "WARN" else "✗")
        print(f"  {mark} {num:>2} {name}: {note}")

    # 2.5 M1 来源交叉验证（事实三角验证）
    if args.cross_validate:
        from cross_validate import cross_validate, apply_downgrades

        ver = cross_validate(report)
        print("\n=== [M1 来源交叉验证] ===")
        print(f"  跨源核验通过: {ver['cross_validated']} | 待核实: {ver['needs_verification']} "
              f"| 单源: {ver['single_source']} / 多源: {ver['multi_source']}")
        if args.apply_cross:
            apply_downgrades(report, ver)
            print("  [apply] 单源 A 已降 B + 标待核实，渲染将反映降级")
        else:
            print("  （advisory，未改 IR；加 --apply-cross 可落地下调）")
    print(f"  汇总：FAIL {n_fail} / WARN {n_warn}")
    if n_fail and not args.force:
        print(f"\n[generate] 前置校验有 {n_fail} 项 FAIL，已中止落盘（用 --force 可强制）。", file=sys.stderr)
        sys.exit(1)

    # 3. 渲染 md
    md = render_markdown(report)
    out_md = Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    print(f"\n[generate] 已渲染 md → {out_md} （{len(md)} 字节）")

    # 5. 文本安全网
    if args.validate:
        vpy = ROOT / "scripts" / "validate_report.py"
        r = subprocess.run([sys.executable, str(vpy), str(out_md)],
                           capture_output=True, text=True)
        print("=== [安全网] validate_report.py ===")
        print(r.stdout)
        if r.stderr:
            print(r.stderr)
        if r.returncode != 0:
            print("[generate] 警告：文本安全网校验未通过（FAIL），请检查。", file=sys.stderr)

    # 6. HTML
    if args.html:
        stem = Path(args.out).stem
        hp = build_html(report, Path(args.html_out), stem)
        print(f"[generate] 已生成 HTML → {hp}")

    print("\n[generate] 完成。")


if __name__ == "__main__":
    main()
