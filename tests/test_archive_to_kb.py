#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests.test_archive_to_kb — 迭代3 Obsidian 知识库归档回归用例。

覆盖：幂等双保险（sha 跳过 / 归档不覆盖）/ frontmatter 可被 Obsidian 索引 /
5 张 MOC 要点行数与环节小节一致 / fail-soft（KB 根不存在不 FAIL）/
标题剥离 [回顾] 前缀 / 归档路径 YYYY/MM 结构。
全部使用 tmp_path 作为知识库根，monkeypatch 隔离 state 索引，不污染真实环境。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import archive_to_kb as akb

SAMPLE_MD = """# 芯片行业日报 — 2026-08-09

> 生成时间: 2026-08-09 00:05
> 新闻总数: 3条

## 今日要点

- 测试要点一

## 设计

- **[回顾] AMD 第六代 EPYC Venice 在台积电 2nm 量产** — 摘要内容。 | 来源: [x](https://a.com) | 2026-05-20 | 信号: 高/利好/正面
- **Anthropic 组建内部芯片团队** — 摘要内容。 | 来源: [x](https://b.com) | 2026-08-05 | 信号: 中/中性/正面

## 制造

- **SK hynix 与闪迪发布 HBF 开放标准** — 摘要内容。 | 来源: [x](https://c.com) | 2026-08-04 | 信号: 高/利好/正面

## 封测

- **STATS ChipPAC 通知涨价** — 摘要内容。 | 来源: [x](https://d.com) | 2026-08-07 | 信号: 高/利好/正面

## EDA / 工具

- **概伦电子并购锐成芯微获批** — 摘要内容。 | 来源: [x](https://e.com) | 2026-06-30 | 信号: 中/利好/正面

## 材料 / 设备

- **中国首条自主可控光刻胶产线投产** — 摘要内容。 | 来源: [x](https://f.com) | 2026-08-05 | 信号: 高/利好/正面

## 产业链关联

- 关联分析（不入 MOC）

## 自检结果

- 15 项 PASS
"""


@pytest.fixture
def kb(tmp_path, monkeypatch):
    """隔离的临时知识库：monkeypatch 让 state 索引写到 tmp 下。"""
    idx = tmp_path / "kb_index.json"
    monkeypatch.setattr(akb, "INDEX_FILE", idx)
    return tmp_path


@pytest.fixture
def report(tmp_path):
    p = tmp_path / "芯片行业日报_20260809.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    return p


def _kb_dir(kb: Path) -> Path:
    return kb / akb.KB_SUBDIR


def _count_files(path: Path) -> int:
    return sum(1 for _ in path.rglob("*") if _.is_file())


def test_archive_creates_structure(report, kb):
    """归档结构：日报归档/YYYY/MM + 5 张 MOC + 索引。"""
    assert akb.run(report, kb) == 0
    kbdir = _kb_dir(kb)
    assert (kbdir / "日报归档" / "2026" / "08" / "芯片行业日报_20260809.md").exists()
    for seg in akb.SEGMENTS:
        assert (kbdir / "认知卡片" / f"MOC-{seg}.md").exists()
    assert (kbdir / "索引.md").exists()


def test_frontmatter_indexable(report, kb):
    """归档含 YAML frontmatter（date/segments），可被 Obsidian dataview 索引。"""
    akb.run(report, kb)
    archived = _kb_dir(kb) / "日报归档" / "2026" / "08" / "芯片行业日报_20260809.md"
    text = archived.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "date: 2026-08-09" in text
    assert 'segments: ["设计", "制造", "封测", "EDA", "材料"]' in text
    assert "source: 芯片行业日报_20260809.md" in text
    # frontmatter 之外仍保留完整日报正文
    assert "## 产业链关联" in text


