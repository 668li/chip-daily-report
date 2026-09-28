#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.article_fetch — 文章正文安全抓取（v8 R2 源深水区，2026-09-28）。

定位：日报引用的「文章级 URL」正文抓取，供两处消费——
  1. prepare_candidates：给 top 候选附 body_full（生成会话读原文，不再只看
     RSS 160 字摘要）；
  2. validate_claims（声明级对账门禁）：承重数字逐条对照原文，对不上不出版。

安全模型（与 collector.py 同源并如实放大的部分）：
  - https-only + 发请求前校验 host + 拒绝解析到私网/回环/链路本地/保留地址
  - 重定向逐跳重新校验（对抗 302 带去内网）
  - 响应体 5MB 上限、超时控制
  - 白名单口径与 collector 不同，如实说明：collector 白名单约束的是「发现式
    采集」（输入空间=注册源 feed）；本模块只抓「日报已引用的文章 URL」——
    每次抓取目标=读者会被引导点开的同一链接，白名单=静态 feed 域 ∪ 发现层
    动态源域 ∪ rule_registry.yaml 分级域名 ∪ 报告自身引用域（cited），
    且单次运行有抓取条数上限、无链接外递归。
  - Google News 分享链（302+JS 二跳）直接判 redirect_only，不浪费请求。

缓存：state/article_cache/<sha1(url)>.json（.gitignore，可再生的临时产物）。
"""
from __future__ import annotations

import hashlib
import html as _html
import ipaddress
import json
import re
import socket
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

MAX_BODY_BYTES = 5 * 1024 * 1024          # 与 collector._MAX_BODY_BYTES 同规
UA = "chip-daily-report article-fetcher contact@example.com"
REDIRECT_LIMIT = 4

# collector 静态白名单 ∪ 发现层动态白名单（复用同一防线，不另立口径）
try:
    from collector import _ALLOWED_HOSTS as _STATIC_HOSTS, _dynamic_hosts
except Exception:  # pragma: no cover - 仅直跑脚本时可能触发
    _STATIC_HOSTS, _dynamic_hosts = set(), (lambda path=None: set())

_REGISTRY_PATH = ROOT / "rules" / "rule_registry.yaml"


def _registry_domains(path=None) -> set:
    """rule_registry.yaml 的全部分级域名（A/B/C 池），fail-soft 空集。
    递归收集任意层级 key=domain 的标量值，不假设 YAML 具体嵌套形态。"""
    out: set = set()
    try:
        import yaml
        data = yaml.safe_load(Path(path or _REGISTRY_PATH).read_text(encoding="utf-8"))
    except Exception:
        return out

    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "domain" and isinstance(v, str) and v.strip():
                    out.add(v.strip().lower())
                else:
                    _walk(v)
        elif isinstance(node, list):
            for it in node:
                _walk(it)

    _walk(data)
    return out


def is_gnews_link(url: str) -> bool:
    """Google News 分享链（302+JS 二跳，本环境无法端到端机器验证）。"""
    host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    return host == "news.google.com" or host.endswith(".news.google.com")


def _base_hosts() -> set:
    return set(_STATIC_HOSTS) | _dynamic_hosts() | _registry_domains()


def _ip_guard(host: str) -> None:
    """DNS 解析结果逐 IP 拒私网/回环/链路本地/保留/多播（与 collector 同口径）。"""
    try:
        infos = socket.getaddrinfo(host, 443)
    except OSError:
        return  # 离线环境：不在此阻塞，交给 urlopen 自然失败
    for info in infos:
        addr = str(info[4][0]).split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"域名解析到受限地址：{host} -> {addr}")


def assert_citable_url(url: str, extra_hosts=None) -> str:
    """词法校验（https + 白名单∪引用域）+ IP 校验；返回小写 host。
    安全审计可见性要求：校验逻辑显式内联在本函数（与 collector._safe_fetch_ex
    同风格），不依赖隐式全局状态。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"仅允许 https 抓取：{url}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"URL 缺少主机名：{url}")
    allowed = _base_hosts() | {h.lower() for h in (extra_hosts or set())}
    if host not in allowed:
        raise ValueError(f"域名不在可核验白名单：{host}")
    _ip_guard(host)
    return host


