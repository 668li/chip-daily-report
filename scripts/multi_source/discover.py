#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.discover — 自主源发现层 v1（打破「人工供源」信息茧房）。

定位：collector 只吃静态白名单（_ALLOWED_HOSTS + registry.SOURCES），本质是
「人工供源」。本模块让系统自己 发现 → 验证 → 纳入 新数据源：

  引擎1 gnews_domains    Google News RSS 是万能发现源：条目 <source url=...>
                         直接给出出版方域名，无需解重定向链
  引擎2 opml_candidates  公开 OPML 订阅清单采样候选 feed（允许失败跳过）
  引擎3 newsnow_domains  newsnow 热榜条目 URL 提取域名

候选域名经 known 过滤（registry.SOURCES ∪ collector._ALLOWED_HOSTS ∪ state
已有 domain）得到 net-new 增量，再逐域探测：
  feed 自动发现：首页 <link rel="alternate" type="application/rss+xml|atom+xml">
                的 href → 失败再试常见路径清单
                /feed/ /feed /rss /rss.xml /atom.xml /feed.xml /index.xml /feeds/all
  feed 合法性：响应体含 "<html" 是反爬壳（AnandTech 已死站就是 200+HTML 陷阱）
              必须拒绝；须含 <rss / <feed / <rdf:RDF 且解析出 ≥1 条目
  新鲜度：最新条目 90 天内；完全无日期按 unknown 标记仍算过
  相关性：CHIP_KW 词典（中英），不同关键词命中 ≥3 且有命中的条目数 ≥2 才过

生命周期状态机（抄 Miniflux 设计，状态文件 state/discovered_sources.json）：
  candidate --探测通过--> trial --连续 2 次通过--> active
  确定性失败（html_shell/not_a_feed/no_entries/low_relevance/stale_feed）
  error_count+1 且 next_check_at = now + min(30min*2^error_count, 7天)；
  连续 3 次 → frozen（冻结池保留，不删除，每周随到期重探，通过即翻案 trial）。
  瞬时失败（fetch_failed/probe_error：断网/超时/WAF 抖动）单独计数、
  退避上限 24h，不冻结、不改变 state——断网一个下午不冻死全池。
每次运行原子写回（先写 .tmp 再 os.replace）。

安全形态（与 collector.py 同源，防线不同）：
  发现层要探测未知域名，不能有静态白名单，防线 =
    https-only + _assert_safe_url 解析 IP 拒私网/回环/链路本地/保留/多播
    + 响应体大小上限 + 每域礼貌间隔 ≥0.8s + Google News 相邻 query ≥2s
  XML 一律 defusedxml（forbid_dtd + forbid_entities），实体白名单预处理同 collector。

实测黑名单（2026-09-25 调研，不要接，省探测预算）：
  TrendForce RSS(404) / The Elec(403,502) / AnandTech(关站, 200+HTML 陷阱) /
  36kr /feed / 虎嗅 /rss/0.xml / Bing News RSS(仅 12 条) /
  RSSHub / DailyHotApi / 60s API 公共实例（均被 Cloudflare 拦截）。

CLI：python scripts/multi_source/discover.py --mode quick|full|status|rescore [--max-domains N]
  quick   = 仅 gnews 2 组 query + 探测上限 8 个新域
  full    = 全部引擎（+OPML +newsnow）+ 探测上限 18 个
  status  = 只打印现有状态表，不联网
  rescore = 门禁升级后用「当前门禁」对全池 trial/active 复判：
            相关性/合法性不达标（确定性失败）降回 candidate；
            瞬时失败（断网/超时/WAF）不动——与生命周期同一语义。
结尾固定打印（供门禁 grep）：
  [discover] SUMMARY net_new=X validated=Y promoted=A state_total=T known_domains=K
任何异常 fail-soft，进程 exit 0（argparse 用法错误除外）。
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import defusedxml.ElementTree as _safe_et

try:  # 同目录复用 collector 的安全解析与实体预处理形态
    import collector as _collector
except ImportError:  # 包内导入兜底（被当作包成员导入时）
    from . import collector as _collector

try:
    import registry as _registry
except ImportError:
    from . import registry as _registry

# 复用 collector 的 defusedxml 安全解析（禁 DTD/实体扩展）与实体白名单
_xml_fromstring = _collector._xml_fromstring
_strip_html = _collector._strip_html
_SAFE_ENTITIES = _collector.RSSCollector._SAFE_ENTITIES

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = ROOT / "state" / "discovered_sources.json"

UA = "Mozilla/5.0 (compatible; ChipDailyBot/1.0; chip-daily-report)"
_MAX_BODY_BYTES = 2 * 1024 * 1024   # 发现层只需标题/链接/日期，2MB 上限足够
_POLITE_INTERVAL = 0.8              # 每域礼貌间隔（秒）
_GNEWS_INTERVAL = 2.0               # Google News 相邻 query 间隔（秒）

# ---- 生命周期参数（抄 Miniflux 设计） ----
OK_INTERVAL = 12 * 3600        # 探测通过 → 12h 后复查
BASE_BACKOFF = 30 * 60         # 失败退避基数 30min
MAX_BACKOFF = 7 * 24 * 3600    # 退避封顶 7 天（frozen 即每周重探一次）
FREEZE_AFTER = 3               # 确定性失败 3 次 → frozen（瞬时失败不冻结）
TRIAL_PASSES = 2               # trial 连续 2 次通过 → active
FRESH_DAYS = 90                # 最新条目 90 天内算新鲜
# 瞬时失败前缀（对抗审查 #5）：网络层不可达/超时/WAF 抖动——不惩罚内容资格、
# 不触发冻结（断网一个下午不应把全池冻死、被 collector 白名单除名）；
# 只有确定性失败（html_shell/not_a_feed/no_entries/low_relevance/stale_feed）
# 才累积 error_count 走 frozen。
TRANSIENT_REASON_PREFIXES = ("fetch_failed:", "probe_error:")
TRANSIENT_MAX_BACKOFF = 24 * 3600   # 瞬时失败退避上限 24h

FEED_PATHS = ("/feed/", "/feed", "/rss", "/rss.xml", "/atom.xml",
              "/feed.xml", "/index.xml", "/feeds/all",
              "/index.rss", "/feed.rss")   # 后两个补 Ghost/老式博客形态

# 移动端镜像首标签：从不承载 feed，且是最激进的 WAF；探测前规范化到发布方主域
_MOBILE_LABELS = ("m", "wap", "touch", "mobile", "i")

