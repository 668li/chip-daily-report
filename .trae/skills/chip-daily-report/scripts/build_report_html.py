#!/usr/bin/env python3
"""
build_report_html.py — 芯片行业日报可视化 HTML 构建器（CLI 入口）。

用法：
  python build_report_html.py <日报md> [--out DIR]

  - 解析日报 md（report_viz.parser）
  - 按 VIEW_REGISTRY 装配所有视图（report_viz.build_report_html）
  - 输出单文件零依赖 HTML 到 --out（默认 delivery/）

新增可视化模块：在 report_viz/views/ 加一个 render(report)->str 的模块，
并在 report_viz/views/__init__.py 的 VIEW_REGISTRY 注册即可，本 CLI 与装配器零改动。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许以脚本或模块两种方式运行
sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_viz import build_from_file  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description="芯片行业日报可视化 HTML 构建器")
    ap.add_argument("report", help="日报 Markdown 文件路径（如 芯片行业日报_20260808.md）")
    ap.add_argument("--out", default=str(ROOT / "delivery"), help="输出目录（默认 delivery/）")
    args = ap.parse_args()

    src = Path(args.report)
    if not src.exists():
        print(f"[build] 找不到日报文件：{src}", file=sys.stderr)
        sys.exit(1)

    html_text = build_from_file(src)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = src.stem + ".html"
    out_path = out_dir / out_name
    out_path.write_text(html_text, encoding="utf-8")
    print(f"[build] 已生成 {out_path} （{len(html_text)} 字节）")


if __name__ == "__main__":
    main()
