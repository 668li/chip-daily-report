#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.collector — 模块2：多源数据采集适配器。

设计原则（适配器模式，可扩展）：
  - BaseCollector 定义统一采集接口：collect(scope) -> list[RawItem]
  - 每个数据源一个适配器子类，互不耦合
  - 运行模式：
      * online  真实抓取（SEC EDGAR 无需 key，可直连；其余源留接口）
      * offline 离线示例（内置从现有日报构造的多源样例，保证沙箱可跑通全流程）
  - 输出统一到 RawItem 结构，交给 cleaner.normalize() 清洗标准化

RawItem 字段（采集原始态）：
  source_id / source_name / tier / type / segment(guess) / title /
  url / published / body / raw_payload
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from email.utils import parsedate_to_datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

UA = "chip-daily-report collector contact@example.com"


@dataclass
class RawItem:
    source_id: str
    source_name: str
    tier: int
    type: str
    segment: str
    title: str
    url: str
    published: str            # YYYY-MM-DD
    body: str = ""
    raw_payload: dict = field(default_factory=dict)


# ============================================================
# 采集适配器基类
# ============================================================
class BaseCollector:
    source_id = "base"

    def collect(self, scope: dict) -> list[RawItem]:
        raise NotImplementedError


# ============================================================
# SEC EDGAR 真实采集器（公开 API，无需 key）
#   https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=8-K&dateb=&owner=include&count=40
#   生产建议：走 EDGAR full-text search API，本实现为 JSON API 演示（需联网）。
# ============================================================
class SECEdgarCollector(BaseCollector):
    source_id = "sec_edgar"
    BASE = "https://www.sec.gov/cgi-bin/browse-edgar"

    def collect(self, scope: dict) -> list[RawItem]:
        cik = scope.get("cik", "0001045810")  # NVIDIA
        url = (f"{self.BASE}?action=getcompany&CIK={cik}"
               f"&type=8-K&dateb=&owner=include&count=10&output=atom")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "chip-daily-report research demo contact@example.com"})
            with urllib.request.urlopen(req, timeout=10) as r:
                xml = r.read().decode("utf-8", "ignore")
        except Exception as e:  # 网络不可用 → 离线降级
            print(f"[collector:{self.source_id}] 网络不可用，降级离线模式：{e}")
            return []
        items = []
        for m in re.finditer(r"<title>(8-K[^<]*)</title>", xml[:20000]):
            items.append(RawItem(
                source_id=self.source_id, source_name="SEC EDGAR", tier=2,
                type="filing", segment="设计",
                title=m.group(1).strip(), url=url,
                published="", body="SEC 8-K filing 条目（完整抓取见生产实现）",
            ))
        return items


