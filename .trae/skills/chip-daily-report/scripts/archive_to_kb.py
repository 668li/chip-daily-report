#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chip-daily-report → Obsidian 知识库归档脚本（迭代3，2026-08-09）。

把日报从"每天看完就散"沉淀为长期知识资产：

  1. 归档   日报 → <kb>/07-芯片行业日报/日报归档/YYYY/MM/芯片行业日报_YYYYMMDD.md
            （原样内容 + 前置 YAML frontmatter: date/segments，供 Obsidian dataview）
  2. MOC    按 5 环节提取每日要点 → <kb>/07-芯片行业日报/认知卡片/MOC-设计|制造|封测|EDA|材料.md
            （append-only，每日追加 `- YYYY-MM-DD | **标题** — 信号` 行）
  3. 索引   <kb>/07-芯片行业日报/索引.md（认知卡片链接 + 按月归档目录 + dataview 查询）

幂等双保险：
  a. 归档目标文件已存在 → 跳过复制（不覆盖）
  b. state/kb_archive_index.json 记录 {文件名: sha256}——同一日报二次运行：
     sha 匹配 → 整体跳过（MOC/索引都不重复追加）；sha 变化 → MOC 按行去重追加

fail-soft：KB 根目录不存在 → 打印跳过并 return 0（不阻塞 F4 链路）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # project root
INDEX_FILE = ROOT / "state" / "kb_archive_index.json"
KB_SUBDIR = "07-芯片行业日报"

SEGMENTS = ["设计", "制造", "封测", "EDA", "材料"]
# 日报环节小标题（X15 全称）→ MOC 文件后缀
SEG_HEADINGS = {
    "设计": "设计",
    "制造": "制造",
    "封测": "封测",
    "EDA / 工具": "EDA",
    "材料 / 设备": "材料",
}

TITLE_RE = re.compile(r"^#\s*芯片行业日报\s*[—-]\s*(\d{4}-\d{2}-\d{2})")
HEADING_RE = re.compile(r"^##\s+(.+)$")
NEWS_RE = re.compile(r"^-\s*\*\*(.+?)\*\*\s*—")
DATE_RE = re.compile(r"\|\s*(\d{4}-\d{2}-\d{2})\s*(\||$)")
SIGNAL_RE = re.compile(r"\|\s*信号:\s*([^\s|]+/[^\s|]+/[^\s|]+)")


# ============================================================
# 解析日报
# ============================================================
def parse_report(md: Path) -> dict:
    """解析日报 → {date, segments:[...], news:{MOC名: [(title, date, signal), ...]}}。"""
    text = md.read_text(encoding="utf-8")
    date = ""
    m = TITLE_RE.search(text)
    if m:
        date = m.group(1)
    # 文件名兜底：芯片行业日报_YYYYMMDD.md
    if not date:
        fm = re.search(r"_(\d{8})\.md$", md.name)
        if fm:
            d = fm.group(1)
            date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    # 环节小节扫描
    cur_moc = None
    news: dict[str, list] = {}
    segments: list[str] = []
    for line in text.splitlines():
        hm = HEADING_RE.match(line)
        if hm:
            cur_moc = SEG_HEADINGS.get(hm.group(1).strip())
            if cur_moc and cur_moc not in segments:
                segments.append(cur_moc)
            continue
        if cur_moc is None:
            continue
        nm = NEWS_RE.match(line.strip())
        if not nm:
            continue
        title = nm.group(1).strip()
        title = re.sub(r"^\[(回顾|译|独家)\]\s*", "", title)   # 剥离标签前缀，复盘行更干净
        dm = DATE_RE.search(line)
        sm = SIGNAL_RE.search(line)
        news.setdefault(cur_moc, []).append(
            (title, dm.group(1) if dm else date, sm.group(1) if sm else ""))
    return {"date": date, "segments": segments, "news": news, "text": text}


# ============================================================
# frontmatter
# ============================================================
def with_frontmatter(date: str, segments: list, source_name: str, text: str) -> str:
    seg_list = "[" + ", ".join(f'"{s}"' for s in segments) + "]"
    fm = (f"---\n"
          f"date: {date}\n"
          f"type: 芯片行业日报\n"
          f"segments: {seg_list}\n"
          f"source: {source_name}\n"
          f"---\n\n")
    return fm + text


# ============================================================
# MOC 认知卡片
# ============================================================
MOC_TEMPLATE = """# MOC — {seg}（环节认知卡片）

> 由 chip-daily-report 归档脚本自动追加。用于跨日复盘：该环节每天发生了什么、信号如何演变。

## 每日要点

"""


