#!/usr/bin/env python3
"""
test_x_decisions.py —— X1–X16 上游冲突裁决回归用例（F3 裁决固化）

目标：把 delivery/高层架构设计.md §3.4 的 16 组唯一裁决固化为可自动化验证的断言，
防止后续规则修改导致裁决漂移（特别是 X1/X7 域名分裂复发）。

运行：
  cd <skill根目录>
  python -m pytest tests/test_x_decisions.py -v
"""
import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "rules" / "rule_registry.yaml"
SCRIPT = ROOT / "scripts" / "validate_report.py"
SOURCES = ROOT / "references" / "sources.md"
CLASSIFICATION = ROOT / "references" / "classification.md"
SKILL = ROOT / "SKILL.md"
RUBRIC = ROOT / "references" / "rubric.md"
CLAUDE = ROOT / "CLAUDE.md"

SOURCES_START = "<!-- GEN:ALEVEL:START -->"
SOURCES_END = "<!-- GEN:ALEVEL:END -->"


def load_registry():
    with open(REGISTRY, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_report", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_text(p):
    return p.read_text(encoding="utf-8")


def parse_sources_alevel_domains(text):
    i = text.find(SOURCES_START)
    j = text.find(SOURCES_END)
    block = text[i:j]
    domains = set()
    from urllib.parse import urlparse
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip() != ""]
        if len(cells) < 3 or cells[0] == "来源":
            continue
        host = urlparse(cells[2]).netloc.lower().lstrip("www.")
        if host:
            domains.add(host)
    return domains


# =============================================================================
# X1 / X7：单一权威源 + 双向差集=0
# =============================================================================

def test_X1_registry_is_single_source_of_truth():
    reg = load_registry()
    a = reg["domains"]["a_level"]
    assert len(a) == 44, f"X1/X7: A 级域名应为 44 个，实际 {len(a)}"


def test_X7_bidirectional_diff_zero():
    """注册表 ↔ 脚本 ↔ sources.md 的 A 级域名集合必须完全一致。"""
    reg = load_registry()
    reg_a = {d["domain"].lower() for d in reg["domains"]["a_level"]}
    v = load_validator()
    script_a = {d.lower() for d in v.A_LEVEL_DOMAINS}
    sources_a = parse_sources_alevel_domains(read_text(SOURCES))

    assert reg_a == script_a, f"X7: 注册表与脚本 A 级域名不一致: {reg_a ^ script_a}"
    assert reg_a == sources_a, f"X7: 注册表与 sources.md A 级域名不一致: {reg_a ^ sources_a}"
    assert script_a == sources_a, f"X7: 脚本与 sources.md A 级域名不一致: {script_a ^ sources_a}"


def test_X7_c_level_matches():
    reg = load_registry()
    reg_c = {d["domain"].lower() for d in reg["domains"]["c_level"]}
    v = load_validator()
    assert reg_c == {d.lower() for d in v.C_LEVEL_DOMAINS}


def test_X7_segments_match():
    reg = load_registry()
    v = load_validator()
    assert list(reg["segments"]) == list(v.SEGMENTS)


# =============================================================================
# X3：摘要句数阈值 3-5 PASS / 6 WARN / ≥7 FAIL / 1-2 FAIL
# =============================================================================

def test_X3_sentence_thresholds():
    v = load_validator()
    assert v.count_sentences("一句。二句。三句。") == 3
    assert v.count_sentences("一。二。三。四。五。") == 5
    assert v.count_sentences("一。二。三。四。五。六。") == 6
    assert v.count_sentences("一。二。三。四。五。六。七。") == 7
    # 检查4 的 ok 判定：3-5 PASS
    item = {"title": "t", "summary": "一。二。三。四。五。", "source": "", "timestamp": ""}
    _, ok, n = v.check_summary_sentences([item])[0]
    assert ok and n == 5
    # 6 句：ok=False（WARN 由 main 判断 sent==6）
    item6 = {"title": "t", "summary": "一。二。三。四。五。六。", "source": "", "timestamp": ""}
    _, ok6, n6 = v.check_summary_sentences([item6])[0]
    assert not ok6 and n6 == 6


# =============================================================================
# X4：摘要过长回退目标为 Step 3（非 Step 5）
# =============================================================================

def test_X4_failure_table_back_to_step3():
    skill = read_text(SKILL)
    # 失败处理表中"摘要过长"行必须回退 Step 3
    row = re.search(r"摘要过长[^\n]*Step\s*(\d)", skill)
    assert row is not None, "X4: 未找到'摘要过长'失败处理行"
    assert row.group(1) == "3", f"X4: 摘要过长应回退 Step 3，实际 Step {row.group(1)}"
    # 确保没有"回到Step 5"的误写残留于摘要过长语境
    assert "回到Step 5" not in skill, "X4: SKILL.md 仍存在'回到Step 5'笔误"


# =============================================================================
# X5 / X6：Rubric 15 项口径 + 15 行自检表
# =============================================================================

def test_X5_rubric_has_15_items():
    rubric = read_text(RUBRIC)
    # rubric.md 以 "### N. 检查项名" 编号 15 项
    nums = set(int(m) for m in re.findall(r"^###\s+(\d+)\.", rubric, re.MULTILINE))
    assert len([n for n in nums if 1 <= n <= 15]) >= 15, \
        f"X5: rubric.md 应覆盖 15 项 Rubric，实际 {sorted(nums)}"


