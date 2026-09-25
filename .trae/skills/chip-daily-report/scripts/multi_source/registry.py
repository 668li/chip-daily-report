#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.registry — 数据源注册表（模块1 · 盘点）。

把现有分散在 sources.md（A/B/C 白名单 + Tier-0~4 来源池）与
rule_registry.yaml 的数据源，固化为结构化的「环节 × 源类型」网格注册表，
输出 data/source_registry.json，供 gap_analyzer / collector / health 共用。

源类型（type）：
  ir        公司投资者关系 / 法说会 / 官方公告（一手）
  news      行业媒体（权威 / 聚合）
  analysis  深度分析 / 研究机构
  filing    监管 / 财报原始文件（SEC EDGAR / 交易所公告）
  data      价格 / 产能 / 市场数据（TrendForce / SIA / WSTS）
  academic  学术会议 / 论文

环节（segment）：设计 / 制造 / 封测 / EDA / 材料（与 rule_registry 一致）
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # -> project root
DATA_DIR = Path(__file__).resolve().parent / "data"

SEGMENTS = ["设计", "制造", "封测", "EDA", "材料"]
TYPES = ["ir", "news", "analysis", "filing", "data", "academic"]
TYPE_LABEL = {
    "ir": "公司一手(IR/法说会)",
    "news": "行业媒体",
    "analysis": "深度分析",
    "filing": "监管/财报文件",
    "data": "价格/产能数据",
    "academic": "学术会议/论文",
}