class _CitedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向逐跳校验：落点必须重新通过 assert_citable_url（同 collector 防线）。"""

    def __init__(self, extra_hosts):
        self._extra = extra_hosts

    def redirect_request(self, req, fp, code, msg, newurl):
        assert_citable_url(str(newurl), self._extra)
        return super().redirect_request(req, fp, code, msg, headers=None, newurl=newurl)


def _strip_html(raw: bytes) -> str:
    """HTML → 纯文本：去 script/style/noscript/注释，标签转空格，实体还原。"""
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "ignore")
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = _html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_once(url: str, extra_hosts: set, timeout: int) -> str:
    """单次抓取（重定向逐跳校验 + 5MB 上限），失败抛异常由调用方降级。"""
    assert_citable_url(url, extra_hosts)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener(_CitedRedirectHandler(extra_hosts))
    with opener.open(req, timeout=timeout) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        if ctype and not (ctype.startswith("text/") or "html" in ctype
                          or "xml" in ctype or "json" in ctype):
            raise ValueError(f"非文本内容类型：{ctype}")
        return _strip_html(r.read(MAX_BODY_BYTES))


def fetch_text(url: str, extra_hosts: set | None = None,
               timeout: int = 10) -> tuple[str, str]:
    """抓取文章正文文本；先走系统代理解析，失败后绕代理直连重试一次
    （国内站 ithome 等实测走代理被拦，与 collector Newsnow 双路经验一致）。
    返回 (text, via)；via ∈ {'proxy','direct'}。
    白名单/https 违规在发任何请求前即抛 ValueError（词法校验不进重试循环）。"""
    extra = set(extra_hosts or set())
    assert_citable_url(url, extra)  # 词法校验前置：失败直接 ValueError，零请求
    errs: list[str] = []
    for via, opener in (("proxy", None), ("direct", urllib.request.ProxyHandler({}))):
        try:
            assert_citable_url(url, extra)
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            if opener is None:
                op = urllib.request.build_opener(_CitedRedirectHandler(extra))
            else:
                op = urllib.request.build_opener(
                    opener, _CitedRedirectHandler(extra))
            with op.open(req, timeout=timeout) as r:
                ctype = (r.headers.get("Content-Type") or "").lower()
                if ctype and not (ctype.startswith("text/") or "html" in ctype
                                  or "xml" in ctype or "json" in ctype):
                    raise ValueError(f"非文本内容类型：{ctype}")
                return _strip_html(r.read(MAX_BODY_BYTES)), via
        except Exception as e:  # noqa: BLE001 —— 双路都败才算失败
            errs.append(f"{via}: {e}")
    raise RuntimeError("; ".join(errs))


# ============================================================
# 磁盘缓存（state/article_cache/，.gitignore，可再生产物）
# ============================================================
def _cache_path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"{digest}.json"


def load_cached(url: str, cache_dir: Path, max_age_hours: float = 168.0) -> dict | None:
    """命中且未过期的缓存记录；否则 None。损坏记录按未命中处理并清除。"""
    p = _cache_path(Path(cache_dir), url)
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        age_h = (time.time() - float(rec.get("fetched_at", 0))) / 3600.0
    except (TypeError, ValueError):
        return None
    if age_h > max_age_hours:
        return None
    if rec.get("url") != url:
        return None
    return rec


def store_cache(url: str, cache_dir: Path, text: str, via: str) -> None:
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    rec = {
        "url": url,
        "host": (urllib.parse.urlparse(url).hostname or "").lower(),
        "fetched_at": time.time(),
        "fetched_via": via,
        "text_len": len(text),
        "text": text,
    }
    _cache_path(d, url).write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def get_article_text(url: str, cache_dir: Path | None = None,
                     max_age_hours: float = 168.0, timeout: int = 10,
                     extra_hosts: set | None = None,
                     allow_fetch: bool = True) -> dict:
    """统一入口：缓存 → 抓取 → 结构化状态。
    返回 {url, host, status, text_len, text, error}，status ∈
      ok=新抓 / cached=缓存命中 / redirect_only=gnews 跳转链 /
      too_short=文本过短（疑似反爬/付费墙） / error=抓取失败。
    status 为 ok/cached 时 text 可用。绝不抛出（fail-soft）。"""
    url = (url or "").strip()
    empty = {"url": url, "host": "", "status": "error", "text_len": 0,
             "text": "", "error": "empty url"}
    if not url:
        return empty
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if is_gnews_link(url):
        return {"url": url, "host": host, "status": "redirect_only",
                "text_len": 0, "text": "", "error": "gnews share link"}
    cache_dir = Path(cache_dir) if cache_dir else ROOT / "state" / "article_cache"
    cached = load_cached(url, cache_dir, max_age_hours)
    if cached is not None:
        return {"url": url, "host": host, "status": "cached",
                "text_len": int(cached.get("text_len") or 0),
                "text": str(cached.get("text") or ""), "error": None}
    if not allow_fetch:
        return {"url": url, "host": host, "status": "error",
                "text_len": 0, "text": "", "error": "fetch disabled"}
    try:
        text, via = fetch_text(url, extra_hosts=extra_hosts, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "host": host, "status": "error",
                "text_len": 0, "text": "", "error": str(e)[:300]}
    if len(text) < 200:
        return {"url": url, "host": host, "status": "too_short",
                "text_len": len(text), "text": "", "error": "疑似反爬/付费墙"}
    store_cache(url, cache_dir, text, via)
    return {"url": url, "host": host, "status": "ok",
            "text_len": len(text), "text": text, "error": None}
