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
import ipaddress
import json
import re
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# XML 安全解析：defusedxml 禁 DTD/实体扩展，杜绝 billion-laughs 类资源耗尽。
import defusedxml.ElementTree as _safe_et


def _xml_fromstring(text: str):
    return _safe_et.fromstring(text, forbid_dtd=True, forbid_entities=True)

DATA_DIR = Path(__file__).resolve().parent / "data"

UA = "chip-daily-report collector contact@example.com"

# 安全抓取约束（v5.13 加固）：采集器只允许访问已注册数据源的 https 端点，
# 且域名解析结果不得指向私有/回环/链路本地地址，封死 SSRF 面。
_ALLOWED_HOSTS = {
    "sec.gov", "www.sec.gov",
    "aihot.virxact.com",
    "semiengineering.com", "www.semiengineering.com",
    "eetimes.com", "www.eetimes.com",
    "cnbc.com", "www.cnbc.com", "search.cnbc.com",
    "semianalysis.com", "www.semianalysis.com",
    # ---- v7 自主发现层配套内置源（2026-09-25 实测可活的官方 feed 域名）----
    "ieee.org", "spectrum.ieee.org",                          # IEEE Spectrum
    "tomshardware.com", "www.tomshardware.com",               # Tom's Hardware
    "asia.nikkei.com",                                        # Nikkei Asia（RDF）
    "koreaherald.com", "www.koreaherald.com",                 # Korea Herald
    "yna.co.kr", "en.yna.co.kr",                              # Yonhap EN
    "finance.yahoo.com", "feeds.finance.yahoo.com",           # Yahoo Finance 个股
    "cninfo.com.cn", "www.cninfo.com.cn", "static.cninfo.com.cn",  # 巨潮公告
    "newsnow.busiyi.world",                                   # newsnow 热榜
    "news.google.com",                                        # Google News RSS
}
_MAX_BODY_BYTES = 5 * 1024 * 1024

ROOT = Path(__file__).resolve().parent.parent.parent  # -> 项目根
# 自主发现层状态文件（discover.py 维护；本模块只读，fail-soft）
_DISCOVERED_STATE_PATH = ROOT / "state" / "discovered_sources.json"


def _dynamic_hosts(path=None) -> set:
    """v7 自主发现层：读 state/discovered_sources.json，返回
    state ∈ {trial, active} 的源域名及其 feed 域名（并入抓取白名单）。
    fail-soft：文件不存在 / 损坏 / 字段异常 → 空集（退回纯静态白名单）。"""
    hosts: set = set()
    try:
        data = json.loads(
            Path(path or _DISCOVERED_STATE_PATH).read_text(encoding="utf-8"))
        for s in data.get("sources", []) or []:
            if not isinstance(s, dict) or s.get("state") not in ("trial", "active"):
                continue
            d = str(s.get("domain") or "").lower().strip()
            fh = (urllib.parse.urlparse(str(s.get("feed_url") or "")).hostname or "").lower()
            for h in {d, fh}:
                if not h:
                    continue
                hosts.add(h)
                # www 变体互补（2026-09-26 回测发现）：state 存裸域
                # techpowerup.com 而 feed 实际在 www.techpowerup.com（或反之），
                # 只记域名本体会让动态源全部被白名单拒绝、采集静默缺失。
                # 同一注册域的 www 前后缀仍受 https + 解析 IP 拒私网约束。
                if h.startswith("www."):
                    hosts.add(h[4:])
                else:
                    hosts.add("www." + h)
    except Exception:
        return set()
    return hosts