# ============================================================
# 现有数据源盘点（来源：references/sources.md + rule_registry.yaml，2026-08-09）
# 每个源：id / name / tier / type / segments(覆盖环节) / url / status(active|stale|down)
# ============================================================
SOURCES = [
    # ---------- Tier-0 公司一手（IR / 法说会 / 官方公告） ----------
    dict(id="tsmc_ir", name="TSMC 台积电 IR", tier=0, type="ir", segments=["制造"],
         url="https://ir.tsmc.com", status="active"),
    dict(id="samsung_ir", name="Samsung Semiconductor", tier=0, type="ir",
         segments=["设计", "制造", "封测"], url="https://www.samsung.com/semiconductor", status="active"),
    dict(id="skhynix_ir", name="SK hynix 新闻室", tier=0, type="ir",
         segments=["制造", "封测"], url="https://news.skhynix.com", status="active"),
    dict(id="intel_ir", name="Intel Newsroom", tier=0, type="ir",
         segments=["设计", "制造"], url="https://www.intel.com/newsroom", status="active"),
    dict(id="nvidia_ir", name="NVIDIA Newsroom", tier=0, type="ir",
         segments=["设计"], url="https://nvidianews.nvidia.com", status="active"),
    dict(id="amd_ir", name="AMD IR", tier=0, type="ir", segments=["设计"],
         url="https://ir.amd.com", status="active"),
    dict(id="micron_ir", name="Micron 美光 IR", tier=0, type="ir",
         segments=["制造", "封测"], url="https://investors.micron.com", status="active"),
    dict(id="asml_ir", name="ASML IR", tier=0, type="ir", segments=["材料"],
         url="https://www.asml.com", status="active"),
    dict(id="amat_ir", name="Applied Materials IR", tier=0, type="ir",
         segments=["材料"], url="https://www.appliedmaterials.com", status="active"),
    dict(id="lam_ir", name="Lam Research IR", tier=0, type="ir", segments=["材料"],
         url="https://www.lamresearch.com", status="active"),
    dict(id="kla_ir", name="KLA IR", tier=0, type="ir", segments=["材料"],
         url="https://www.kla.com", status="active"),
    dict(id="broadcom_ir", name="Broadcom IR", tier=0, type="ir", segments=["设计"],
         url="https://www.broadcom.com", status="active"),
    dict(id="smic_ir", name="中芯国际 SMIC IR", tier=0, type="ir", segments=["制造"],
         url="https://www.smci.com", status="active"),
    dict(id="huahong_ir", name="华虹半导体 IR", tier=0, type="ir", segments=["制造"],
         url="https://www.huahong.com", status="active"),
    dict(id="naura_ir", name="北方华创 IR", tier=0, type="ir", segments=["材料"],
         url="https://www.naura.com", status="active"),
    dict(id="amec_ir", name="中微公司 AMEC IR", tier=0, type="ir", segments=["材料"],
         url="https://www.amec-inc.com", status="active"),
    dict(id="jcet_filing", name="长电科技（交易所公告）", tier=0, type="filing",
         segments=["封测"], url="http://www.sse.com.cn", status="active"),
    dict(id="cambricon_filing", name="寒武纪（交易所公告）", tier=0, type="filing",
         segments=["设计"], url="http://www.sse.com.cn", status="active"),
    # ---------- Tier-1 英文权威行业媒体 / 深度分析 ----------
    dict(id="semianalysis", name="SemiAnalysis", tier=1, type="analysis",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="https://www.semianalysis.com", status="active"),
    dict(id="digitimes_en", name="DigiTimes(EN)", tier=1, type="news",
         segments=["制造", "封测"], url="https://www.digitimes.com", status="active"),
    dict(id="digitimes_tw", name="电子时报 DigiTimes(TW)", tier=1, type="news",
         segments=["制造", "封测"], url="https://www.digitimes.com.tw", status="active"),
    dict(id="semiengineering", name="Semiconductor Engineering", tier=1, type="news",
         segments=["EDA", "材料", "设计"], url="https://semiengineering.com", status="active"),
    dict(id="eetimes", name="EE Times", tier=1, type="news",
         segments=["设计", "EDA"], url="https://www.eetimes.com", status="active"),
    dict(id="techinsights", name="TechInsights", tier=1, type="analysis",
         segments=["设计", "制造", "封测"], url="https://www.techinsights.com", status="active"),
    dict(id="trendforce", name="TrendForce(EN)", tier=1, type="data",
         segments=["制造", "封测", "材料"], url="https://www.trendforce.com", status="active"),
    dict(id="thelec", name="The Elec", tier=1, type="news",
         segments=["制造", "封测"], url="https://www.thelec.net", status="active"),
    dict(id="tomshardware", name="Tom's Hardware", tier=1, type="news",
         segments=["设计"], url="https://www.tomshardware.com", status="active"),
    # ---------- Tier-2 监管 / 财报原始文件 ----------
    dict(id="sec_edgar", name="SEC EDGAR", tier=2, type="filing",
         segments=["设计", "制造", "封测"], url="https://www.sec.gov/cgi-bin/browse-edgar", status="active"),
    dict(id="sse_szse", name="上交所 / 深交所公告", tier=2, type="filing",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="http://www.cninfo.com.cn", status="active"),
    dict(id="mops", name="台湾 MOPS 公开资讯观测站", tier=2, type="filing",
         segments=["制造", "封测"], url="https://mops.twse.com.tw", status="active"),
    dict(id="dart", name="韩国 DART", tier=2, type="filing",
         segments=["制造", "封测"], url="https://dart.fss.or.kr", status="active"),
    # ---------- Tier-3 中文权威媒体（A 级白名单节选） ----------
    dict(id="cls", name="财联社", tier=3, type="news", segments=["制造", "封测", "设计"],
         url="https://www.cls.cn", status="active"),
    dict(id="stcn", name="证券时报", tier=3, type="news", segments=["设计", "制造", "封测", "EDA", "材料"],
         url="https://www.stcn.com", status="active"),
    dict(id="xinhuanet", name="新华网", tier=3, type="news", segments=["制造", "材料"],
         url="https://www.xinhuanet.com", status="active"),
    dict(id="21jingji", name="21世纪经济报道", tier=3, type="news",
         segments=["材料", "制造"], url="https://www.21jingji.com", status="active"),
    dict(id="eetchina", name="EET-China", tier=3, type="news",
         segments=["设计", "EDA", "材料"], url="https://www.eet-china.com", status="active"),
    dict(id="cninfo", name="巨潮资讯", tier=3, type="filing",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="https://www.cninfo.com.cn", status="active"),
    # ---------- Tier-4 聚合（B 级，仅线索） ----------
    dict(id="aihot", name="AIHOT 聚合 API", tier=4, type="news",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="https://aihot.virxact.com",
         status="active", note="迭代2 正式源：collector 适配器已接入，links.original 追溯原文"),
    dict(id="qq_news", name="腾讯新闻", tier=4, type="news",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="https://news.qq.com", status="active"),
    dict(id="toutiao", name="今日头条", tier=4, type="news",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="https://www.toutiao.com", status="active"),
    dict(id="163_news", name="网易科技", tier=4, type="news",
         segments=["设计", "制造", "封测"], url="https://tech.163.com", status="active"),
    # ---------- 建议新增（缺口候选，status=planned） ----------
    dict(id="sia_wsts", name="SIA / WSTS 市场数据", tier=1, type="data",
         segments=["设计", "制造", "封测", "EDA", "材料"], url="https://www.semiconductors.org", status="planned"),
    dict(id="dramexchange", name="TrendForce DRAMeXchange 价格", tier=1, type="data",
         segments=["制造"], url="https://www.trendforce.com", status="planned"),
    dict(id="google_patents", name="Google Patents 专利情报", tier=2, type="filing",
         segments=["设计", "EDA", "材料"], url="https://patents.google.com", status="planned"),
    dict(id="bis_rules", name="美国 BIS 出口管制规则", tier=2, type="filing",
         segments=["制造", "材料", "封测"], url="https://www.bis.doc.gov", status="planned"),
    dict(id="eu_chips", name="欧盟芯片法案官方", tier=2, type="filing",
         segments=["制造", "材料"], url="https://digital-strategy.ec.europa.eu", status="planned"),
    dict(id="yole", name="Yole Group 封装/材料分析", tier=1, type="analysis",
         segments=["封测", "材料"], url="https://www.yolegroup.com", status="planned"),
    dict(id="semi_api", name="SEMI 行业数据 API", tier=1, type="data",
         segments=["材料"], url="https://www.semi.org", status="planned"),
    dict(id="cnipa", name="国家知识产权局专利检索", tier=2, type="filing",
         segments=["设计", "EDA", "材料"], url="https://pss-system.cponline.cnipa.gov.cn", status="planned"),
]