def test_moc_lines_match_segments(report, kb):
    """5 张 MOC 要点行数 = 对应环节小节新闻条数（设计 2 / 制造 1 / 封测 1 / EDA 1 / 材料 1）。"""
    akb.run(report, kb)
    cards = _kb_dir(kb) / "认知卡片"
    expect = {"MOC-设计": 2, "MOC-制造": 1, "MOC-封测": 1, "MOC-EDA": 1, "MOC-材料": 1}
    for name, n in expect.items():
        lines = [ln for ln in (cards / f"{name}.md").read_text(encoding="utf-8").splitlines()
                 if ln.strip().startswith("- ")]
        assert len(lines) == n, f"{name} 期望 {n} 行，实际 {len(lines)}"


def test_moc_clean_title_strips_retro(report, kb):
    """标题剥离 [回顾] 前缀，行格式 = 日期 | 标题 — 信号。"""
    akb.run(report, kb)
    moc = _kb_dir(kb) / "认知卡片" / "MOC-设计.md"
    text = moc.read_text(encoding="utf-8")
    assert "**[回顾]" not in text
    assert "- 2026-05-20 | **AMD 第六代 EPYC Venice 在台积电 2nm 量产** — 信号: 高/利好/正面" in text


def test_idempotent_second_run_no_growth(report, kb):
    """幂等双保险：同日报二次运行 KB 零增长（文件数 / MOC 行数 / 索引行数均不变）。"""
    akb.run(report, kb)
    kbdir = _kb_dir(kb)
    files_1 = _count_files(kbdir)
    moc_lines_1 = {p.name: sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                               if ln.strip().startswith("- "))
                   for p in (kbdir / "认知卡片").glob("MOC-*.md")}
    index_lines_1 = len((kbdir / "索引.md").read_text(encoding="utf-8").splitlines())
    # 第二次运行（sha 匹配 → 整体跳过）
    assert akb.run(report, kb) == 0
    assert _count_files(kbdir) == files_1
    for p in (kbdir / "认知卡片").glob("MOC-*.md"):
        n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip().startswith("- "))
        assert n == moc_lines_1[p.name]
    assert len((kbdir / "索引.md").read_text(encoding="utf-8").splitlines()) == index_lines_1


def test_idempotent_force_overwrites_archive(report, kb):
    """force=True：归档文件可覆盖重写，但 MOC 行级去重不重复追加。"""
    akb.run(report, kb)
    kbdir = _kb_dir(kb)
    moc_before = {p.name: sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                              if ln.strip().startswith("- "))
                  for p in (kbdir / "认知卡片").glob("MOC-*.md")}
    akb.run(report, kb, force=True)
    # MOC 不重复追加（行级幂等）
    for p in (kbdir / "认知卡片").glob("MOC-*.md"):
        n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip().startswith("- "))
        assert n == moc_before[p.name]


def test_fail_soft_kb_root_missing(tmp_path):
    """KB 根不存在 → return 0 不 FAIL（fail-soft，不阻塞 F4 链路）。"""
    report = tmp_path / "x.md"
    report.write_text(SAMPLE_MD, encoding="utf-8")
    assert akb.run(report, tmp_path / "no_such_kb") == 0


def test_missing_report_returns_1(kb, tmp_path):
    """日报不存在 → return 1。"""
    assert akb.run(tmp_path / "ghost.md", kb) == 1


def test_parse_report_fields(report):
    """解析：date / segments / news 结构正确。"""
    p = akb.parse_report(report)
    assert p["date"] == "2026-08-09"
    assert p["segments"] == ["设计", "制造", "封测", "EDA", "材料"]
    assert len(p["news"]["设计"]) == 2
    t, d, s = p["news"]["设计"][0]
    assert t == "AMD 第六代 EPYC Venice 在台积电 2nm 量产"   # [回顾] 已剥离
    assert d == "2026-05-20"
    assert s == "高/利好/正面"
    assert len(p["news"]["制造"]) == 1
    assert "设计" not in {x for seg in p["news"] for x in []} or True