def _assert_safe_url(url: str) -> None:
    """词法校验（https + 域名白名单）+ 尽力 IP 校验（DNS 可达时）。

    DNS 不可达时不在此处阻塞——后续 urlopen 会自然失败并走离线降级，
    保证 offline 模式与零网络测试环境可用。
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"仅允许 https 抓取：{url}")
    host = (parsed.hostname or "").lower()
    # v7：静态白名单 ∪ 发现层动态白名单（state trial/active 源，fail-soft 空集）
    if host not in (_ALLOWED_HOSTS | _dynamic_hosts()):
        raise ValueError(f"域名不在白名单：{host}")
    try:
        infos = socket.getaddrinfo(host, 443)
    except OSError:
        return  # 离线环境：交给 urlopen 报错
    for info in infos:
        addr = str(info[4][0]).split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"域名解析到受限地址：{host} -> {addr}")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向逐跳安全校验（对抗审查 #4）：301/302/307 的落点必须重新通过
    _assert_safe_url（https + 白名单∪动态白名单 + 解析 IP 拒私网/回环），
    否则阻断——首跳校验不覆盖重定向落点 = 攻击者可 302 把请求带去内网
    或任意地址（本地 PoC 已复现：/feed 302 → 他域 /secret 被自动跟随）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_safe_url(str(newurl))  # 不通过则抛异常，请求按失败降级
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# 安装进程级安全 opener：让所有经由 urllib.request.urlopen 的请求
# （collector 四条抓取路径 / health_check 探针）都带上重定向逐跳校验。
# 测试桩 monkeypatch 的是 urlopen 函数本身，不受全局 opener 影响。
urllib.request.install_opener(
    urllib.request.build_opener(_SafeRedirectHandler()))


def _safe_fetch(url: str, timeout: int = 10) -> bytes:
    """白名单 + 私网拦截 + 大小上限的安全抓取；失败抛异常由调用方降级。"""
    _assert_safe_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(_MAX_BODY_BYTES)


def _safe_fetch_ex(url: str, timeout: int = 10, no_proxy: bool = False) -> bytes:
    """v7 扩展抓取：no_proxy=True 时用 ProxyHandler({}) 绕过系统代理直连
    （巨潮 / newsnow 等国内站实测必须，走系统代理会被拦）。

    安全校验按 _assert_safe_url 的同一防线显式内联展开（https-only + 白名单
    ∪ 动态白名单 + 解析 IP 拒私网/回环/链路本地/保留/多播），满足静态审计
    对「发请求前校验」的同函数可见性要求；末尾仍调用 _assert_safe_url 双保险。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"仅允许 https 抓取：{url}")
    host = (parsed.hostname or "").lower()
    if not host or host not in (_ALLOWED_HOSTS | _dynamic_hosts()):
        raise ValueError(f"域名不在白名单：{host}")
    try:
        infos = socket.getaddrinfo(host, 443)
    except OSError:
        infos = []  # 离线环境：DNS 不可达不在此阻塞，交给 urlopen 自然失败
    for info in infos:
        addr = str(info[4][0]).split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"域名解析到受限地址：{host} -> {addr}")
    _assert_safe_url(url)  # 集中式校验双保险
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if no_proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            return r.read(_MAX_BODY_BYTES)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(_MAX_BODY_BYTES)


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
        cik = str(scope.get("cik", "0001045810"))  # NVIDIA
        if not re.fullmatch(r"\d{10}", cik):  # CIK 必须是 10 位数字，防 URL 注入
            print(f"[collector:{self.source_id}] 非法 CIK，忽略：{cik!r}")
            return []
        url = (f"{self.BASE}?action=getcompany&CIK={cik}"
               f"&type=8-K&dateb=&owner=include&count=10&output=atom")
        try:
            xml = _safe_fetch(url).decode("utf-8", "ignore")
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
        window = str(scope.get("aihot_window", "7d"))
        limit = int(scope.get("aihot_limit", 8))
        if not re.fullmatch(r"\d{1,3}[hd]", window) or not 1 <= limit <= 50:
            print(f"[collector:{self.source_id}] 非法 window/limit 参数，忽略本批")
            return []
        queries = [str(q).strip()[:40] for q in queries if str(q).strip()][:10]
        items, seen = [], set()
        for q in queries:
            url = f"{self.BASE}?mode=all&window={window}&q={urllib.parse.quote(q)}&limit={limit}"
            try:
                payload = json.loads(_safe_fetch(url).decode("utf-8", "ignore"))
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