GNEWS_LANG_PARAMS = {
    "zh-CN": {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
    "en-US": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
}
# quick = 2 组 query（中英各一）；full 追加 3 组
GNEWS_QUERIES_QUICK = {
    "zh-CN": ["(半导体 OR 芯片 OR 晶圆厂) when:7d"],
    "en-US": ["(semiconductor OR chip OR wafer fab) when:7d"],
}
GNEWS_QUERIES_FULL_EXTRA = {
    "zh-CN": ["(先进封装 OR 光刻 OR 出口管制) when:7d"],
    "en-US": ['(TSMC OR Samsung OR "SK hynix") when:7d',
              '(HBM OR chiplet OR "export control") when:7d',
              '(Ryzen OR Radeon OR GeForce OR motherboard) when:7d'],
}
# 末条为硬件垂类 query（2026-09-26 两轮回测实证）：芯片垂类博客（wccftech /
# videocardz 一类）几乎都有干净 feed 且能过相关性门，但被财经门户的原始
# hits 压住；用硬件词主动打捞，是修「发现质量」而非放宽验证门槛。

OPML_URLS = (
    "https://raw.githubusercontent.com/aiworkflowpro/awesome-rss-feeds-list/main/feeds/en-news.opml",
    "https://raw.githubusercontent.com/fuxiaoai/tidings-rss/main/tidings-top200.opml",
)
OPML_SAMPLE_CAP = 60   # 按文档序采样上限

NEWSNOW_BASE = "https://newsnow.busiyi.world/api/s"
NEWSNOW_IDS = ("cls-hot", "wallstreetcn-hot", "gelonghui")

# 相关性词典（中英）；判定：不同关键词命中 ≥3 且有命中的条目数 ≥2。
# 英文词按 \b 词边界匹配（对抗审查 #1：纯子串下 chiptune 命中 chip、
# medal 命中 eda、石版画 lithograph 命中 litho，可刷过相关性门）；
# 中文无词边界概念，保持子串匹配。
CHIP_KW_EN = (
    "semiconductor", "chip", "wafer", "foundry", "fab", "tsmc", "samsung",
    "sk hynix", "micron", "nvidia", "amd", "intel", "asml",
    "hbm", "dram", "nand", "euv", "lithography", "packaging", "chiplet",
    "cowos", "eda", "synopsys", "cadence", "gaa", "smic", "export control",
    "tapeout", "photomask",
)
# 中文（对抗审查 #6：补齐国产链公司名、政策机构词与设备材料环节词，
# 消除「同义英文句过门、中文句零分」的偏科）
CHIP_KW_ZH = (
    "半导体", "芯片", "晶圆", "光刻", "制程", "代工", "存储", "封测",
    "先进封装", "光刻胶", "电子特气", "硅片", "出口管制", "集成电路",
    "台积电", "中芯国际", "华虹", "三星", "海力士", "美光", "英伟达",
    "北方华创", "中微公司", "长电科技", "实体清单", "芯片法案",
    "国家大基金", "大基金", "靶材", "抛光垫", "载板", "引线框架",
    "刻蚀", "离子注入", "光刻机", "流片", "晶圆厂", "成熟制程",
    "先进制程", "存储芯片", "AI芯片",
)
CHIP_KW = CHIP_KW_EN + CHIP_KW_ZH
# 英文词编译为词边界正则（容忍复数 s/es：fab/fabs、chip/chips）
_KW_PATTERNS = tuple(
    [(kw, re.compile(rf"\b{re.escape(kw)}(?:s|es)?\b", re.I)) for kw in CHIP_KW_EN]
    + [(kw, None) for kw in CHIP_KW_ZH]
)


def _kw_hits_in(text: str) -> set:
    """返回 text 命中的关键词集合（英文词边界、中文子串）。"""
    hits = set()
    for kw, pat in _KW_PATTERNS:
        if pat is not None:
            if pat.search(text):
                hits.add(kw)
        elif kw in text:
            hits.add(kw)
    return hits


# ============================================================
# 安全抓取形态（发现层专用，无静态白名单）
# ============================================================
def _assert_safe_url(url: str) -> None:
    """发现层专用 URL 校验：https-only + DNS 解析后逐 IP 拒受限地址。

    发现层要探测未知域名，不能有静态白名单；防线 = scheme 校验 + 解析 IP
    拒私网/回环/链路本地/保留/多播/未指定 + 响应体大小上限（见 _fetch）
    + 每域礼貌间隔。DNS 不可达时不在此阻塞（离线环境交给 urlopen 自然失败，
    同 collector 形态）。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"仅允许 https 抓取：{url}")
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:  # 防内网单标签主机名（如 http://intranet）
        raise ValueError(f"非法主机名：{host!r}")
    try:
        infos = socket.getaddrinfo(host, 443)
    except OSError:
        return
    for info in infos:
        addr = str(info[4][0]).split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"域名解析到受限地址：{host} -> {addr}")


_LAST_HIT: dict[str, float] = {}   # 每域上次请求时刻（模块级，礼貌间隔）


def _polite_wait(url: str, interval: float | None = None) -> None:
    """同域请求前 sleep 补足礼貌间隔（≥0.8s），降低对目标站压力。
    interval 缺省在调用时读模块常量（测试可归零）。"""
    interval = _POLITE_INTERVAL if interval is None else interval
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    now = time.time()
    last = _LAST_HIT.get(host)
    if last is not None:
        wait = interval - (now - last)
        if wait > 0:
            time.sleep(wait)
    _LAST_HIT[host] = time.time()


class _DiscoverRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向逐跳安全校验（对抗审查 #4）：301/302/307 的落点必须重新通过
    _assert_safe_url（https-only + 解析 IP 拒私网/回环），否则阻断——
    首跳校验不覆盖重定向落点 = 攻击者可 302 把探测请求带去内网/任意地址。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_safe_url(str(newurl))  # 不通过则抛 ValueError，探测按失败处理
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str, timeout: int = 12, no_proxy: bool = False) -> bytes:
    """安全抓取：URL 校验 + 每域礼貌间隔 + 响应体大小上限 + 双路径回退
    + 重定向逐跳校验（_DiscoverRedirectHandler）。

    路径策略：默认先走系统代理、失败自动换直连重试一次；显式 no_proxy=True
    则先直连、失败换系统代理（cninfo / newsnow 等国内站实测必须直连）。
    404（确定性答案）与超时（站太慢本就不宜做自动源）不重试。
    校验按 _assert_safe_url 同一防线显式内联展开（满足静态审计的同函数
    可见性），末尾再调 _assert_safe_url 双保险。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"仅允许 https 抓取：{url}")
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        raise ValueError(f"非法主机名：{host!r}")
    try:
        infos = socket.getaddrinfo(host, 443)
    except OSError:
        infos = []  # 离线环境：DNS 不可达不在此阻塞
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
    last_err: Exception | None = None
    # (是否直连) 序列：默认代理→直连；显式 no_proxy 则直连→代理
    attempts = (True, False) if no_proxy else (False, True)
    for i, direct in enumerate(attempts):
        _polite_wait(url)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            if direct:
                # 直连 opener：关代理 + 重定向逐跳校验
                opener = urllib.request.build_opener(
                    _DiscoverRedirectHandler(), urllib.request.ProxyHandler({}))
                resp = opener.open(req, timeout=timeout)
            else:
                # 默认 opener：走系统代理（ProxyHandler 读环境变量）+ 重定向校验
                opener = urllib.request.build_opener(_DiscoverRedirectHandler())
                resp = opener.open(req, timeout=timeout)
            with resp:
                return resp.read(_MAX_BODY_BYTES)
        except urllib.error.HTTPError as e:
            last_err = e
            if getattr(e, "code", 0) == 404:
                raise  # 404 是确定答案，换路径无意义
        except (socket.timeout, TimeoutError):
            raise  # 站点响应过慢：本就不适合做自动源，如实失败
        except Exception as e:
            last_err = e
        if i == 0 and last_err is not None:
            print(f"[discover:fetch] {url} 走{'直连' if attempts[0] else '系统代理'}"
                  f"失败（{type(last_err).__name__}），换路径重试")
    raise last_err  # type: ignore[misc]