def test_X6_selfcheck_table_15_rows():
    skill = read_text(SKILL)
    # 输出格式中的自检表示例应包含 15 个编号行
    nums = set(int(m) for m in re.findall(r"^\|\s*(\d+)\s*\|", skill, re.MULTILINE))
    assert len([n for n in nums if 1 <= n <= 15]) >= 15, \
        f"X6: SKILL.md 自检表示例应含 15 行，实际 {sorted(nums)}"


# =============================================================================
# X8：Samsung 父域匹配
# =============================================================================

def test_X8_samsung_parent_domain():
    v = load_validator()
    assert v.domain_matches("news.samsung.com", "samsung.com") is True
    assert v.domain_matches("semiconductor.samsung.com", "samsung.com") is True
    assert v.domain_matches("samsung.com", "samsung.com") is True
    # 脚本常量确实登记 samsung.com 父域
    assert "samsung.com" in {d.lower() for d in v.A_LEVEL_DOMAINS}


# =============================================================================
# X9：HBM 归制造（封装工艺细节除外）
# =============================================================================

def test_X9_hbm_to_manufacturing():
    cls = read_text(CLASSIFICATION)
    assert "HBM" in cls and "制造" in cls
    # 存疑仲裁表应有 HBM 归制造的明确表述
    assert "HBM" in cls and ("归制造" in cls or "归 制造" in cls), \
        "X9: classification.md 应明确 HBM 相关新闻归制造"


# =============================================================================
# X10：产能实体 IPO 纳入 / 纯融资不纳入
# =============================================================================

def test_X10_ipo_binary_rule():
    cls = read_text(CLASSIFICATION)
    assert "产能实体" in cls and "纳入" in cls, "X10: 应写明产能实体 IPO 纳入"
    assert "纯融资" in cls and "不纳入" in cls, "X10: 应写明纯融资/IPO 不纳入"


# =============================================================================
# X11：股价可作一句佐证，不得作主体
# =============================================================================

def test_X11_stock_price_as_evidence_only():
    cls = read_text(CLASSIFICATION)
    assert "X11" in cls, "X11: classification.md 应含 X11 股价书写规范小节"
    assert "佐证" in cls, "X11: 应允许股价作为一句影响佐证"
    # 校验器仍应拦截含投资建议关键词的摘要
    v = load_validator()
    items = [{"title": "t", "summary": "某公司发布新技术，建议买入。", "source": "", "timestamp": ""}]
    viol = v.check_neutrality(items)
    assert len(viol) > 0, "X11: 含'建议买入'的摘要应被中立性检查拦截"


# =============================================================================
# X12：单期条数软指标
# =============================================================================

def test_X12_news_count_soft_indicator():
    v = load_validator()
    assert v.check_news_count(0) == ("PASS", v.check_news_count(0)[1])  # 节假日0条自动PASS
    assert v.check_news_count(17)[0] == "PASS"   # 落入 15-20
    assert v.check_news_count(22)[0] == "WARN"   # 21-25 WARN
    assert v.check_news_count(12)[0] == "WARN"   # 10-14 WARN
    assert v.check_news_count(8)[0] == "FAIL"    # <10 FAIL
    assert v.check_news_count(26)[0] == "FAIL"   # >25 FAIL


# =============================================================================
# X13 / X14：来源分级统计位于自检结果小节内
# =============================================================================

def test_X14_source_stats_inside_selfcheck():
    v = load_validator()
    # 独立一级章节 -> WARN
    bad = "# 芯片行业日报 — 2026-08-07\n\n## 来源分级统计\n\nA级：x.com=1条\n\n## 自检结果\n\n| # | 检查项 | 结果 |\n"
    assert v.check_source_stats_location(bad)[0] == "WARN"
    # 仅在自检结果内 -> PASS
    good = "## 自检结果\n\n来源分级统计：A级 x.com=1条\n"
    assert v.check_source_stats_location(good)[0] == "PASS"


# =============================================================================
# X15：环节章节全称
# =============================================================================

def test_X15_section_title_fullname():
    v = load_validator()
    bad = "## EDA\n\n## 材料\n"
    assert v.check_section_title_fullname(bad)[0] == "WARN"
    good = "## EDA / 工具\n\n## 材料 / 设备\n"
    assert v.check_section_title_fullname(good)[0] == "PASS"


# =============================================================================
# X16：标题附日期 + 元信息 blockquote 半角冒号
# =============================================================================

def test_X16_title_date_and_meta_format():
    v = load_validator()
    good = "# 芯片行业日报 — 2026年8月7日\n\n> 生成时间: 2026-08-07 13:00\n> 覆盖范围: 2026-08-07\n> 新闻总数: 18条\n"
    assert v.check_title_date(good)[0] == "PASS"
    # 缺日期 -> WARN
    no_date = "# 芯片行业日报\n\n> 生成时间: 2026-08-07 13:00\n"
    assert v.check_title_date(no_date)[0] == "WARN"
    # 元信息非 blockquote -> WARN
    no_block = "# 芯片行业日报 — 2026年8月7日\n\n生成时间：2026-08-07 13:00\n"
    assert v.check_title_date(no_block)[0] == "WARN"


# =============================================================================
# X2：镜像同步状态文案（CLAUDE.md 当前状态段）
# =============================================================================

def test_X2_mirror_sync_status_documented():
    claude = read_text(CLAUDE)
    # 当前状态段应说明镜像同步情况（X2 裁决：8 文件中 7 个已一致，仅域名常量曾待同步）
    assert "镜像" in claude, "X2: CLAUDE.md 应说明 .trae 镜像同步状态"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
