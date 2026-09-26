#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.cleaner — 模块2：清洗与标准化。

输入：collector 的 RawItem 列表
处理：
  1. 去噪：HTML 标签剥离、重复空白、控制字符清理
  2. 日期标准化：统一为 YYYY-MM-DD（缺省补 "unknown"）
  3. 标题清洗：去首尾空格、合并空格、[回顾] 等前缀剥离
  4. 环节归一：映射到标准 5 环节（设计/制造/封测/EDA/材料）
  5. URL 规范化：去掉 utm 参数、追踪参数
  6. 去重签名：生成 canonical fingerprint（供 fusion 聚类）
输出：data/cleaned_events.json
"""
from __future__ import annotations

import html as _html
import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from collector import RawItem, load_offline

DATA_DIR = Path(__file__).resolve().parent / "data"

SEG_ALIAS = {
    "设计": "设计", "芯片设计": "设计", "design": "设计",
    "制造": "制造", "晶圆": "制造", "代工": "制造", "foundry": "制造",
    "封测": "封测", "封装": "封测", "测试": "封测", "osat": "封测",
    "EDA": "EDA", "eda": "EDA", "工具": "EDA",
    "材料": "材料", "设备": "材料", "material": "材料",
    "综合": None, "其他": None,
}
SEGMENTS = ["设计", "制造", "封测", "EDA", "材料"]

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
UTM_RE = re.compile(r"[?&](utm_[a-z]+|spm|from|scm)=[^&]*")
DATE_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")


def clean_text(s: str) -> str:
    s = _html.unescape(s or "")
    s = TAG_RE.sub(" ", s)
    s = CTRL_RE.sub("", s)
    s = SPACE_RE.sub(" ", s)
    return s.strip()


def norm_date(s: str) -> str:
    if not s:
        return "unknown"
    m = DATE_RE.search(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return "unknown"


def norm_url(s: str) -> str:
    s = (s or "").strip()
    s = UTM_RE.sub("", s)
    return s


def norm_segment(seg: str) -> str:
    if not seg:
        return "未知"
    s = seg.strip()
    for k, v in SEG_ALIAS.items():
        if k.lower() in s.lower():
            return v if v else "未知"
    return "未知"


def clean_title(t: str) -> str:
    t = clean_text(t)
    t = re.sub(r"^\[(回顾|译|独家)\]\s*", "", t)
    return t


# v8 P1-C（2026-09-26）：采集准入前移——文章级 URL 判定，口径同 validate_report
# [G-1]（https?://[^/]+/.+）：域名根/仅斜杠 = 站点首页 = 伪追溯（评审 P0-1 断根）
ARTICLE_URL_RE = re.compile(r"https?://[^/]+/.+")


def is_article_url(url: str) -> bool:
    """文章级 = netloc 之后有真实路径；域名根、仅斜杠、空串都不算。"""
    return bool(ARTICLE_URL_RE.match((url or "").strip()))


def admit_article_level(cleaned: list[dict]) -> tuple[list[dict], list[dict]]:
    """采中准入：无文章级 URL 的条目不入候选池（G-1 从验后拦截前移到采中）。

    返回 (准入, 拒绝)；拒绝项原样保留，供 gate_report 披露拒绝原因。
    """
    admitted: list[dict] = []
    dropped: list[dict] = []
    for c in cleaned:
        if is_article_url(c.get("url", "")):
            admitted.append(c)
        else:
            dropped.append(c)
    return admitted, dropped


def normalize(items: list[RawItem]) -> list[dict]:
    out = []
    for it in items:
        body = clean_text(it.body)
        out.append({
            "source_id": it.source_id,
            "source_name": it.source_name,
            "tier": it.tier,
            "type": it.type,
            "segment": norm_segment(it.segment or ""),
            "title": clean_title(it.title),
            "url": norm_url(it.url),
            "published": norm_date(it.published),
            "body": body,
            "fingerprint": make_fingerprint(clean_title(it.title)),
        })
    return out


_STOP = {"the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "with", "by",
         "公司", "公布", "发布", "宣布", "拟", "约", "计划", "年", "月", "日", "第"}


def make_fingerprint(title: str) -> str:
    """事件指纹：标题去停用词 + 数字归一 → 规范化签名（用于模糊聚类）。"""
    t = title.lower()
    t = re.sub(r"\d+", "#", t)                    # 数字归一（38.4亿→#亿, 384→#）
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff#]+", " ", t)
    toks = [w for w in t.split() if w not in _STOP and len(w) > 1]
    return " ".join(sorted(set(toks)))


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


if __name__ == "__main__":
    raw = load_offline({})
    cleaned = normalize(raw)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "cleaned_events.json").write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[cleaner] 清洗标准化 {len(cleaned)} 条")
    print("[cleaner] 按环节:", dict(Counter(c["segment"] for c in cleaned)))
    print("[cleaner] 日期缺失:", sum(1 for c in cleaned if c["published"] == "unknown"))
