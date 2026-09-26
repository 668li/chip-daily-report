#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_understanding — 理解层存在性校验 v1（v8 护城河冲刺 P0-B，2026-09-26）。

定位（ADR-004）：与 validate_report.py（26 项硬校验）串联组成门禁族——
本脚本只做「理解层结构存在性」校验，语义一致性（知识锚↔已修课程匹配）明确划 v2。

v1 检查项（全部 FAIL 级）：
  U1 今日导师课节存在（## 今日导师课）
  U2 深度第一课非空（### 深度第一课 有正文，≥50 字）
  U3 费曼解释节存在且至少 1 条术语（## 费曼解释 + ≥1 个 `- ` 条目）
  U4 每个推演块（### 推演 N）含非空 知识锚（v6.2 身份化两要素之一）
  U5 每个推演块含非空 成长含义（身份化两要素之二，落点必须给动作）
  U6 每个推演块含非空 验证窗口（可对账前提）

用法：python scripts/validate_understanding.py <日报md路径>
退出码：0=全过；1=存在 FAIL；2=文件不可读。
不追溯历史期：只对当期新日报要求（runner verify 串联调用）。
回归红灯：tests/test_validate_understanding.py 从试产第 1 期构造缺锚缺陷样本
（临时副本，不碰真实历史文件），本脚本必须对它 FAIL。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MIN_LESSON_CHARS = 50

U_CHECKS = [
    ("U1", "今日导师课节存在"),
    ("U2", "深度第一课非空"),
    ("U3", "费曼解释节存在且有术语条目"),
    ("U4", "推演块含知识锚"),
    ("U5", "推演块含成长含义"),
    ("U6", "推演块含验证窗口"),
]


def _sections(text: str) -> dict[str, str]:
    """按 `## ` 切节：{节名: 节正文（含 ### 子节）}。"""
    secs: dict[str, str] = {}
    cur = "_head"
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("###"):
            secs[cur] = "\n".join(buf)
            cur = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    secs[cur] = "\n".join(buf)
    return secs


def _subsections(body: str) -> dict[str, str]:
    """节内按 `### ` 切子节。"""
    subs: dict[str, str] = {}
    cur = "_body"
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("### "):
            subs[cur] = "\n".join(buf)
            cur = line[4:].strip()
            buf = []
        else:
            buf.append(line)
    subs[cur] = "\n".join(buf)
    return subs


def validate_text(text: str) -> list[tuple[str, str, str]]:
    """返回 [(编号, 描述, PASS/FAIL+原因)]；供脚本与 pytest 复用。"""
    rows: list[tuple[str, str, str]] = []
    secs = _sections(text)

    lesson = next((s for name, s in secs.items() if "今日导师课" in name), None)
    rows.append(("U1", U_CHECKS[0][1], "PASS" if lesson is not None else "FAIL 无「## 今日导师课」节"))

    if lesson is not None:
        subs = _subsections(lesson)
        first = next((s for name, s in subs.items() if "深度第一课" in name), None)
        body = re.sub(r"\s", "", first or "")
        if first is None:
            rows.append(("U2", U_CHECKS[1][1], "FAIL 缺「### 深度第一课」子节"))
        elif len(body) < MIN_LESSON_CHARS:
            rows.append(("U2", U_CHECKS[1][1], f"FAIL 正文仅 {len(body)} 字（<{MIN_LESSON_CHARS}，疑似占位）"))
        else:
            rows.append(("U2", U_CHECKS[1][1], f"PASS 正文 {len(body)} 字"))
    else:
        rows.append(("U2", U_CHECKS[1][1], "FAIL 无导师课节可查"))

    feynman = next((s for name, s in secs.items() if "费曼解释" in name), None)
    if feynman is None:
        rows.append(("U3", U_CHECKS[2][1], "FAIL 无「## 费曼解释」节"))
    else:
        n_items = len(re.findall(r"^\s*-\s+\*\*", feynman, re.M))
        if n_items < 1:
            rows.append(("U3", U_CHECKS[2][1], "FAIL 费曼节 0 条术语条目"))
        else:
            rows.append(("U3", U_CHECKS[2][1], f"PASS {n_items} 条术语"))

    blocks: list[tuple[str, str]] = []
    cur: tuple[str, list[str]] | None = None
    for line in text.splitlines():
        if line.startswith("### 推演"):
            if cur:
                blocks.append((cur[0], "\n".join(cur[1])))
            cur = (line.strip().lstrip("# ").strip(), [])
        elif cur is not None:
            if line.startswith("### ") or line.startswith("## "):
                blocks.append((cur[0], "\n".join(cur[1])))
                cur = None
            else:
                cur[1].append(line)
    if cur:
        blocks.append((cur[0], "\n".join(cur[1])))

    for code, desc in U_CHECKS[3:6]:
        marker = {"U4": "知识锚", "U5": "成长含义", "U6": "验证窗口"}[code]
        if not blocks:
            rows.append((code, desc, "FAIL 全文无推演块（### 推演 N）"))
            continue
        missing = []
        empty = []
        for title, body in blocks:
            m = re.search(rf"\*\*{marker}\*\*[：:](.*)", body)
            if m is None:
                missing.append(title)
            elif not m.group(1).strip():
                empty.append(title)
        if missing:
            rows.append((code, desc, f"FAIL {len(missing)}/{len(blocks)} 块缺「{marker}」: {missing[0][:40]}"))
        elif empty:
            rows.append((code, desc, f"FAIL {len(empty)}/{len(blocks)} 块「{marker}」为空: {empty[0][:40]}"))
        else:
            rows.append((code, desc, f"PASS {len(blocks)}/{len(blocks)} 块齐备"))
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python scripts/validate_understanding.py <日报md路径>")
        return 2
    path = Path(sys.argv[1])
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[understanding] ✗ 文件不可读: {e}")
        return 2

    print(f"[understanding] 理解层存在性校验 v1 — {path.name}")
    n_fail = 0
    for code, desc, verdict in validate_text(text):
        mark = "✓ PASS" if verdict.startswith("PASS") else "✗ FAIL"
        if verdict.startswith("FAIL"):
            n_fail += 1
        print(f"  {mark}  [{code}] {desc} — {verdict}")
    if n_fail:
        print(f"[understanding] ✗ {n_fail} 项 FAIL —— 理解层结构缺失，按 v6.2 规范补齐后重校")
        return 1
    print("[understanding] ✓ 全部通过（结构存在性；语义一致性归 v2）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