# ============================================================
# XML / feed 解析（容错同 collector）
# ============================================================
def _preprocess_xml(text: str) -> str:
    """XML 解析前预处理（同 collector.RSSCollector._parse 白名单思路）：
    裸 &（非实体开头）转义 + 常见 HTML 命名实体替换为字面字符。"""
    if not text:
        return text
    text = re.sub(r"&(?![a-zA-Z#][a-zA-Z0-9#]*;)", "&amp;", text)
    text = re.sub(r"&([a-zA-Z][a-zA-Z0-9]*);",
                  lambda m: _SAFE_ENTITIES.get(m.group(1), m.group(0)), text)
    return text


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _find_child(el, name):
    for child in el:
        if _local(child.tag) == name:
            return child
    return None


def _child_text(el, name) -> str:
    c = _find_child(el, name)
    return (c.text or "") if c is not None else ""


def _normalize_date(raw: str) -> str:
    """RFC822 / ISO8601 → YYYY-MM-DD；解析失败返回空串。"""
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except Exception:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _entry_date(el) -> str:
    """条目日期兜底链：pubDate(RSS2.0) → published/updated(Atom)
    → date（dc:date 命名空间本地名，Nikkei RDF 需要）。"""
    for name in ("pubDate", "published", "updated", "date"):
        d = _normalize_date(_child_text(el, name))
        if d:
            return d
    return ""


def parse_feed_entries(xml_text: str) -> list[dict]:
    """宽容解析 feed 条目：RSS2.0 item + RDF item + Atom entry。
    title/link/pubDate/dc:date/description，容错同 collector
    （HTML 命名实体白名单 + 裸 & 转义 + defusedxml 禁 DTD/实体）。"""
    try:
        root = _xml_fromstring(_preprocess_xml(xml_text or ""))
    except Exception as e:
        print(f"[discover] XML 解析失败：{e}")
        return []
    out: list[dict] = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = _child_text(el, "title").strip()
        if not title:
            continue
        link = _child_text(el, "link").strip()
        if not link:  # Atom 形态：链接在 href 属性
            lc = _find_child(el, "link")
            if lc is not None:
                link = (lc.get("href") or "").strip()
        desc = _strip_html(_child_text(el, "description")
                           or _child_text(el, "summary")
                           or _child_text(el, "encoded"))
        # Google News 形态：<source url="出版方域名">（发现新源的关键）
        src = _find_child(el, "source")
        publisher = (src.get("url") or "").strip() if src is not None else ""
        out.append({"title": title, "link": link, "date": _entry_date(el),
                    "description": desc, "publisher": publisher})
    return out


# ============================================================
# 引擎1：Google News RSS 出版方域名计频
# ============================================================
_LAST_GNEWS_HIT = [0.0]   # 可变容器，记录上次 gnews 请求时刻


def gnews_url(query: str, lang: str) -> str:
    p = GNEWS_LANG_PARAMS.get(lang, GNEWS_LANG_PARAMS["en-US"])
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
            f"&hl={p['hl']}&gl={p['gl']}&ceid={p['ceid']}")


def gnews_domains(queries, lang: str = "zh-CN") -> dict:
    """拉 Google News RSS，从条目 <source> 的 url 属性提取出版方域名并计频。
    返回 {domain: {"hits": n, "sample_titles": [...]}}。
    相邻 query 间隔 ≥2s（_GNEWS_INTERVAL，测试可调 0）。单查询失败跳过。"""
    out: dict[str, dict] = {}
    for i, q in enumerate(queries):
        url = gnews_url(q, lang)
        if i:  # 相邻 query 礼貌间隔
            wait = _GNEWS_INTERVAL - (time.time() - _LAST_GNEWS_HIT[0])
            if wait > 0:
                time.sleep(wait)
        _LAST_GNEWS_HIT[0] = time.time()
        try:
            body = _fetch(url).decode("utf-8", "ignore")
        except Exception as e:
            print(f"[discover:gnews] 查询失败跳过 {q!r}：{e}")
            continue
        for e in parse_feed_entries(body):
            d = _norm_host(e.get("publisher") or "")
            if not d:
                continue
            rec = out.setdefault(d, {"hits": 0, "sample_titles": []})
            rec["hits"] += 1
            if len(rec["sample_titles"]) < 3:
                rec["sample_titles"].append(e["title"][:100])
    return out