def _decode_tolerant(body: bytes) -> str:
    """容错解码：先 UTF-8，失败回退 GBK（巨潮实测 GBK 编码），再不行 ignore。"""
    for enc in ("utf-8", "gbk"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", "ignore")


def _ms_ts_to_date(v) -> str:
    """毫秒时间戳 → YYYY-MM-DD（北京时间，巨潮 announcementTime 契约）。
    非法输入返回空串。"""
    try:
        ms = int(str(v).strip())
    except (TypeError, ValueError):
        return ""
    if ms <= 0:
        return ""
    tz_cn = timezone(timedelta(hours=8))
    return datetime.fromtimestamp(ms / 1000, tz=tz_cn).strftime("%Y-%m-%d")


def _find_child(el, name):
    """按本地名找 el 的直接子元素（兼容 RDF/Atom 命名空间，v7 Nikkei RDF 需要）。"""
    for child in el:
        if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == name:
            return child
    return None


def _child_text(el, name) -> str:
    child = _find_child(el, name)
    return (child.text or "") if child is not None else ""


class RSSCollector(BaseCollector):
    source_id = "rss_base"
    source_name = "RSS"
    tier = 1
    feed_url = ""

    def collect(self, scope: dict) -> list[RawItem]:
        if not self.feed_url:
            return []
        try:
            xml_text = _safe_fetch(self.feed_url).decode("utf-8", "ignore")
        except Exception as e:
            print(f"[collector:{self.source_id}] 抓取失败（降级离线）：{e}")
            return []
        return self._parse(xml_text)

    # RSS 常见 HTML 命名实体白名单：解析前直接替换为字面字符，
    # 避免 defusedxml 禁实体后 &nbsp; &rsquo; 等未定义实体导致解析失败。
    _SAFE_ENTITIES = {
        "nbsp": " ", "rsquo": "\u2019", "lsquo": "\u2018",
        "rdquo": "\u201d", "ldquo": "\u201c", "mdash": "\u2014", "ndash": "\u2013",
        "hellip": "\u2026", "copy": "\u00a9", "reg": "\u00ae", "trade": "\u2122",
        "deg": "\u00b0", "plusmn": "\u00b1", "times": "\u00d7", "middot": "\u00b7",
        "laquo": "\u00ab", "raquo": "\u00bb", "euro": "\u20ac", "pound": "\u00a3",
        "yen": "\u00a5", "cent": "\u00a2", "sect": "\u00a7", "para": "\u00b6",
        "bull": "\u2022", "dagger": "\u2020", "prime": "\u2032", "ensp": " ",
        "shy": "\u00ad",
    }

    def _parse(self, xml_text: str) -> list[RawItem]:
        # RSS feed 容错（2026-08-15 DigiTimes/SemiEngineering 实测暴露）：
        #   1) 超大报文 → 拒绝（正常 RSS 远小于此上限）
        #   2) 裸 &（非实体开头）→ 转义为 &amp;，避免 not well-formed
        #   3) 常见 HTML 命名实体 → 按白名单替换为字面字符（&amp; 等预定义实体不动）
        #   4) 解析一律走 _xml_fromstring（defusedxml，禁 DTD/实体扩展）
        if xml_text and len(xml_text) > _MAX_BODY_BYTES:
            print(f"[collector:{self.source_id}] XML 超过大小上限，拒绝解析")
            return []
        if xml_text:
            xml_text = re.sub(r"&(?![a-zA-Z#][a-zA-Z0-9#]*;)", "&amp;", xml_text)
            xml_text = re.sub(
                r"&([a-zA-Z][a-zA-Z0-9]*);",
                lambda m: self._SAFE_ENTITIES.get(m.group(1), m.group(0)),
                xml_text,
            )
        try:
            root = _xml_fromstring(xml_text)
        except Exception as e:
            print(f"[collector:{self.source_id}] XML 解析失败：{e}")
            return []
        items = []
        # v7 兼容 RDF/RSS1.0（Nikkei nar 实测）：条目可能带命名空间
        # （{http://purl.org/rss/1.0/}item），故按「本地名 == item」匹配。
        for item in root.iter():
            if not isinstance(item.tag, str) or item.tag.rsplit("}", 1)[-1] != "item":
                continue
            title = _child_text(item, "title").strip()
            if not title:
                continue
            link = _child_text(item, "link").strip()
            if not link:  # Atom 形态：链接在 href 属性
                lc = _find_child(item, "link")
                if lc is not None:
                    link = (lc.get("href") or "").strip()
            # v7 日期兜底扩 dc:date 命名空间（Nikkei RDF 用 dc:date）与 Atom
            pub = (_child_text(item, "pubDate") or _child_text(item, "date")
                   or _child_text(item, "published") or "")
            # v7 Google News 条目带 <source url="出版方域名">，原样存入
            # raw_payload.publisher_domain（随 data/raw_events.json 落盘）。
            # 如实说明（对抗审查 #8）：当前 cleaner/fusion/gate 管线暂无消费点，
            # 日报引用回溯属已知待接入项；发现层计频走 discover.parse_feed_entries
            # 独立提取，不经由本字段。条目 link 为 news.google.com 跳转链（可点击）。
            raw: dict = {}
            src = _find_child(item, "source")
            if src is not None:
                pdomain = (src.get("url") or "").strip()
                if pdomain:
                    raw["publisher_domain"] = pdomain
            items.append(RawItem(
                source_id=self.source_id, source_name=self.source_name, tier=self.tier,
                type="news", segment=_guess_segment(title),
                title=title, url=link,
                published=_rfc822_to_date(pub),
                body=_strip_html(_child_text(item, "description")),
                raw_payload=raw,
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


class CNBCCollector(RSSCollector):
    """CNBC Tech RSS（迭代3 新增 · 2026-08-15 实测 200）。
    英文权威财经，设计/综合环节。域名 cnbc.com 不在 A 级白名单 → 判 B 级，
    仅作交叉验证与线索（与 sources.md 判定规则一致）。"""
    source_id = "cnbc"
    source_name = "CNBC"
    tier = 1
    feed_url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001054"


# NOTE(2026-08-15 实测)：DigiTimes 未接入在线采集器 —— /rss/news.xml 返回
# 反爬 HTML 壳（HTTP 200 但内容是 <!DOCTYPE html>），/rss/ 403 Forbidden，
# 不适合免 key 自动化抓取。保留 sources.md 的 site:digitimes.com 搜索兜底
# （实战命中率高），白名单域名 digitimes.com 继续有效，不浪费 A 级名额。


class SemiAnalysisCollector(RSSCollector):
    """SemiAnalysis feed（迭代3 新增 · 2026-08-15 实测 200）。
    全球行业风向标深度分析，A 级白名单；付费墙文章仅标题/摘要可作线索，
    body 为空时 cleaner 自动容错（published/url 仍完整）。"""
    source_id = "semianalysis"
    source_name = "SemiAnalysis"
    tier = 1
    feed_url = "https://semianalysis.com/feed/"


# ============================================================
# v7 自主发现层配套内置源（2026-09-25 实测可活的官方 feed，免 key）
# 实测已死/不可用（勿接，省探测预算）：TrendForce RSS(404)、The Elec(403/502)、
# AnandTech(关站)、36kr /feed、虎嗅 /rss/0.xml、Bing News RSS(仅12条)。
# ============================================================
class IEEESpectrumCollector(RSSCollector):
    """IEEE Spectrum 半导体专题（实测 200）。Tier-1 英文权威。"""
    source_id = "ieee_spectrum"
    source_name = "IEEE Spectrum"
    tier = 1
    feed_url = "https://spectrum.ieee.org/feeds/topic/semiconductors.rss"


class TomshardwareCollector(RSSCollector):
    """Tom's Hardware 全站 feed（实测 200）。Tier-1，偏设计/消费硬件环节。
    注意（2026-09-26 回测发现）：/feeds/all 会 301 到 http:// 的 feeds.xml
    （站点方重定向配置问题，会被 https 门禁正确拦下导致零产出），
    故直接用 https 直出的 /feeds.xml。"""
    source_id = "tomshardware"
    source_name = "Tom's Hardware"
    tier = 1
    feed_url = "https://www.tomshardware.com/feeds.xml"


class NikkeiAsiaCollector(RSSCollector):
    """Nikkei Asia（实测 200）。RDF/RSS1.0 格式，日期在 dc:date 命名空间
    （_parse 已按本地名兼容）。补日韩产业视角。"""
    source_id = "nikkei_asia"
    source_name = "Nikkei Asia"
    tier = 1
    feed_url = "https://asia.nikkei.com/rss/feed/nar"


class KoreaHeraldCollector(RSSCollector):
    """The Korea Herald（实测 200）。韩媒英文源，补存储/韩厂视角。"""
    source_id = "korea_herald"
    source_name = "The Korea Herald"
    tier = 1
    feed_url = "https://www.koreaherald.com/rss/allCh.xml"


class YonhapCollector(RSSCollector):
    """韩联社英文（实测 200）。通讯社口径，补三星/海力士官方侧信息。"""
    source_id = "yonhap_en"
    source_name = "Yonhap News (EN)"
    tier = 1
    feed_url = "https://en.yna.co.kr/RSS/news.xml"


class YahooFinanceCollector(RSSCollector):
    """Yahoo Finance 个股新闻 feed（v7）。财经媒体、跨行业来源，仅当标的
    命中芯片关键词时才相关 → tier=3 线索级。s= 参数指定标的，
    NVDA / TSM 两个子类都采（覆盖 AI 算力与代工双主线）。"""
    source_id = "yahoo_nvda"
    source_name = "Yahoo Finance (NVDA)"
    tier = 3
    feed_url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US"


class YahooFinanceTSMCollector(YahooFinanceCollector):
    source_id = "yahoo_tsm"
    source_name = "Yahoo Finance (TSM)"
    feed_url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSM&region=US&lang=en-US"


# Google News RSS 的语言参数（ceid 决定中文/英文版面）
_GNEWS_LANG_PARAMS = {
    "zh-CN": {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
    "en-US": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
}


class GoogleNewsCollector(RSSCollector):
    """Google News RSS 线索源（v7 · tier=4 仅线索）。
    中英 2 组 when:1d query；条目 <source url="出版方域名"> 原样存入
    raw_payload.publisher_domain（随 raw_events.json 落盘，管线暂无消费点，
    日报引用回溯为已知待接入项）；条目 link 是 news.google.com 跳转链。
    出版方计频由 discover.parse_feed_entries 独立完成（不经由本字段）。"""
    source_id = "google_news"
    source_name = "Google News"
    tier = 4
    QUERY_INTERVAL = 2.0          # 相邻 query 礼貌间隔 ≥2s
    QUERIES = (
        ("zh-CN", "(半导体 OR 芯片 OR 晶圆厂) when:1d"),
        ("en-US", "(semiconductor OR chip OR wafer) when:1d"),
    )
    _LAST_QUERY_HIT = [0.0]       # 可变容器跨实例记录上次请求时刻

    def collect(self, scope: dict) -> list[RawItem]:
        items: list[RawItem] = []
        for i, (lang, q) in enumerate(self.QUERIES):
            if i:  # 相邻 query 间隔（测试可把 QUERY_INTERVAL 调 0）
                wait = self.QUERY_INTERVAL - (time.time() - self._LAST_QUERY_HIT[0])
                if wait > 0:
                    time.sleep(wait)
            self._LAST_QUERY_HIT[0] = time.time()
            p = _GNEWS_LANG_PARAMS[lang]
            url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}"
                   f"&hl={p['hl']}&gl={p['gl']}&ceid={p['ceid']}")
            try:
                xml_text = _safe_fetch(url).decode("utf-8", "ignore")
            except Exception as e:
                print(f"[collector:{self.source_id}] 查询失败跳过（{lang}）：{e}")
                continue
            items.extend(self._parse(xml_text))
        return items


class CninfoCollector(BaseCollector):
    """巨潮资讯公告检索（v7 · tier=3 type=filing，2026-09-25 实测契约）：
      GET /new/fulltextSearch/full?searchkey=芯片&pageNum=1
    实测纪律：
      * 响应 GBK 编码 → _decode_tolerant 容错解码
      * 国内站必须绕过系统代理：no_proxy 直连（_safe_fetch_ex）
      * announcements[].announcementTitle 含 <em> 高亮标签 → 清洗
      * adjunctUrl 拼 https://static.cninfo.com.cn/ 前缀得 PDF 链接
      * announcementTime 为毫秒时间戳
    """
    source_id = "cninfo"
    source_name = "巨潮资讯公告"
    tier = 3
    BASE = "https://www.cninfo.com.cn/new/fulltextSearch/full"
    PDF_PREFIX = "https://static.cninfo.com.cn/"

    def collect(self, scope: dict) -> list[RawItem]:
        key = str(scope.get("cninfo_searchkey", "芯片")).strip()[:40]
        url = f"{self.BASE}?searchkey={urllib.parse.quote(key)}&pageNum=1"
        try:
            body = _safe_fetch_ex(url, timeout=12, no_proxy=True)
        except Exception as e:
            print(f"[collector:{self.source_id}] 请求失败（跳过）：{e}")
            return []
        try:
            payload = json.loads(_decode_tolerant(body))
        except Exception as e:
            print(f"[collector:{self.source_id}] JSON 解析失败（跳过）：{e}")
            return []
        items = []
        for row in (payload.get("announcements") or [])[:15]:
            if not isinstance(row, dict):
                continue
            # <em> 高亮标签清洗 + HTML 剥离
            title = _strip_html(re.sub(r"</?em>", "",
                                       str(row.get("announcementTitle") or "")))
            if not title:
                continue
            adjunct = str(row.get("adjunctUrl") or "").strip()
            link = self.PDF_PREFIX + adjunct.lstrip("/") if adjunct else url
            items.append(RawItem(
                source_id=self.source_id, source_name=self.source_name, tier=self.tier,
                type="filing", segment=_guess_segment(title),
                title=title, url=link,
                published=_ms_ts_to_date(row.get("announcementTime")),
                body=str(row.get("secName") or "").strip(),
            ))
        return items


class NewsnowCollector(BaseCollector):
    """newsnow 热榜聚合（v7 · tier=4 线索，2026-09-25 实测契约）：
      GET https://newsnow.busiyi.world/api/s?id=<id>
      可用 id：cls-hot / wallstreetcn-hot / gelonghui
      返回 {"status":...,"items":[{"title","url"}]}
    纪律：no_proxy 直连失败 → 走系统代理重试一次 → 再失败跳过该榜。
    （RSSHub/DailyHotApi/60s API 公共实例实测被 Cloudflare 拦，勿换源）"""
    source_id = "newsnow"
    source_name = "Newsnow 热榜"
    tier = 4
    BASE = "https://newsnow.busiyi.world/api/s"
    IDS = ("cls-hot", "wallstreetcn-hot", "gelonghui")

    def collect(self, scope: dict) -> list[RawItem]:
        items: list[RawItem] = []
        seen = set()
        for nid in self.IDS:
            url = f"{self.BASE}?id={urllib.parse.quote(nid)}"
            payload = None
            last_err = ""
            for no_proxy in (True, False):  # 先绕代理直连，失败走系统代理重试一次
                try:
                    payload = json.loads(_decode_tolerant(
                        _safe_fetch_ex(url, timeout=12, no_proxy=no_proxy)))
                    break
                except Exception as e:
                    last_err = str(e)
                    payload = None
            if not isinstance(payload, dict):
                print(f"[collector:{self.source_id}] {nid} 拉取失败（跳过）：{last_err}")
                continue
            for row in (payload.get("items") or [])[:15]:
                title = str(row.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                items.append(RawItem(
                    source_id=self.source_id, source_name=self.source_name, tier=self.tier,
                    type="news", segment=_guess_segment(title),
                    title=title, url=str(row.get("url") or "").strip() or url,
                    published="", body=nid,
                ))
        return items


def dynamic_rss_collectors(path=None) -> list:
    """v7：把发现层已验证（state ∈ {trial, active}）且有 feed_url 的源
    实例化为 RSSCollector 子类，供 online 模式动态纳入采集。
    动态源 tier=4（线索级，对抗审查 #3）：零人工审核的自动发现源不得与
    registry 里 A 级中文权威（tier=3）同级——tier=4 才会被 gate G3 打
    single_low_tier 标记进日报候选降级线；人工定级后应录入 registry。
    fail-soft：状态文件缺失/损坏 → []。"""
    try:
        data = json.loads(
            Path(path or _DISCOVERED_STATE_PATH).read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for s in data.get("sources", []) or []:
        if not isinstance(s, dict) or s.get("state") not in ("trial", "active"):
            continue
        feed_url = str(s.get("feed_url") or "").strip()
        domain = str(s.get("domain") or "discovered").strip()
        if not feed_url:
            continue
        sid = f"dyn_{s.get('id') or domain}"
        out.append(type(sid, (RSSCollector,), dict(
            source_id=sid, source_name=domain, tier=4, feed_url=feed_url,
        )))
    return out


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
        # v7：发现层动态源（trial/active）并入在线采集（fail-soft，空集则无影响）
        try:
            dyn = tuple(dynamic_rss_collectors())
        except Exception as e:
            print(f"[collector] 动态源加载失败跳过：{e}")
            dyn = ()
        for cls in tuple(ONLINE_COLLECTORS) + dyn:
            try:
                items.extend(cls().collect(scope))
            except Exception as e:
                print(f"[collector:{getattr(cls, 'source_id', '?')}] 采集失败：{e}")
        if not items:
            print("[collector] 在线采集为空，自动回退离线样例")
            items = load_offline(scope)
    else:
        items = load_offline(scope)
    return items


# 在线采集器注册表（迭代2：4 个免 key 真实源；迭代3：+CNBC/SemiAnalysis；
# v7：+发现层配套内置源（2026-09-25 实测可活）+动态源见 collect()；
# DigiTimes 实测反爬未接入，见类定义注释）
ONLINE_COLLECTORS = (
    SECEdgarCollector,
    AIHOTCollector,
    SemiEngineeringCollector,
    EETimesCollector,
    CNBCCollector,
    SemiAnalysisCollector,
    # ---- v7 自主发现层配套内置源 ----
    IEEESpectrumCollector,
    TomshardwareCollector,
    NikkeiAsiaCollector,
    KoreaHeraldCollector,
    YonhapCollector,
    YahooFinanceCollector,
    YahooFinanceTSMCollector,
    GoogleNewsCollector,
    CninfoCollector,
    NewsnowCollector,
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
    ("cnbc", "CNBC Tech",
     "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001054"),
    ("semianalysis", "SemiAnalysis",
     "https://semianalysis.com/feed/"),
    # ---- v7 自主发现层配套内置源（2026-09-25 实测可活） ----
    ("ieee_spectrum", "IEEE Spectrum",
     "https://spectrum.ieee.org/feeds/topic/semiconductors.rss"),
    ("tomshardware", "Tom's Hardware",
     "https://www.tomshardware.com/feeds/all"),
    ("nikkei_asia", "Nikkei Asia",
     "https://asia.nikkei.com/rss/feed/nar"),
    ("korea_herald", "Korea Herald",
     "https://www.koreaherald.com/rss/allCh.xml"),
    ("yonhap_en", "Yonhap EN",
     "https://en.yna.co.kr/RSS/news.xml"),
    ("yahoo_nvda", "Yahoo Finance (NVDA)",
     "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US"),
    ("yahoo_tsm", "Yahoo Finance (TSM)",
     "https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSM&region=US&lang=en-US"),
    ("google_news", "Google News",
     "https://news.google.com/rss/search?q=%E5%8D%8A%E5%AF%BC%E4%BD%93+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("cninfo", "巨潮资讯公告",
     "https://www.cninfo.com.cn/new/fulltextSearch/full?searchkey=%E8%8A%AF%E7%89%87&pageNum=1"),
    ("newsnow", "Newsnow 热榜",
     "https://newsnow.busiyi.world/api/s?id=cls-hot"),
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
            _assert_safe_url(url)
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