def moc_append(moc: Path, seg: str, rows: list[tuple]) -> int:
    """向 MOC 卡片追加每日要点行（append-only，行级幂等）。返回新增行数。"""
    if not moc.exists():
        moc.write_text(MOC_TEMPLATE.format(seg=seg), encoding="utf-8")
    lines = moc.read_text(encoding="utf-8").splitlines()
    existing = {ln.strip() for ln in lines if ln.strip().startswith("- ")}
    added = 0
    for title, date, signal in rows:
        sig = f" — 信号: {signal}" if signal else ""
        row = f"- {date} | **{title}**{sig}"
        if row not in existing:
            lines.append(row)
            added += 1
    if added:
        moc.write_text("\n".join(lines) + ("\n" if not lines[-1].endswith("\n") else ""), encoding="utf-8")
    return added


# ============================================================
# 索引
# ============================================================
INDEX_TEMPLATE = """# 芯片行业日报 · 知识库索引

> 由 archive_to_kb.py 自动维护（{created}）。日报归档到 `07-芯片行业日报/日报归档/YYYY/MM/`，要点沉淀到下方 5 张认知卡片。

## 认知卡片（MOC）

- [[MOC-设计]]
- [[MOC-制造]]
- [[MOC-封测]]
- [[MOC-EDA]]
- [[MOC-材料]]

## 日报归档

"""


def update_index(index: Path, date: str, month_dir_rel: str, file_name: str) -> bool:
    """索引不存在则创建；存在则按「月份小节 + 日报行」行级幂等追加。返回是否发生变更。"""
    if not index.exists():
        index.write_text(INDEX_TEMPLATE.format(created=date), encoding="utf-8")
    lines = index.read_text(encoding="utf-8").splitlines()
    ym = f"{date[:4]} 年 {int(date[5:7])} 月"
    month_heading = f"### {ym}"
    row = f"- [[{month_dir_rel}/{file_name}|{date}]]"
    if month_heading not in lines:
        lines.append("")
        lines.append(month_heading)
    if row not in lines:
        lines.append(row)
        index.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    return False


# ============================================================
# 幂等索引（state/kb_archive_index.json）
# ============================================================
def _load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ============================================================
# 主流程
# ============================================================
def run(report: Path, kb_root: Path, force: bool = False) -> int:
    # 兼容 str 与 Path 两种调用（SKILL.md / F4 定时任务按字符串路径调用）
    report = Path(report)
    kb_root = Path(kb_root)
    if not kb_root.exists():
        print(f"[archive_to_kb] 跳过：知识库根不存在 {kb_root}（fail-soft，不阻塞）")
        return 0
    if not report.exists():
        print(f"[archive_to_kb] 跳过：日报不存在 {report}")
        return 1

    parsed = parse_report(report)
    date = parsed["date"] or "unknown"
    y, m = (date.split("-")[0], date.split("-")[1]) if "-" in date else ("YYYY", "MM")
    kb_dir = kb_root / KB_SUBDIR
    archive_dir = kb_dir / "日报归档" / y / m
    cards_dir = kb_dir / "认知卡片"
    archive_dir.mkdir(parents=True, exist_ok=True)
    cards_dir.mkdir(parents=True, exist_ok=True)

    # ---- 幂等检查 ----
    meta = _load_index()
    file_name = report.name
    cur_sha = _sha256(parsed["text"])
    prev = meta.get(file_name)
    if prev and prev.get("sha256") == cur_sha and not force:
        print(f"[archive_to_kb] 幂等跳过：{file_name} 已归档（sha 匹配）")
        return 0

    # ---- 1. 归档（frontmatter + 原内容） ----
    target = archive_dir / file_name
    if target.exists() and not force:
        print(f"[archive_to_kb] 归档文件已存在，跳过复制（不覆盖）：{target.relative_to(kb_root)}")
    else:
        fm_text = with_frontmatter(date, parsed["segments"], file_name, parsed["text"])
        target.write_text(fm_text, encoding="utf-8")
        print(f"[archive_to_kb] 已归档 → {target.relative_to(kb_root)}")

    # ---- 2. MOC 追加 ----
    total_added = 0
    for seg in SEGMENTS:
        rows = parsed["news"].get(seg, [])
        if not rows:
            continue
        moc = cards_dir / f"MOC-{seg}.md"
        n = moc_append(moc, seg, rows)
        if n:
            total_added += n
            print(f"[archive_to_kb] MOC-{seg} 追加 {n} 条要点 → {moc.name}")
    if not total_added:
        print("[archive_to_kb] 5 张 MOC 均已含当日要点（无新增）")

    # ---- 3. 索引 ----
    index = kb_dir / "索引.md"
    month_rel = f"日报归档/{y}/{m}"
    update_index(index, date, month_rel, file_name)

    # ---- 记录幂等索引 ----
    meta[file_name] = {"sha256": cur_sha, "date": date, "segments": parsed["segments"]}
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="芯片行业日报 → Obsidian 知识库归档")
    ap.add_argument("--report", required=True, help="日报 md 路径")
    ap.add_argument("--kb-root", default="D:\\我的知识库", help="Obsidian 知识库根目录")
    ap.add_argument("--force", action="store_true", help="强制覆盖归档文件")
    args = ap.parse_args()
    return run(Path(args.report), Path(args.kb_root), force=args.force)


if __name__ == "__main__":
    sys.exit(main())