# ============================================================
# 引擎2：OPML 订阅清单采样
# ============================================================
def opml_candidates() -> list[str]:
    """下载公开 OPML 订阅清单，按文档序采样 outline 的 xmlUrl 属性
    （上限 60 条，文档序去重）。允许单个清单失败跳过（fail-soft）。"""
    urls: list[str] = []
    seen: set[str] = set()
    for u in OPML_URLS:
        try:
            body = _fetch(u, timeout=15).decode("utf-8", "ignore")
        except Exception as e:
            print(f"[discover:opml] 下载失败跳过：{u}：{e}")
            continue
        try:
            root = _xml_fromstring(_preprocess_xml(body))
        except Exception as e:
            print(f"[discover:opml] OPML 解析失败跳过：{u}：{e}")
            continue
        for el in root.iter():
            xurl = (el.get("xmlUrl") or "").strip()
            if xurl.startswith("http") and xurl not in seen:
                seen.add(xurl)
                urls.append(xurl)
    return urls[:OPML_SAMPLE_CAP]


# ============================================================
# 引擎3：newsnow 热榜域名提取
# ============================================================
def newsnow_domains() -> dict:
    """newsnow 3 个热榜 id 的 items[].url 提取域名（no_proxy 直连）。
    返回 {domain: {"hits": n, "sample_titles": [...]}}。单榜失败跳过。"""
    out: dict[str, dict] = {}
    for nid in NEWSNOW_IDS:
        url = f"{NEWSNOW_BASE}?id={urllib.parse.quote(nid)}"
        try:
            payload = json.loads(_fetch(url, no_proxy=True).decode("utf-8", "ignore"))
        except Exception as e:
            print(f"[discover:newsnow] {nid} 拉取失败跳过：{e}")
            continue
        rows = payload.get("items") or [] if isinstance(payload, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            d = _norm_host(str(row.get("url") or ""))
            if not d:
                continue
            rec = out.setdefault(d, {"hits": 0, "sample_titles": []})
            rec["hits"] += 1
            t = str(row.get("title") or "").strip()
            if t and len(rec["sample_titles"]) < 3:
                rec["sample_titles"].append(t[:100])
    return out


# ============================================================
# 已知域过滤（打破信息茧房的增量 = 候选中不在 known 的）
# ============================================================
def _norm_host(h: str) -> str:
    """归一化域名：取 hostname、去尾点、剥一层 www. 前缀。"""
    if not h:
        return ""
    host = (urllib.parse.urlparse(h if "//" in h else f"https://{h}").hostname or "")
    host = host.lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def _canonical_domain(d: str) -> str:
    """发布方主域规范化：在 _norm_host 基础上再剥移动端镜像前缀
    （m. / wap. / touch. / mobile. / i.）。

    依据（2026-09-26 回测实验）：wap.eastmoney.com / m.sohu.com / m.21jingji.com
    这类移动端镜像从不承载 feed 且 WAF 最激进，真正的发布方在主域；主域若已
    在 known（如 21jingji.com 在 registry），归一后自然被增量过滤掉，不浪费
    探测名额。纯通用规则，不含任何写死域名。"""
    host = _norm_host(d)
    if not host:
        return ""
    labels = host.split(".")
    while len(labels) > 2 and labels[0] in _MOBILE_LABELS:
        labels = labels[1:]
    return ".".join(labels)


def _title_kw_hits(sample_titles) -> int:
    """候选质量分：其 Google News 样本标题命中的不同芯片关键词数。
    密度高的发布方大概率是芯片垂类（大概率有可探测的垂类 feed），
    应优先于标题全是宏观/股市的财经门户。"""
    text = " ".join(str(t) for t in sample_titles or []).lower()
    return len(_kw_hits_in(text))


def _build_probe_queue(pool: dict, max_domains: int,
                       group_order=("gnews-en", "gnews-zh", "gnews-en", "newsnow",
                                    "gnews-en", "opml")) -> list:
    """构造探测队列：引擎组间按权重轮转（gnews-en 占 3/6，zh/newsnow/opml
    各 1/6），组内按（样本标题芯片关键词密度 desc, 原始 hits desc）。

    依据（2026-09-26 两轮回测）：第 1 轮按原始 hits 排序，18 个名额被
    wallstreetcn/gelonghui/eastmoney 等 SPA 无 feed 门户占满，validated 仅 1；
    第 2 轮等权轮转下 zh 组候选仍 100% 被拒（无 feed/WAF/壳），en 组有产出
    （wccftech 转 active）——预算按实证产率加权，而非放宽任何验证门槛。"""
    groups: dict = {}
    for d, c in pool.items():
        groups.setdefault(str(c.get("group") or "gnews"), []).append((d, c))
    for rows in groups.values():
        rows.sort(key=lambda kv: (-_title_kw_hits(kv[1].get("sample_titles")),
                                  -int(kv[1].get("hits", 0))))
    present = [g for g in group_order if groups.get(g)]  # 仅保留有货的组次序
    out: list = []
    i = 0
    while len(out) < max_domains and present:
        g = present[i % len(present)]
        out.append(groups[g].pop(0))
        i += 1
        present = [x for x in present if groups.get(x)]  # 弹空的组次序
    return out


def known_domains(state: dict | None = None) -> set:
    """已知域 = registry.SOURCES 的 url 域名 ∪ collector._ALLOWED_HOSTS
    ∪ state 已有 domain 及其 feed 域名。"""
    known = {_norm_host(h) for h in getattr(_collector, "_ALLOWED_HOSTS", set())}
    for s in getattr(_registry, "SOURCES", []) or []:
        h = _norm_host(str(s.get("url") or ""))
        if h:
            known.add(h)
    for rec in (state or {}).get("sources", []) or []:
        if not isinstance(rec, dict):
            continue
        h = _norm_host(str(rec.get("domain") or ""))
        if h:
            known.add(h)
        fh = _norm_host(str(rec.get("feed_url") or ""))
        if fh:
            known.add(fh)
    known.discard("")
    return known


# ============================================================
# feed 自动发现 + 合法性 + 新鲜度 + 相关性
# ============================================================
_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"([a-zA-Z-]+)\s*=\s*[\"']([^\"']*)[\"']")


def feed_links_from_html(html: str, base_url: str) -> list:
    """解析首页 <link rel="alternate" type="application/rss+xml|atom+xml">
    的 href，转绝对 https URL（feed 自动发现标准做法第一步）。"""
    out: list[str] = []
    for m in _LINK_RE.finditer(html or ""):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(m.group(0))}
        if attrs.get("rel", "").lower() != "alternate":
            continue
        t = attrs.get("type", "").lower()
        if "rss+xml" not in t and "atom+xml" not in t:
            continue
        href = (attrs.get("href") or "").strip()
        if not href:
            continue
        absu = urllib.parse.urljoin(base_url, href)
        if absu.startswith("https://"):
            out.append(absu)
    return out