# ============================================================
# AIHOT 聚合 API 采集器（迭代2 正式源，Tier-4 线索，B 级，免 key）
#   端点契约：GET /api/v1/items?mode=all&window=7d&q=<kw>&limit=N
#   纪律（2026-08-09 实战验证）：
#     * 中文关键词必须 URL 编码
#     * 精选池（mode=top）空集时回退 mode=all
#     * 命中后用 links.original 追溯第三方原文（日报引用不直接挂 aihot）
# ============================================================
class AIHOTCollector(BaseCollector):
    source_id = "aihot"
    source_name = "AIHOT 聚合 API"
    BASE = "https://aihot.virxact.com/api/v1/items"

    def collect(self, scope: dict) -> list[RawItem]:
        queries = scope.get("aihot_queries") or ["半导体", "芯片", "存储", "半导体设备", "光刻"]
        window = scope.get("aihot_window", "7d")
        limit = int(scope.get("aihot_limit", 8))
        items, seen = [], set()
        for q in queries:
            url = f"{self.BASE}?mode=all&window={window}&q={urllib.parse.quote(q)}&limit={limit}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    payload = json.loads(r.read().decode("utf-8", "ignore"))
            except Exception as e:
                print(f"[collector:{self.source_id}] 请求失败（降级跳过 {q}）：{e}")
                continue
            rows = payload.get("items") or payload.get("data") or payload.get("results") or []
            for row in rows:
                title = (row.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                links = row.get("links") or {}
                orig = links.get("original") or row.get("url") or url
                items.append(RawItem(
                    source_id=self.source_id, source_name=self.source_name, tier=4,
                    type="news", segment="综合",
                    title=title, url=orig,
                    published=row.get("publishedAt") or row.get("published") or row.get("date") or "",
                    body=row.get("summary") or row.get("content") or "",
                ))
        return items


# ============================================================
# RSS 通用采集器（迭代2 新增，免 key，标准 RSS 2.0 feed）
#   子类只需覆盖 source_id / source_name / tier / feed_url。
#   标题关键词猜测环节（猜不到 → "综合"，cleaner 容错为"未知"）。
# ============================================================
_SEG_KW = [
    ("制造", ["hbm", "dram", "nand", "晶圆", "fab", "foundry", "制程", "产能", "存储",
              "2nm", "3nm", "tsmc", "sk hynix", "samsung", "micron", "代工"]),
    ("设计", ["soc", "cpu", "gpu", "处理器", "架构", "设计", "chip", "nvidia", "amd",
              "intel", "accelerator", "asic"]),
    ("封测", ["封装", "osat", "cowos", "chiplet", "packaging", "测试", "assembly"]),
    ("EDA", ["eda", "synopsys", "cadence", "verification", " ip", "ip核"]),
    ("材料", ["材料", "光刻胶", "硅片", "wafer", "substrate", "气体", "靶材", "设备",
              "asml", "equipment", "lithography"]),
]


def _guess_segment(title: str) -> str:
    t = (title or "").lower()
    for seg, kws in _SEG_KW:
        if any(k in t for k in kws):
            return seg
    return "综合"


def _rfc822_to_date(pub: str) -> str:
    """RSS pubDate（RFC822，如 'Fri, 08 Aug 2026 07:00:00 +0000'）→ YYYY-MM-DD。"""
    if not pub:
        return ""
    try:
        return parsedate_to_datetime(pub).strftime("%Y-%m-%d")
    except Exception:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", pub)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _strip_html(s: str) -> str:
    s = _html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class RSSCollector(BaseCollector):
    source_id = "rss_base"
    source_name = "RSS"
    tier = 1
    feed_url = ""

    def collect(self, scope: dict) -> list[RawItem]:
        if not self.feed_url:
            return []
        try:
            req = urllib.request.Request(self.feed_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                xml_text = r.read().decode("utf-8", "ignore")
        except Exception as e:
            print(f"[collector:{self.source_id}] 抓取失败（降级离线）：{e}")
            return []
        return self._parse(xml_text)

    def _parse(self, xml_text: str) -> list[RawItem]:
        try:
            root = ET.fromstring(xml_text)
        except Exception as e:
            print(f"[collector:{self.source_id}] XML 解析失败：{e}")
            return []
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = (item.findtext("link") or "").strip()
            items.append(RawItem(
                source_id=self.source_id, source_name=self.source_name, tier=self.tier,
                type="news", segment=_guess_segment(title),
                title=title, url=link,
                published=_rfc822_to_date(item.findtext("pubDate") or ""),
                body=_strip_html(item.findtext("description") or ""),
            ))
        return items


class SemiEngineeringCollector(RSSCollector):
    source_id = "semiengineering"
    source_name = "Semiconductor Engineering"
    tier = 1
    feed_url = "https://semiengineering.com/feed/"


class EETimesCollector(RSSCollector):
    source_id = "eetimes"
    source_name = "EE Times"
    tier = 1
    feed_url = "https://www.eetimes.com/feed/"


# ============================================================
# 离线示例数据（内置 5 环节 × 多源样例，模拟真实多源交叉）
#   同一事件刻意多源（含层级差异、价格数字差异、时间差异），
#   用于验证模块 3 的去重 / 交叉验证 / 置信度 与模块 4 的差异对比。
# ============================================================
OFFLINE_EVENTS = [
    # ---- E1: SK海力士 384 亿美元扩产（3 源，含一手 IR）----
    dict(source_id="skhynix_ir", source_name="SK hynix 新闻室", tier=0, type="ir",
         segment="制造", title="SK hynix 公布约 384 亿美元扩产计划 加码 HBM 与 DRAM",
         url="https://news.skhynix.com/hbm-capex-2026", published="2026-08-07",
         body="SK海力士公布约384亿美元扩产计划，重点投向龙仁Y2与清州M17晶圆厂，用于HBM、DRAM与NAND产能扩张。公司凭借HBM3E与HBM4先发优势深度绑定英伟达，2026年HBM出货份额有望维持全球领先。"),
    dict(source_id="cls", source_name="财联社", tier=3, type="news",
         segment="制造", title="SK海力士拟投384亿美元扩产 加码HBM与DRAM",
         url="https://www.cls.cn/detail/xk/2448352", published="2026-08-07",
         body="SK海力士公布约384亿美元扩产计划，重点投向龙仁Y2与清州M17等晶圆厂，用于HBM、DRAM与NAND产能扩张。"),
    dict(source_id="trendforce", source_name="TrendForce", tier=1, type="data",
         segment="制造", title="SK hynix Plans $38.4B Capex for HBM/DRAM Expansion",
         url="https://www.trendforce.com/news/skhynix-capex", published="2026-08-07",
         body="SK hynix announced approximately $38.4 billion capital expenditure for HBM, DRAM and NAND capacity expansion at Yongin Y2 and Cheongju M17 fabs."),
    # ---- E2: 寒武纪业绩扭亏（2 源：中文权威 + 交易所公告）----
    dict(source_id="cambricon_filing", source_name="寒武纪（交易所公告）", tier=0, type="filing",
         segment="设计", title="寒武纪 2026 年半年度报告：营收 59.96 亿元，净利润 23.11 亿元",
         url="http://www.sse.com.cn/assortment/stock/list/info/announcement", published="2026-08-07",
         body="寒武纪发布2026年半年度业绩，实现营业收入59.96亿元同比增长108.13%，归母净利润23.11亿元同比增122.61%，扭转连续亏损。"),
    dict(source_id="stcn", source_name="证券时报", tier=3, type="news",
         segment="设计", title="寒武纪上半年营收59.96亿元同比增108% 净利23.11亿元扭亏",
         url="https://www.stcn.com/article/detail/4064724.html", published="2026-08-07",
         body="寒武纪发布2026年半年度业绩，实现营业收入59.96亿元同比增长108.13%，归母净利润23.11亿元同比增122.61%，扭转连续亏损。思元系列AI训练芯片在国产大模型与智算中心批量落地。"),
    # ---- E3: 台积电 N2 放量（3 源：英文媒体 + 韩媒 + 数据源，含数字差异）----
    dict(source_id="digitimes_tw", source_name="电子时报 DigiTimes", tier=1, type="news",
         segment="制造", title="台积电N2 2nm五厂放量 月产能冲击12万片",
         url="https://www.digitimes.com.tw/n2-2nm-ramp", published="2026-08-06",
         body="台积电N2制程在竹科Fab 20与高雄Fab 22等五座晶圆厂同步进入量产爬坡，单厂月产能已达2万片水平。N2采用GAA纳米片晶体管，较3nm同功耗性能提升10%至15%。"),
    dict(source_id="chosun", source_name="Chosun Ilbo", tier=3, type="news",
         segment="制造", title="TSMC 2nm ramp-up accelerates at five fabs",
         url="https://www.chosun.com/english/industry-en/tsmc-n2", published="2026-08-06",
         body="TSMC's N2 process is ramping at five fabs including Fab 20 and Fab 22, targeting 120,000 wafers per month."),
    dict(source_id="trendforce", source_name="TrendForce", tier=1, type="data",
         segment="制造", title="TSMC N2 Monthly Capacity to Reach 120K Wafers",
         url="https://www.trendforce.com/news/tsmc-n2-capacity", published="2026-08-06",
         body="TrendForce estimates TSMC N2 monthly capacity will reach 120,000 wafers across five fabs in 2026, with unit fab capacity at ~20,000 wafers per month."),
    # ---- E4: AMD MI400（2 源：英文媒体 + 聚合，含分歧：HBM4 容量说法）----
    dict(source_id="eetimes", source_name="EE Times", tier=1, type="news",
         segment="设计", title="AMD Unveils Instinct MI400 Series with CDNA 5",
         url="https://www.eetimes.com/amd-instinct-mi400", published="2026-08-07",
         body="AMD launched the Instinct MI455X accelerator with CDNA 5 architecture, 320 billion transistors and 432GB of HBM4 memory, built on TSMC 2nm for compute dies."),
    dict(source_id="163_news", source_name="网易科技", tier=4, type="news",
         segment="设计", title="AMD发布Instinct MI400系列与Helios机架 正面挑战英伟达Rubin",
         url="https://dy.163.com/article/L3OARQVV0556OH4N.html", published="2026-08-07",
         body="AMD在Advancing AI 2026大会推出Instinct MI455X加速器，基于CDNA 5架构集成3200亿晶体管、搭载384GB HBM4显存。（原始：AMD Advancing AI 2026 发布会）"),
    # ---- E5: 长电临港基地（2 源：权威 + 聚合）----
    dict(source_id="stcn", source_name="证券时报", tier=3, type="news",
         segment="封测", title="长电科技78亿落子上海临港 建先进封装基地",
         url="https://stcn.com/article/detail/3978587.html", published="2026-08-06",
         body="长电科技宣布投资78亿元在上海临港建设先进封装基地，规划覆盖2.5D/3D、HBM3e、Chiplet与CPO光电共封装等产线。"),
    dict(source_id="qq_news", source_name="腾讯新闻", tier=4, type="news",
         segment="封测", title="长电科技78亿建临港先进封装基地 对标台积电CoWoS",
         url="https://new.qq.com/rain/a/20260806A06SBT00", published="2026-08-06",
         body="长电科技宣布投资78亿元在上海临港建设先进封装基地，XDFOI平台对标台积电CoWoS，8层HBM3E量产良率已达98.5%。"),
    # ---- E6: 概伦电子并购（单源：唯一来源，验证低置信度/一致性缺陷）----
    dict(source_id="eastmoney", source_name="东方财富网", tier=4, type="news",
         segment="EDA", title="概伦电子21.74亿并购落地 国产EDA迈向平台化",
         url="https://caifuhao.eastmoney.com/news/20260804", published="2026-08-04",
         body="概伦电子完成收购锐成芯微100%股权与纳能微45.64%股权，交易作价21.74亿元，正式补齐半导体IP短板。"),
    # ---- E7: 存储价格（2 数据源，数字差异：+53~58% vs +55%）----
    dict(source_id="trendforce", source_name="TrendForce", tier=1, type="data",
         segment="制造", title="DRAM Contract Prices Up 53-58% QoQ in 2Q26",
         url="https://www.trendforce.com/news/dram-price-2q26", published="2026-07-14",
         body="TrendForce: general DRAM contract prices rose 53-58% QoQ in Q2 2026, HBM included. HBM market to grow 58% to $54.6B in 2026."),
    dict(source_id="qq_news", source_name="腾讯新闻", tier=4, type="news",
         segment="制造", title="存储超级周期：Q2 DRAM合约价环比上涨55%",
         url="https://new.qq.com/rain/a/20260714A02J1V00", published="2026-07-14",
         body="据集邦咨询数据，2026年Q2一般型DRAM合约价环比上涨55%，NAND Flash上涨55%-60%，AI服务器消耗全球约53%的DRAM月产能。"),
    # ---- E8: 华大九天 3DIC（单源中文媒体）----
    dict(source_id="eetchina", source_name="EET-China", tier=3, type="news",
         segment="EDA", title="华大九天发布Argus 3DIC全流程EDA 对标国际大厂",
         url="https://www.eet-china.com/mp/a507778.html", published="2026-08-05",
         body="华大九天推出Argus 3DIC物理验证平台，全面支持2.5D/3D异构集成封装设计，实现从协同设计到封装的全链路物理验证。"),
    # ---- E9: 光刻胶（单源）----
    dict(source_id="21jingji", source_name="21世纪经济报道", tier=3, type="news",
         segment="材料", title="鼎龙股份光刻胶产能达330吨 潜江二期投产",
         url="https://m.21jingji.com/article/20260805", published="2026-08-05",
         body="鼎龙股份半导体光刻胶业务再扩容，潜江二期300吨产线投产叠加一期30吨产能，KrF与ArF光刻胶总产能达到330吨。"),
    # ---- E10: 出口管制 MATCH 法案（2 源：政府一手 + 中文权威）----
    dict(source_id="bis_rules", source_name="美国 BIS 出口管制规则", tier=2, type="filing",
         segment="制造", title="MATCH Act: House Foreign Affairs Committee Passes 36-8",
         url="https://www.bis.doc.gov/match-act", published="2026-04-22",
         body="US House Foreign Affairs Committee passed the MATCH Act 36-8, expanding semiconductor equipment export controls to multilateral alignment covering immersion DUV lithography."),
    dict(source_id="xinhuanet", source_name="新华网", tier=3, type="news",
         segment="制造", title="美众议院外交事务委员会36:8通过芯片设备多边管制法案",
         url="https://www.xinhuanet.com/finance/20260610", published="2026-06-10",
         body="美国众议院外交事务委员会以36:8通过《MATCH法案》，将半导体设备出口管制从单边点名升级为多边强制对齐，覆盖浸没式DUV光刻机。"),
]


def load_offline(scope: dict) -> list[RawItem]:
    """构造离线样例（含 3 个跨源冲突样例用于演示差异对比）。"""
    items = []
    for e in OFFLINE_EVENTS:
        items.append(RawItem(
            source_id=e["source_id"], source_name=e["source_name"],
            tier=e["tier"], type=e["type"], segment=e["segment"],
            title=e["title"], url=e["url"], published=e["published"],
            body=e["body"],
        ))
    return items


def collect(scope: dict | None = None, mode: str = "offline") -> list[RawItem]:
    """统一采集入口。

    mode:
      offline 内置多源样例（默认，保证可运行）
      online  真实抓取（迭代2：SEC EDGAR + AIHOT + SemiEngineering + EE Times
              共 4 个免 key 真实源；任一失败自动跳过不阻塞）
    """
    scope = scope or {}
    items: list[RawItem] = []
    if mode == "online":
        for cls in ONLINE_COLLECTORS:
            try:
                items.extend(cls().collect(scope))
            except Exception as e:
                print(f"[collector:{cls.source_id}] 采集失败：{e}")
        if not items:
            print("[collector] 在线采集为空，自动回退离线样例")
            items = load_offline(scope)
    else:
        items = load_offline(scope)
    return items


# 在线采集器注册表（迭代2：4 个免 key 真实源）
ONLINE_COLLECTORS = (
    SECEdgarCollector,
    AIHOTCollector,
    SemiEngineeringCollector,
    EETimesCollector,
)


# ============================================================
# 连通性探针（v6.0，health_check 复用）
#   对每个在线数据源端点做一次真实请求，返回状态/时延/错误。
#   fail-soft：任何异常 → status=down，绝不抛出。
# ============================================================
PROBE_ENDPOINTS = [
    ("sec_edgar", "SEC EDGAR",
     "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001045810&type=8-K&count=1&output=atom"),
    ("aihot", "AIHOT 聚合 API",
     "https://aihot.virxact.com/api/v1/items?mode=all&window=24h&limit=1"),
    ("semiengineering", "Semiconductor Engineering",
     "https://semiengineering.com/feed/"),
    ("eetimes", "EE Times",
     "https://www.eetimes.com/feed/"),
]


def probe_online_sources(timeout: int = 8) -> list[dict]:
    """探针所有在线源端点（SEC EDGAR / AIHOT）。

    返回 [{source_id, source_name, status(ok|down), http_status, latency_ms, error}]。
    断网/超时/异常均不抛出，只标记 down。
    """
    results = []
    for sid, name, url in PROBE_ENDPOINTS:
        start = time.time()
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status_code = getattr(r, "status", 200)
                latency = int((time.time() - start) * 1000)
            results.append({
                "source_id": sid, "source_name": name, "status": "ok",
                "http_status": status_code, "latency_ms": latency, "error": None,
            })
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            results.append({
                "source_id": sid, "source_name": name, "status": "down",
                "http_status": None, "latency_ms": latency, "error": str(e)[:200],
            })
    return results


if __name__ == "__main__":
    items = collect(mode="offline")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "raw_events.json").write_text(
        json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print(f"[collector] 采集 {len(items)} 条原始事件")
    print("[collector] 按源层级:", dict(Counter(i.tier for i in items)))
    print("[collector] 按环节:", dict(Counter(i.segment for i in items)))