# 目标覆盖网格：每环节 × 每源类型 应至少有多少个独立源（最小目标）
TARGET_GRID = {seg: {t: 1 for t in TYPES} for seg in SEGMENTS}
# 关键网格提额（data / filing / analysis 是缩小信息差的关键，目标 2）
for seg in SEGMENTS:
    TARGET_GRID[seg]["data"] = 2
    TARGET_GRID[seg]["filing"] = 2
    TARGET_GRID[seg]["analysis"] = 2


def build_registry() -> dict:
    """生成结构化注册表 dict。"""
    grid = {seg: {t: [] for t in TYPES} for seg in SEGMENTS}
    for s in SOURCES:
        for seg in s["segments"]:
            grid[seg][s["type"]].append(s["id"])
    return {
        "meta": {
            "version": "1.0",
            "generated": "2026-08-09",
            "source": "references/sources.md + rules/rule_registry.yaml（盘点产物）",
            "segment_count": len(SEGMENTS),
            "type_count": len(TYPES),
        },
        "segments": SEGMENTS,
        "types": TYPES,
        "type_labels": TYPE_LABEL,
        "target_grid": TARGET_GRID,
        "sources": SOURCES,
        "grid": grid,
        "source_count": {
            "total": len(SOURCES),
            "active": sum(1 for s in SOURCES if s["status"] == "active"),
            "planned": sum(1 for s in SOURCES if s["status"] == "planned"),
        },
    }


def write_registry(path=None):
    path = path or (DATA_DIR / "source_registry.json")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reg = build_registry()
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[registry] 已写入 {path}（{len(reg['sources'])} 源 / {reg['source_count']['active']} 活跃 / {reg['source_count']['planned']} 计划新增）")
    return reg


if __name__ == "__main__":
    write_registry()