def probe_feed_url(feed_url: str) -> dict:
    """单 feed 探测：合法性（HTML 反爬壳 / 非 feed / 无条目拒绝）
    + 新鲜度（最新条目 90 天内；完全无日期 → unknown 仍算过）。"""
    res = {"feed_url": feed_url, "ok": False, "http_ok": False, "entry_count": 0,
           "entries": [], "last_entry_date": "", "freshness": "", "reason": ""}
    try:
        body = _fetch(feed_url).decode("utf-8", "ignore")
        res["http_ok"] = True
    except Exception as e:
        res["reason"] = f"fetch_failed:{type(e).__name__}"
        return res
    head = body[:4000].lower()
    if "<html" in head:
        # 反爬壳陷阱：HTTP 200 但内容是 HTML（AnandTech 已死站 / DigiTimes 形态）
        res["reason"] = "html_shell"
        return res
    if not ("<rss" in head or "<feed" in head or "<rdf" in head):
        res["reason"] = "not_a_feed"
        return res
    entries = parse_feed_entries(body)
    if not entries:
        res["reason"] = "no_entries"
        return res
    res["entry_count"] = len(entries)
    dates = [e["date"] for e in entries if e["date"]]
    if dates:
        res["last_entry_date"] = max(dates)
        try:
            latest = datetime.strptime(res["last_entry_date"], "%Y-%m-%d").date()
            if latest < datetime.now(timezone.utc).date() - timedelta(days=FRESH_DAYS):
                res["reason"] = "stale_feed"
                return res
        except ValueError:
            pass  # 日期格式异常 → 按 unknown 处理，不拒绝
    res["freshness"] = "ok" if dates else "unknown"
    res["entries"] = entries[:20]
    res["ok"] = True
    return res


# 命中条目占比下限（对抗消防水管全站 feed）。0.30 依据 2026-09-26 实测谱：
# 真垂类 feed 密度 0.35-0.5（tspasemiconductor/eenewseurope/electronicsweekly/
# techpowerup），芯片强相关综合站 0.3（wccftech/electronicsforyou），而
# businesskorea 类全站消防水管只有 0.25 且恰好踩线——0.30 是「芯片内容
# 至少占三成」的可证伪分界，不是针对单一站点的调参。
RELEVANCE_MIN_RATIO = 0.30


def score_relevance(entries: list) -> dict:
    """相关性打分：命中过的不同关键词数 + 有命中的条目数 + 命中密度。
    英文关键词按词边界匹配（_kw_hits_in），中文按子串。"""
    kws: set = set()
    hit_entries = 0
    for e in entries:
        text = (str(e.get("title", "")) + " " + str(e.get("description", ""))).lower()
        hit = _kw_hits_in(text)
        if hit:
            hit_entries += 1
            kws |= hit
    ratio = hit_entries / len(entries) if entries else 0.0
    return {"kw_hits": len(kws), "entry_hits": hit_entries,
            "hit_ratio": round(ratio, 3), "matched": sorted(kws)[:12]}


def is_relevant(score: dict) -> bool:
    """判定（三条件，缺一不可）：
      1) 不同关键词命中 ≥3（单一条目堆砌一个话题刷不满）；
      2) 有命中的条目数 ≥2（孤条偶然命中不算垂类）；
      3) 命中条目占比 ≥25%（对抗审查复判发现：businesskorea/gagadget 类
         全站消防水管 feed 靠几十条里凑 2 条提 Samsung/芯片刷过绝对数门槛
         ——密度才度量「这是不是芯片垂类 feed」）。"""
    return (score.get("kw_hits", 0) >= 3
            and score.get("entry_hits", 0) >= 2
            and score.get("hit_ratio", 0.0) >= RELEVANCE_MIN_RATIO)


def probe_domain(domain: str, feed_hint: str = "", hint_via: str = "hint") -> dict:
    """域名级探测：feed 自动发现（首页 link 标签 → 路径清单兜底）
    → 合法性 + 新鲜度 + 相关性打分。返回统一探测结果 dict（不抛异常）。
    hint_via 区分 feed_hint 来源：OPML 清单直给="hint"，生命周期复核
    传已知 feed_url="recheck"（对抗审查 #2：两者语义不同，不得混用）。"""
    domain = _norm_host(domain)
    result = {"domain": domain, "homepage": f"https://{domain}/", "ok": False,
              "relevant": False, "feed_url": "", "discovered_via": "",
              "score": {"kw_hits": 0, "entry_hits": 0}, "reason": "",
              "last_entry_date": "",
              "evidence": {"http_ok": False, "entry_count": 0, "sample_titles": []}}
    if not domain:
        result["reason"] = "bad_domain"
        return result
    # 1) 候选 feed URL：hint（OPML 直给）→ 首页 link 标签 → 常见路径清单
    candidates: list = []
    seen_fu: set = set()

    def _add(fu: str, via: str) -> None:
        fu = (fu or "").strip()
        if fu.startswith("https://") and fu not in seen_fu:
            seen_fu.add(fu)
            candidates.append((fu, via))

    if feed_hint:
        _add(feed_hint, hint_via)
    try:
        html = _fetch(result["homepage"], timeout=10).decode("utf-8", "ignore")
        for u in feed_links_from_html(html, result["homepage"])[:3]:
            _add(u, "link_tag")
    except Exception as e:
        print(f"[discover] {domain} 首页抓取失败（转路径清单兜底）：{e}")
    # 路径清单始终作为兜底追加（2026-09-26 回测：部分站首页 link 标签指向
    # 死链，路径清单里才有活 feed；_add 去重保证不重复探测）
    for p in FEED_PATHS:
        _add(f"https://{domain}{p}", "path_list")
    # 2) 逐个试，第一个合法 feed 胜出
    best_fail = ""
    for fu, via in candidates:
        pr = probe_feed_url(fu)
        if pr["ok"]:
            score = score_relevance(pr["entries"])
            rel = is_relevant(score)
            result.update({
                "ok": True, "feed_url": fu, "discovered_via": via,
                "score": {"kw_hits": score["kw_hits"], "entry_hits": score["entry_hits"]},
                "relevant": rel,
                "reason": "" if rel else "low_relevance",
                "last_entry_date": pr["last_entry_date"],
                "evidence": {
                    "http_ok": True, "entry_count": pr["entry_count"],
                    "sample_titles": [e["title"][:80] for e in pr["entries"][:3]],
                },
            })
            return result
        best_fail = pr["reason"]
    result["reason"] = best_fail or "no_valid_feed"
    return result


# ============================================================
# 生命周期状态机（抄 Miniflux：error_count / next_check_at / state）
# ============================================================
def backoff_seconds(error_count: int) -> float:
    """指数退避：30min * 2^error_count，封顶 7 天。"""
    return min(float(BASE_BACKOFF) * (2 ** max(int(error_count), 0)), float(MAX_BACKOFF))


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def update_lifecycle(state: dict, results: list, now: float | None = None) -> dict:
    """状态机推进：
      探测通过 → candidate→trial；trial 连续 2 次通过 → active；
      frozen 重探通过 → 复活回 trial；失败 error_count+1 且
      next_check_at = now + min(30min*2^error_count, 7天)；error_count≥3 → frozen
      （冻结池保留，不删除）。
    返回 {"validated": 本次探测通过数, "promoted": trial→active 数}。"""
    now = float(now if now is not None else time.time())
    now_iso = _iso(now)
    sources = state.setdefault("sources", [])
    by_domain = {s.get("domain"): s for s in sources if isinstance(s, dict)}
    validated = promoted = 0
    for r in results:
        domain = str(r.get("domain") or "")
        rec = by_domain.get(domain)
        if r.get("ok") and r.get("relevant"):
            validated += 1
            if rec is None:  # 新源首次通过 → 入池
                rec = {"id": domain, "domain": domain,
                       "feed_url": r.get("feed_url", ""),
                       "homepage": r.get("homepage", f"https://{domain}/"),
                       "discovered_via": r.get("discovered_via", ""),
                       "state": "candidate",
                       "score": {"kw_hits": 0, "entry_hits": 0},
                       "error_count": 0, "consecutive_ok": 0,
                       "last_checked": "", "next_check_at": 0,
                       "last_entry_date": "", "evidence": {}}
                sources.append(rec)
                by_domain[domain] = rec
            rec["feed_url"] = r.get("feed_url") or rec.get("feed_url", "")
            # 对抗审查 #2：复核时 feed_hint 会命中（probe 走已知 feed_url），
            # 但 discovered_via 表达的是「首次发现渠道」，不得被复核覆盖——
            # 否则 gnews 首发现的源会被错标成 hint（现网 8 个 active 全被
            # 错标 hint 的根因）。仅在原值为空时写入。
            if not rec.get("discovered_via"):
                rec["discovered_via"] = r.get("discovered_via") or ""
            rec["score"] = r.get("score") or rec.get("score") or {"kw_hits": 0, "entry_hits": 0}
            rec["last_entry_date"] = r.get("last_entry_date", "")
            rec["evidence"] = r.get("evidence") or rec.get("evidence") or {}
            rec["error_count"] = 0
            rec["consecutive_ok"] = int(rec.get("consecutive_ok", 0)) + 1
            rec["last_checked"] = now_iso
            rec["next_check_at"] = now + OK_INTERVAL
            if rec.get("state") == "candidate":
                rec["state"] = "trial"            # candidate 通过探测 → trial
            elif rec.get("state") == "frozen":
                rec["state"] = "trial"            # 冻结池重探复活
                rec["consecutive_ok"] = 1
            if rec.get("state") == "trial" and rec["consecutive_ok"] >= TRIAL_PASSES:
                rec["state"] = "active"           # trial 连续 2 次通过 → active
                promoted += 1
        else:
            reason = str(r.get("reason") or "probe_failed")
            transient = reason.startswith(TRANSIENT_REASON_PREFIXES)
            if rec is None:
                # 失败候选也入池（state=candidate，带退避）：不这样做的话，
                # 同一批死域（无 feed 门户/WAF 站）每轮都重占探测名额——
                # 2026-09-26 回测两轮均复现。退避期内不再探测；下次探测通过
                # 即翻案为 trial，通道保留。
                rec = {"id": domain, "domain": domain,
                       "feed_url": r.get("feed_url", ""),
                       "homepage": r.get("homepage", f"https://{domain}/"),
                       "discovered_via": r.get("discovered_via", ""),
                       "state": "candidate",
                       "score": {"kw_hits": 0, "entry_hits": 0},
                       "error_count": 0, "consecutive_ok": 0,
                       "last_checked": "", "next_check_at": 0,
                       "last_entry_date": "", "evidence": {}}
                sources.append(rec)
                by_domain[domain] = rec
            rec["consecutive_ok"] = 0
            rec["last_checked"] = now_iso
            rec["last_error"] = reason[:120]
            if transient:
                # 瞬时失败（断网/超时/WAF 抖动）：短退避重试，不累积
                # error_count、不冻结、state 不变（trial/active 不被 collector
                # 白名单除名）——对抗审查 #5
                rec["transient_errors"] = int(rec.get("transient_errors", 0)) + 1
                rec["next_check_at"] = now + min(
                    BASE_BACKOFF * (2 ** min(int(rec["transient_errors"]), 6)),
                    TRANSIENT_MAX_BACKOFF)
            else:
                # 确定性失败（html_shell/not_a_feed/no_entries/low_relevance/
                # stale_feed）：累积 error_count，3 次 → frozen
                rec["error_count"] = int(rec.get("error_count", 0)) + 1
                rec["next_check_at"] = now + backoff_seconds(rec["error_count"])
                if rec["error_count"] >= FREEZE_AFTER:
                    rec["state"] = "frozen"       # 连续 3 败冻结（保留不删）
    return {"validated": validated, "promoted": promoted}


# ============================================================
# 状态文件 IO（原子写回）
# ============================================================
def load_state(path=None) -> dict:
    """读状态文件；不存在 / 损坏 / 结构不对 → 返回空骨架（fail-soft）。"""
    p = Path(path or STATE_PATH)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sources"), list):
            data.setdefault("version", 1)
            return data
    except Exception:
        pass
    return {"version": 1, "updated": "", "sources": []}


def save_state(state: dict, path=None) -> None:
    """原子写回：先写 .tmp 再 os.replace，避免半写文件。"""
    p = Path(path or STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ============================================================
# 一次完整运行：发现 → 过滤 → 探测 → 纳入
# ============================================================
def _merge_candidates(pool: dict, hits: dict, via: str, group: str = "gnews",
                      feed_hints: dict | None = None) -> None:
    """把引擎产出合并进候选池：键用发布方主域规范化（移动镜像并入主域），
    同域叠加 hits，保留样本标题与 feed 提示，记录引擎组供队列轮转。"""
    for raw_d, r in hits.items():
        d = _canonical_domain(raw_d)
        if not d:
            continue
        rec = pool.setdefault(d, {"hits": 0, "sample_titles": [], "via": via,
                                  "group": group, "feed_hint": ""})
        rec["hits"] += int(r.get("hits", 0))
        for t in r.get("sample_titles", []):
            if len(rec["sample_titles"]) < 3 and t not in rec["sample_titles"]:
                rec["sample_titles"].append(t)
        if feed_hints and not rec["feed_hint"]:
            rec["feed_hint"] = feed_hints.get(d, "") or feed_hints.get(raw_d, "")


def _next_ts(s: dict) -> float:
    try:
        return float(s.get("next_check_at") or 0)
    except (TypeError, ValueError):
        return 0.0   # 脏数据视作最早到期


def _select_due(state: dict, now: float, cap: int) -> list:
    """到期复查选择：trial 是试用期（未定信），每次运行必复核；
    active/frozen/candidate 按 next_check_at 到期。trial 最多占 cap 的 1/3
    （至少 1 个），防止存量复核挤压新域发现预算。"""
    trials, by_time = [], []
    for s in state.get("sources", []):
        if not isinstance(s, dict):
            continue
        if str(s.get("state")) == "trial":
            trials.append(s)
        elif _next_ts(s) <= now:
            by_time.append(s)
    trials.sort(key=_next_ts)
    by_time.sort(key=_next_ts)
    return (trials[:max(1, cap // 3)] + by_time)[:cap]


def run_discovery(mode: str = "quick", max_domains: int | None = None,
                  state_path=None) -> dict:
    """一次完整 发现→验证→纳入 运行（fail-soft，不抛出），返回统计 dict。
    quick = gnews 2 组 query + 探测上限 8 个新域；
    full  = 全部引擎 + 探测上限 18 个（同时复查到期的存量源，推进生命周期）。"""
    max_domains = int(max_domains or (8 if mode == "quick" else 18))
    state = load_state(state_path)
    now = time.time()

    # ---- 引擎产出候选池（键=发布方主域，组=gnews-zh/gnews-en/newsnow/opml）----
    pool: dict = {}
    try:
        query_sets = {k: list(v) for k, v in GNEWS_QUERIES_QUICK.items()}
        if mode == "full":
            for lang, qs in GNEWS_QUERIES_FULL_EXTRA.items():
                query_sets.setdefault(lang, []).extend(qs)
        for lang, qs in query_sets.items():
            group = "gnews-zh" if lang.startswith("zh") else "gnews-en"
            _merge_candidates(pool, gnews_domains(qs, lang), "gnews", group=group)
    except Exception as e:
        print(f"[discover] gnews 引擎异常跳过：{e}")
    if mode == "full":
        try:
            hints: dict = {}
            for u in opml_candidates():
                d = _canonical_domain(u)
                if d and d not in hints:
                    hints[d] = u
            _merge_candidates(pool, {d: {"hits": 1, "sample_titles": []} for d in hints},
                              "opml", group="opml", feed_hints=hints)
        except Exception as e:
            print(f"[discover] opml 引擎异常跳过：{e}")
        try:
            _merge_candidates(pool, newsnow_domains(), "newsnow", group="newsnow")
        except Exception as e:
            print(f"[discover] newsnow 引擎异常跳过：{e}")

    # ---- 已知域过滤：net-new 就是打破信息茧房的增量 ----
    known = known_domains(state)
    known_norm = {_canonical_domain(k) for k in known}
    net_new = {d: c for d, c in pool.items() if _canonical_domain(d) not in known_norm}

    # ---- 探测：先到期复查（生命周期推进），再新域（组间轮转 + 芯片密度排序）----
    results: list = []
    for s in _select_due(state, now, max_domains):
        d = str(s.get("domain") or "")
        try:
            results.append(probe_domain(d, feed_hint=str(s.get("feed_url") or ""),
                                        hint_via="recheck"))
        except Exception as e:
            print(f"[discover] {d or '?'} 复查异常按失败处理：{e}")
            results.append({"domain": d, "ok": False, "relevant": False,
                            "reason": f"probe_error:{type(e).__name__}"})
    queue = _build_probe_queue(net_new, max_domains)
    for d, c in queue:
        try:
            r = probe_domain(d, feed_hint=str(c.get("feed_hint") or ""))
            r["discovered_via"] = c.get("via", "")
            results.append(r)
        except Exception as e:
            print(f"[discover] {d} 探测异常按失败处理：{e}")
            results.append({"domain": d, "ok": False, "relevant": False,
                            "reason": f"probe_error:{type(e).__name__}"})

    # ---- 纳入 + 原子写回 ----
    stats = update_lifecycle(state, results)
    state["version"] = 1
    state["updated"] = _iso(time.time())
    try:
        save_state(state, state_path)
    except Exception as e:
        print(f"[discover] 状态文件写回失败（不影响本次结果）：{e}")
    state_total = len(state.get("sources", []))
    known_total = len(known_domains(state))
    print(f"[discover] SUMMARY net_new={len(net_new)} validated={stats['validated']} "
          f"promoted={stats['promoted']} state_total={state_total} "
          f"known_domains={known_total}")
    return {"net_new": len(net_new), "validated": stats["validated"],
            "promoted": stats["promoted"], "state_total": state_total,
            "known_domains": known_total}


# ============================================================
# v8 R4 产出问责（2026-09-28）：「机制自主≠产出自主」的记账断根。
# 每次运行按「首次发现渠道」给 validated 池对账：非种子渠道
# （gnews/newsnow 等自主发现）validated=0 时如实宣布「发现层=机制演示」。
# ============================================================
VALIDATED_STATES = ("trial", "active")


def production_accounting(state_path=None) -> dict:
    """validated 池按发现渠道拆分对账（只读状态文件，不联网）。"""
    state = load_state(state_path)
    srcs = [s for s in state.get("sources", []) if isinstance(s, dict)]
    validated = [s for s in srcs if s.get("state") in VALIDATED_STATES]
    # 宁严勿宽：非种子渠道取显式名单（gnews*/newsnow），缺失/未知渠道
    # 一律按种子计——demo_mode 判定宁苛刻勿粉饰
    nonseed = []
    for s in validated:
        via = str(s.get("discovered_via") or "")
        if via.startswith("gnews") or via == "newsnow":
            nonseed.append(s)
    return {
        "state_total": len(srcs),
        "validated": len(validated),
        "seed_validated": len(validated) - len(nonseed),
        "nonseed_validated": len(nonseed),
        "nonseed_domains": [str(s.get("domain") or "") for s in nonseed],
        "demo_mode": len(nonseed) == 0,
    }


def print_accounting(acc: dict) -> None:
    tag = "机制演示" if acc["demo_mode"] else "有产出"
    print(f"[discover:问责] 产出状态={tag} validated={acc['validated']} "
          f"(种子 {acc['seed_validated']} / 非种子 {acc['nonseed_validated']}) "
          f"非种子域={', '.join(acc['nonseed_domains']) or '无'}")
    if acc["demo_mode"]:
        print("[discover:问责] ⚠ 发现层=机制演示：非种子渠道 validated=0——"
              "自主发现零产出，如实宣布不粉饰（v7 复盘教训的记账断根）")


def print_status(state_path=None) -> None:
    """status 模式：只打印现有状态表，不联网。"""
    state = load_state(state_path)
    sources = [s for s in state.get("sources", []) if isinstance(s, dict)]
    print(f"[discover] 状态文件 {state_path or STATE_PATH}")
    print(f"[discover] updated={state.get('updated') or '-'} sources={len(sources)}")
    now = time.time()
    for s in sources:
        nxt = _next_ts(s)
        due = "due" if nxt <= now else f"{(nxt - now) / 3600:.0f}h"
        print(f"  [{str(s.get('state', '?')):8}] {str(s.get('domain', '?')):38} "
              f"err={s.get('error_count', 0)} ok={s.get('consecutive_ok', 0)} "
              f"next={due:<5} {str(s.get('feed_url', ''))[:80]}")
    if not sources:
        print("  （空——先跑 --mode quick 产出候选）")
    print(f"[discover] SUMMARY net_new=0 validated=0 promoted=0 "
          f"state_total={len(sources)} known_domains={len(known_domains(state))}")
    print_accounting(production_accounting(state_path))


def rescore_pool(state_path=None) -> dict:
    """rescore 模式：门禁升级后，用「当前门禁」对全池 trial/active 复判。

    背景（2026-09-26 第 4 轮）：现存 active 池是在英文词边界修复前的
    子串相关性门下转正的，混入游戏/比价类站点；等确定性失败 3 次自然
    清洗太慢且浪费探测预算。规则对全池一视同仁、不手工点名：
      - 复判通过且仍相关 → 保留，刷新 last_checked 与样本证据；
      - 复判为确定性失败（low_relevance / not_a_feed / html_shell 等）
        → 降回 candidate，计数归零、按退避到期，证据记 rescore 结论；
      - 复判为瞬时失败（fetch_failed/probe_error）→ 不动（瞬时失败
        不惩罚内容资格，与 update_lifecycle 同语义）。
    fail-soft：任何单源异常跳过，状态文件写回失败不影响退出码。
    """
    state = load_state(state_path)
    now = time.time()
    checked = demoted = kept = skipped = 0
    for s in state.get("sources", []):
        if not isinstance(s, dict) or s.get("state") not in ("trial", "active"):
            continue
        feed_url = str(s.get("feed_url") or "")
        if not feed_url:
            continue
        checked += 1
        try:
            pr = probe_feed_url(feed_url)
        except Exception as e:  # 探测器自身异常按瞬时处理，不惩罚
            print(f"[discover:rescore] {s.get('domain')} 探测异常跳过：{e}")
            skipped += 1
            continue
        ev = s["evidence"] if isinstance(s.get("evidence"), dict) else {}
        if not pr.get("ok"):
            reason = str(pr.get("reason") or "probe_error")
            if reason.startswith(TRANSIENT_REASON_PREFIXES):
                skipped += 1
                continue
            s["state"] = "candidate"
            s["error_count"] = 0
            s["consecutive_ok"] = 0
            s["next_check_at"] = now + backoff_seconds(0)
            ev["rescore"] = f"{_iso(now)} demoted:{reason}"
            s["evidence"] = ev
            demoted += 1
            print(f"[discover:rescore] {s.get('domain')} 降回 candidate（{reason}）")
            continue
        if is_relevant(score_relevance(pr.get("entries") or [])):
            kept += 1
            s["last_checked"] = _iso(now)
            ev["rescore"] = f"{_iso(now)} kept"
            ev["sample_titles"] = [e["title"][:80] for e in (pr.get("entries") or [])[:3]]
            s["evidence"] = ev
        else:
            s["state"] = "candidate"
            s["error_count"] = 0
            s["consecutive_ok"] = 0
            s["next_check_at"] = now + backoff_seconds(0)
            ev["rescore"] = f"{_iso(now)} demoted:low_relevance"
            s["evidence"] = ev
            demoted += 1
            print(f"[discover:rescore] {s.get('domain')} 降回 candidate（low_relevance）")
    state["updated"] = _iso(time.time())
    try:
        save_state(state, state_path)
    except Exception as e:
        print(f"[discover] 状态文件写回失败（不影响本次结果）：{e}")
    print(f"[discover] RESCORE checked={checked} demoted={demoted} "
          f"kept={kept} skipped_transient={skipped}")
    return {"checked": checked, "demoted": demoted, "kept": kept,
            "skipped_transient": skipped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="芯片行业日报 · 自主源发现层 v1")
    parser.add_argument("--mode", choices=["quick", "full", "status", "rescore"],
                        default="quick",
                        help="quick=gnews 2 组 query + 8 新域；full=全引擎 + 18 新域；"
                             "status=不联网；rescore=门禁升级后全池复判")
    parser.add_argument("--max-domains", type=int, default=None,
                        help="本次探测的新域上限（覆盖模式默认值）")
    args = parser.parse_args(argv)
    try:
        if args.mode == "status":
            print_status()
        elif args.mode == "rescore":
            rescore_pool()
        else:
            run_discovery(args.mode, args.max_domains)
            print_accounting(production_accounting())  # v8 R4 产出问责
    except Exception as e:  # fail-soft：任何异常不改变退出码
        print(f"[discover] 运行异常（fail-soft）：{e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
