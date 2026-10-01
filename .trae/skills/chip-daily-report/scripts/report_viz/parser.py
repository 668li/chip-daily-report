#!/usr/bin/env python3
"""report_viz.parser — 把芯片行业日报 Markdown 解析为结构化 dict。

解析目标（与 SKILL.md 输出格式、validate_report.py 正则保持一致）：
  - 一级标题 / 头部元信息（生成时间 / 覆盖范围 / 新闻总数）
  - 今日要点
  - 5 环节新闻（设计 / 制造 / 封测 / EDA / 材料），含技术注解、原始出处、来源级别
  - 产业链关联（关联组）
  - 自检结果表格

来源级别判定只检查 URL 域名，与 validate_report.py / quality_dashboard.py 共用
rules/rule_registry.yaml（单一权威源），不依赖 display text。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/report_viz/ -> project root
REGISTRY = ROOT / "rules" / "rule_registry.yaml"

# 与 validate_report.py 完全一致的新闻行正则
NEWS_RE = re.compile(
    r"^-\s+\*\*(.+?)\*\*\s+[—–\-]+\s+(.+?)(?:\s*\|\s*来源[:：]\s*(.+?))?(?:\s*\|\s*(.+))?$"
)
# 容错：技术注解/原始出处可能被 markdown 行内代码反引号包裹（`[技术注解: …]`），
# 故首尾反引号可选；与 validate_report 的宽松检测口径一致。
ANNOT_RE = re.compile(r"`?\[技术注解:\s*(.+?)\]`?")
ORIGIN_RE = re.compile(r"`?（原始[:：]\s*(.+?)）`?")
SOURCE_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
SUBHEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
SELFCHECK_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(PASS|FAIL|WARN)\s*\|\s*([^|]*?)\s*\|\s*$")
# v5.2 信号层：信号: 重要性/影响方向/情绪（与 validate_report.py 的 SIGNAL_RE 一致）
SIGNAL_RE = re.compile(r"信号[:：]\s*(高|中|低)\s*/\s*(利好|利空|中性)\s*/\s*(正面|负面|中性)")
# v6.0 理解优先：新闻主行下的缩进子行（🧠 背后原理 / 🎯 对你意味着什么 / 🎓💼 考研·就业）
TEACH_RE = re.compile(r"^\s{2,}-\s+(.+?)\s*$")

# 5 个标准产业链环节（顺序即产业链流向）
SEG_ORDER = ["设计", "制造", "封测", "EDA", "材料"]

# 横向维度（多维日报扩展）：市场 / 政策 / 资本
DIM_ORDER = ["市场与需求", "政策与监管", "资本与投融资"]

# v5.3 附加小节：持续追踪（B）/ 前瞻兑现回顾（v5.10 方向1）/ 前瞻催化剂（C）；
# v6.1 未来推演（推演型前瞻，取代前两者的新版承载节）；v5.4 费曼解释（F1.3）；
# v5.6 深度解读/未来借鉴；v5.8 今日导师课
EXTRA_ORDER = ["持续追踪", "前瞻兑现回顾", "前瞻催化剂", "未来推演", "费曼解释", "深度解读", "未来借鉴", "今日导师课", "读者回声"]


def _seg_of(heading: str):
    """把章节标题映射到环节 key（兼容 '## EDA / 工具' 这类全称）。"""
    for k in SEG_ORDER:
        if heading.startswith(k):
            return k
    return None


def load_domain_sets():
    a, b, c = set(), set(), set()
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            reg = yaml.safe_load(f)
        for d in reg.get("domains", {}).get("a_level", []):
            a.add(d["domain"].lower())
        for d in reg.get("domains", {}).get("b_level", []):
            b.add(d["domain"].lower())
        for d in reg.get("domains", {}).get("c_level", []):
            c.add(d["domain"].lower())
    except Exception:
        pass
    return a, b, c


A_SET, B_SET, C_SET = load_domain_sets()


def _classify(domain: str) -> str:
    d = domain.lower().lstrip("www.")
    if any(d == p or d.endswith("." + p) for p in A_SET):
        return "A"
    if any(d == p or d.endswith("." + p) for p in C_SET):
        return "C"
    return "B"  # 默认 B 级（聚合源）


def _extract_list(buf):
    # v6.0：缩进子行（如今日要点的「为什么值得你花时间」）不收为独立要点——
    # strip 后会被误判成顶格条目、往返时膨胀成多条；IR 侧暂不承载，需 HTML 化时再扩槽。
    items = []
    for ln in buf:
        if ln[:1] in (" ", "\t"):
            continue
        s = ln.strip()
        if s.startswith("- "):
            items.append(s[2:].strip())
    return items


def _parse_sources(source_part: str):
    """返回 [(name, url), ...] 与统一级别（A > C > B）。"""
    if not source_part:
        return [], "B"
    links = SOURCE_LINK_RE.findall(source_part)
    levels = [_classify(urlparse_netloc(u)) for _, u in links]
    if not levels:
        return links, "B"
    if "A" in levels:
        unified = "A"
    elif "C" in levels:
        unified = "C"
    else:
        unified = "B"
    return links, unified


def urlparse_netloc(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc.lower().lstrip("www.")


# v6.0 理解优先：teach 三槽按首 emoji 分类；槽值存子行原文（含 emoji 与标签），
# 解析/渲染互逆；同槽首现为准，不重复收录。
_TEACH_SLOT_BY_EMOJI = {"🧠": "principle", "🎯": "impact", "🎓": "career", "💼": "career"}


def _attach_teach(item, text):
    for emoji, slot in _TEACH_SLOT_BY_EMOJI.items():
        if text.startswith(emoji):
            if not item["teach"][slot]:
                item["teach"][slot] = text
            return


def _parse_news(buf):
    items = []
    for ln in buf:
        m = NEWS_RE.match(ln)
        if not m:
            # v6.0：主行后的缩进子行归入上一条新闻的 teach 三槽（不计条目）
            if items:
                tm = TEACH_RE.match(ln)
                if tm:
                    _attach_teach(items[-1], tm.group(1).strip())
            continue
        title = m.group(1).strip()
        summary = m.group(2).strip()
        is_review = title.startswith("[回顾]")
        clean_title = title
        if is_review:
            clean_title = title[len("[回顾]"):].strip()

        annotation = None
        am = ANNOT_RE.search(summary)
        if am:
            annotation = am.group(1).strip()
            summary = ANNOT_RE.sub("", summary).strip()

        origin = None
        om = ORIGIN_RE.search(summary)
        if om:
            origin = om.group(1).strip()
            summary = ORIGIN_RE.sub("", summary).strip()

        sources, level = _parse_sources(m.group(3))

        # v5.2 信号层：从行尾拆出 信号: 重要性/影响方向/情绪 与时间戳
        tail = (m.group(4) or "").strip()
        signal = None
        sm = SIGNAL_RE.search(tail)
        if sm:
            signal = {
                "importance": sm.group(1),
                "impact": sm.group(2),
                "sentiment": sm.group(3),
            }
            tail = (tail[: sm.start()] + tail[sm.end() :]).strip(" |").strip()
        timestamp = tail.strip()

        items.append(
            {
                "title": clean_title,
                "is_review": is_review,
                "summary": summary,
                "annotation": annotation,
                "origin": origin,
                "sources": sources,
                "level": level,
                "timestamp": timestamp,
                "signal": signal,
                "teach": {"principle": None, "impact": None, "career": None},
            }
        )
    return items


def _parse_chain(buf):
    groups = []
    for ln in buf:
        # 兼容两种写法：
        #   - **关联组1：标题**。正文
        #   - **关联组1：标题**：正文
        m = re.match(r"^-\s+\*\*(.+?)\*\*\s*[：:.]?\s*(.+)$", ln)
        if m:
            groups.append({"title": m.group(1).strip(), "body": m.group(2).strip()})
    return groups


def _parse_dim_section(buf):
    """解析一个横向维度小节（## 市场与需求 等），返回 {intro, subs}。

    subs 为 ### 子标题列表，每项为 {title, body, sources:[{name,url,level}], level}。
    内联来源链接 [名称](url) 与日报 5 环节一致，用域名判定 A/B/C。
    """
    intro_lines = []
    subs = []
    cur_sub = None
    for ln in buf:
        sm = SUBHEADING_RE.match(ln)
        if sm:
            if cur_sub is not None:
                subs.append(cur_sub)
            cur_sub = {"title": sm.group(1).strip(), "body": []}
        elif cur_sub is not None:
            cur_sub["body"].append(ln)
        else:
            intro_lines.append(ln)
    if cur_sub is not None:
        subs.append(cur_sub)

    intro = "\n".join(intro_lines).strip()
    intro = re.sub(r"(?m)^\s*>+\s?", "", intro).strip()  # 去 blockquote 的 >

    out_subs = []
    for s in subs:
        body_text = "\n".join(s["body"]).strip()
        links = SOURCE_LINK_RE.findall(body_text)
        srcs = [
            {"name": n, "url": u, "level": _classify(urlparse_netloc(u))}
            for n, u in links
        ]
        levels = [x["level"] for x in srcs]
        level = "C" if "C" in levels else ("A" if "A" in levels else "B")
        out_subs.append(
            {"title": s["title"], "body": body_text, "sources": srcs, "level": level}
        )
    return {"intro": intro, "subs": out_subs}


def _split_md_row(line):
    """把一行 markdown 表格行切成单元格列表（去掉首尾竖线与空白）。"""
    s = line.strip()
    if not s.startswith("|"):
        return []
    cells = [c.strip() for c in s.strip("|").split("|")]
    return cells


def _is_sep_row(cells):
    """判断是否为表格分隔行 |---|---|。"""
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells)


def _parse_tracking(buf):
    """解析 '## 持续追踪' 小节。

    v8.1 表格化：`| 主题 | 方向 | 变化（Δ） | 连续 | 当日进展 |`，变化列独立成列
    （此前变化被压在单行散文里，读者扫不出"哪条在加速/哪条在熄火"）。
    v6.0 及更早的 `- **主题**：方向（连续N期）Δ 变比 — …` 项目符号形态继续兼容。
    """
    items = []
    header = None
    for ln in buf:
        cells = _split_md_row(ln)
        if not cells:
            header = None
            continue
        if _is_sep_row(cells):
            continue
        if header is None:
            # 第一行非分隔的表格行=表头；若不是表头就退回项目符号形态
            if any("主题" in c for c in cells):
                header = cells
            continue
        if len(cells) < len(header):
            continue

        def cell(key, default=""):
            for i, h in enumerate(header):
                if key in h and i < len(cells):
                    return cells[i]
            return default

        items.append(
            {
                "topic": cell("主题"),
                "direction": cell("方向"),
                "delta": cell("变化"),
                "streak": cell("连续"),
                "progress": cell("进展"),
                "detail": " ｜ ".join(
                    x for x in (cell("方向"), cell("变化"), cell("连续"), cell("进展")) if x
                ),
            }
        )
    if items:
        return items

    for ln in buf:
        m = re.match(r"^-\s+\*\*(.+?)\*\*\s*[:：]\s*(.+)$", ln.strip())
        if m:
            items.append({"topic": m.group(1).strip(), "detail": m.group(2).strip()})
    return items


def _parse_feynman(buf):
    """解析 '## 费曼解释' 小节（F1.3·v5.4）：提取 '- **术语**：大白话解释' 列表。"""
    items = []
    for ln in buf:
        m = re.match(r"^-\s+\*\*(.+?)\*\*\s*[:：]\s*(.+)$", ln.strip())
        if m:
            items.append({"term": m.group(1).strip(), "text": m.group(2).strip()})
    return items


def _parse_deep_dive(buf):
    """解析 '## 深度解读' 小节（v5.6）：提取 '### 解读 N：标题' 及其下各部分。

    每条解读的正文用 '- **关键词**：内容' 形式，提取为 {title, parts:[(key, text)]}。
    """
    items = []
    cur = None
    for ln in buf:
        hm = re.match(r"^###\s+解读\s*\d*\s*[：:.]?\s*(.*)$", ln.strip())
        if hm:
            if cur is not None:
                items.append(cur)
            cur = {"title": hm.group(1).strip() or "解读", "parts": []}
            continue
        pm = re.match(r"^-\s*\*\*(.+?)\*\*\s*[：:]\s*(.+)$", ln.strip())
        if cur is not None and pm:
            cur["parts"].append((pm.group(1).strip(), pm.group(2).strip()))
    if cur is not None:
        items.append(cur)
    return items


def _parse_future_lessons(buf):
    """解析 '## 未来借鉴' 小节（v5.6）：提取 '- **类目**：...' 列表。

    类目为 趋势信号/格局预判/可借鉴行动/风险提示 等，值为后续内容（可含编号子项）。
    """
    items = []
    cur_key = None
    cur_text = []
    for ln in buf:
        m = re.match(r"^-\s*\*\*(.+?)\*\*\s*[:：]\s*(.*)$", ln.strip())
        if m:
            if cur_key:
                items.append({"category": cur_key, "text": " ".join(cur_text).strip()})
            cur_key = m.group(1).strip()
            cur_text = [m.group(2).strip()] if m.group(2).strip() else []
            continue
        if cur_key and ln.strip():
            cur_text.append(ln.strip())
    if cur_key:
        items.append({"category": cur_key, "text": " ".join(cur_text).strip()})
    return items


def _parse_tutor(buf):
    """解析 '## 今日导师课' 小节（v5.8）：提取 ### 子模块及其正文。

    四模块：今日速览 / 深度第一课 / 必懂概念 / 课后思考。
    返回 [{module, body}]，body 为模块下的全部原始行（含子列表）。
    """
    items = []
    cur = None
    for ln in buf:
        sm = SUBHEADING_RE.match(ln)
        if sm:
            if cur is not None:
                items.append(cur)
            cur = {"module": sm.group(1).strip(), "body": []}
            continue
        if cur is not None:
            cur["body"].append(ln)
    if cur is not None:
        items.append(cur)
    # 去首尾空行
    for it in items:
        it["body"] = [l for l in it["body"] if l.strip()]
    return items


def _parse_catalyst(buf):
    """解析 '## 前瞻催化剂' 小节（C·v5.3 / v5.11）：提取表格行。

    v5.11 起速览表为 6 列：日期|事件|环节|重要度|确定性|来源。
    旧 5 列（无确定性）向后兼容：certainty=None，来源取第 5 列。
    同时修正旧版 6 列时把『确定性』误当来源的 bug。
    """
    rows = []
    for ln in buf:
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("日期", "") or set(cells[0]) <= {"-", ":"}:
            continue
        if len(cells) >= 6:
            certainty = cells[4]
            src_cell = cells[5]
        else:
            certainty = None
            src_cell = cells[4]
        links = SOURCE_LINK_RE.findall(src_cell)
        srcs = [
            {"name": n, "url": u, "level": _classify(urlparse_netloc(u))}
            for n, u in links
        ]
        rows.append(
            {
                "date": cells[0],
                "event": cells[1],
                "segment": cells[2],
                "importance": cells[3],
                "certainty": certainty,
                "sources": srcs,
            }
        )
    return rows


def _parse_reader_voice(buf):
    """解析 '## 读者回声' 小节（v8.1 固定节：读者环的正文出口）。

    结构：首行 blockquote=收集口径说明；'「…」' 行=读者原话（逐字引用不加工）；
    '—— 记录于 …' 行=该条原话的期号/时间；'- **[期号]**：…' 行=本期回声台账
    （已改/未改）。无原话时 quotes 为空、台账仍写"本期无新反馈"——整节不省略。
    """
    intro = ""
    quotes = []
    ledger = []
    for ln in buf:
        s = ln.strip()
        if s.startswith(">"):
            body = s.lstrip("> ").strip()
            if not body:
                continue
            if body.startswith("「") or body.startswith("」"):
                quotes.append({"text": body.strip("「」").strip(), "meta": ""})
            elif body.startswith("——") and quotes:
                quotes[-1]["meta"] = body.strip("—— ").strip()
            elif not intro:
                intro = body
            continue
        m = re.match(r"^-\s*\*\*(.+?)\*\*\s*[：:]\s*(.+)$", s)
        if m:
            ledger.append({"issue": m.group(1).strip(), "text": m.group(2).strip()})
    return {"intro": intro, "quotes": quotes, "ledger": ledger}


def _parse_catalyst_notes(buf):
    """解析 '## 前瞻催化剂'（v5.11）/'## 未来推演'（v6.1）下的 '### 前瞻/推演 N：标题' 解读块。

    每条解读含 '- **这意味着什么（看点）**' / '- **到时候盯什么（关注信号）**' /
    '- **可能影响什么（潜在影响）**' 三部分，提取为 {title, parts:[(key, text)]}。
    """
    items = []
    cur = None
    for ln in buf:
        hm = re.match(r"^###\s+(?:前瞻|推演)\s*\d*\s*[：:.]?\s*(.*)$", ln.strip())
        if hm:
            if cur is not None:
                items.append(cur)
            cur = {"title": hm.group(1).strip() or "前瞻", "parts": []}
            continue
        pm = re.match(r"^-\s*\*\*(.+?)\*\*\s*[：:]\s*(.+)$", ln.strip())
        if cur is not None and pm:
            cur["parts"].append((pm.group(1).strip(), pm.group(2).strip()))
    if cur is not None:
        items.append(cur)
    return items


def _parse_future(buf):
    """解析 '## 未来推演' 小节（v6.1 推演型前瞻）三分区。

    '### 推演 N' → catalyst_notes（复用解读块结构，剧本/窗口为 parts）；
    '### 确定时点' 表格行 → catalysts（复用 _parse_catalyst）；
    '### 兑现回顾' → forward_review（复用 _parse_forward_review 子块解析）。
    分区前的引言 blockquote 存 future_intro；未知行保留在 forward_review['extra']，
    往返零丢失。
    """
    intro_lines = []
    proj_buf = []
    cal_buf = []
    rev_buf = []
    sub = None  # None=引言区 / "proj" / "cal" / "rev" / "other"
    for ln in buf:
        hm = re.match(r"^###\s+(.*)$", ln.strip())
        if hm:
            head = hm.group(1)
            if head.startswith("推演"):
                sub = "proj"
                proj_buf.append(ln)
            elif head.startswith("确定时点"):
                sub = "cal"
                cal_buf.append(ln)
            elif head.startswith("兑现回顾"):
                sub = "rev"
                rev_buf.append(ln)
            else:
                sub = "other"
                rev_buf.append(ln)
            continue
        if sub == "proj":
            proj_buf.append(ln)
        elif sub == "cal":
            cal_buf.append(ln)
        elif sub == "rev" or sub == "other":
            rev_buf.append(ln)
        else:
            if ln.strip():
                intro_lines.append(ln)
    return {
        "future_intro": "\n".join(intro_lines).strip(),
        "catalyst_notes": _parse_catalyst_notes(proj_buf),
        "catalysts": _parse_catalyst(cal_buf),
        "forward_review": _parse_forward_review(rev_buf),
    }


def _parse_forward_review(buf):
    """解析 '## 前瞻兑现回顾' 小节（v5.10 方向1·预告→验证闭环）。

    提取：开头 blockquote 说明（intro）、'### 回看 N：标题' 条目（含
    '- **发生了没**' / '- **和我们当时判断是否一致**' 两部分）、结尾 '**闭环小结**'（v6.0 起兼容人话版标签'**预判成绩单**'）。
    返回 {intro, items:[{title, parts:[(key,text)]}], summary}。
    """
    intro_lines = []
    items = []
    summary = ""
    summary_label = ""  # v6.0：闭环小结人话版改名「预判成绩单」，标签原文随写回保留
    extra = []  # v6.0：未识别的非空行原样保留（如「预判成绩单」块/表格/结论行），往返零丢失
    scoreboard = []  # v8.1：四态计分板 [{state,count,latest,next}]，把欠账从散文里提出来独立成表
    sb_header = None
    cur = None
    for ln in buf:
        s = ln.strip()
        if s.startswith(">"):
            intro_lines.append(s.lstrip("> ").strip())
            continue
        cells = _split_md_row(ln)
        if cells:
            if _is_sep_row(cells):
                continue
            if sb_header is None:
                # 表头含「状态」+「累计」→ 四态计分板；其余表格照旧进 extra
                if any("状态" in c for c in cells) and any("累计" in c for c in cells):
                    sb_header = cells
                    continue
                extra.append(s)
                continue
            if len(cells) >= len(sb_header):
                scoreboard.append(
                    {
                        "state": cells[0],
                        "count": cells[1] if len(cells) > 1 else "",
                        "latest": cells[2] if len(cells) > 2 else "",
                        "next": cells[3] if len(cells) > 3 else "",
                    }
                )
            continue
        sb_header = None
        hm = re.match(r"^###\s+回看\s*\d*\s*[：:.]?\s*(.*)$", ln.strip())
        if hm:
            if cur is not None:
                items.append(cur)
            cur = {"title": hm.group(1).strip() or "回看", "parts": []}
            continue
        sm = re.match(r"^\*\*\s*(闭环小结|预判成绩单)\s*\*\*\s*[：:]?\s*(.*)$", ln.strip())
        if sm:
            summary_label = sm.group(1).strip()
            summary = sm.group(2).strip()
            continue
        pm = re.match(r"^-\s*\*\*(.+?)\*\*\s*[：:]\s*(.+)$", ln.strip())
        if cur is not None and pm:
            cur["parts"].append((pm.group(1).strip(), pm.group(2).strip()))
        elif ln.strip():
            extra.append(ln.strip())
    if cur is not None:
        items.append(cur)
    return {
        "intro": "\n".join(intro_lines).strip(),
        "items": items,
        "scoreboard": scoreboard,
        "summary_label": summary_label or "闭环小结",
        "summary": summary,
        "extra": extra,
    }


def _parse_selfcheck(buf):
    rows = []
    for ln in buf:
        m = SELFCHECK_ROW_RE.match(ln)
        if m:
            rows.append(
                {
                    "num": int(m.group(1)),
                    "name": m.group(2).strip(),
                    "result": m.group(3),
                    "note": m.group(4).strip(),
                }
            )
    return rows


def parse_report(path) -> dict:
    """解析一份日报 md，返回结构化 dict。"""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    report = {
        "title": "",
        "gen_time": "",
        "coverage": "",
        "news_count": None,
        "highlights": [],
        "segments": {},
        "chain_groups": [],
        "selfcheck": [],
        "dimensions": {},
        "tracking": [],
        "catalysts": [],
        "feynman": [],
        "deep_dive": [],
        "future_lessons": [],
        "tutor": [],
        "forward_review": None,  # v5.10 方向1：预告→验证闭环
        "catalyst_notes": [],  # v5.11：高/中重要度催化剂前瞻解读块
        "future_intro": "",  # v6.1：未来推演小节引言
        "reader_voice": None,  # v8.1：读者回声（读者环的正文出口）
        "source_stats": {"A": 0, "B": 0, "C": 0},
    }

    for ln in lines:
        mt = re.match(r"^#\s+芯片行业日报\s*(.*)$", ln)
        if mt:
            report["title"] = "芯片行业日报" + mt.group(1)
            break

    for ln in lines[:15]:
        if ln.lstrip().startswith(">"):
            s = ln.lstrip("> ").strip()
            if s.startswith("生成时间"):
                report["gen_time"] = re.split(r"[:：]", s, 1)[1].strip()
            elif s.startswith("覆盖范围"):
                report["coverage"] = re.split(r"[:：]", s, 1)[1].strip()
            elif s.startswith("新闻总数"):
                mm = re.search(r"(\d+)", s)
                report["news_count"] = int(mm.group(1)) if mm else None

    cur = None
    in_selfcheck = False
    buf = []

    # 设计约束（v6.0）：首个 ## 标题之前不得有自由段落——cur=None 时 _flush 无落点，
    # buf 整体丢弃；「读前须知」必须写在「今日导师课 → 今日速览」body 内（_parse_tutor 原样捕获）。
    def _flush():
        nonlocal buf
        if cur == "今日要点":
            report["highlights"] = _extract_list(buf)
        elif cur in SEG_ORDER:
            report["segments"].setdefault(cur, []).extend(_parse_news(buf))
        elif cur == "产业链关联":
            report["chain_groups"].extend(_parse_chain(buf))
        elif cur in DIM_ORDER:
            report["dimensions"].setdefault(cur, _parse_dim_section(buf))
        elif cur == "持续追踪":
            report["tracking"].extend(_parse_tracking(buf))
        elif cur == "前瞻兑现回顾":
            report["forward_review"] = _parse_forward_review(buf)
        elif cur == "未来推演":
            report.update(_parse_future(buf))
        elif cur == "前瞻催化剂":
            report["catalysts"].extend(_parse_catalyst(buf))
            report["catalyst_notes"].extend(_parse_catalyst_notes(buf))
        elif cur == "费曼解释":
            report["feynman"].extend(_parse_feynman(buf))
        elif cur == "深度解读":
            report["deep_dive"].extend(_parse_deep_dive(buf))
        elif cur == "未来借鉴":
            report["future_lessons"].extend(_parse_future_lessons(buf))
        elif cur == "今日导师课":
            report["tutor"].extend(_parse_tutor(buf))
        elif cur == "读者回声":
            report["reader_voice"] = _parse_reader_voice(buf)
        elif in_selfcheck:
            report["selfcheck"].extend(_parse_selfcheck(buf))
        buf = []

    for ln in lines:
        hm = HEADING_RE.match(ln)
        if hm:
            _flush()
            h = hm.group(1).strip()
            seg = _seg_of(h)
            if h == "今日要点":
                cur = "今日要点"
            elif seg:
                cur = seg
            elif h == "产业链关联":
                cur = "产业链关联"
            elif h in DIM_ORDER:
                cur = h
            elif h in EXTRA_ORDER:
                cur = h
            elif h == "自检结果":
                cur = "自检结果"
                in_selfcheck = True
            else:
                cur = None
            continue
        buf.append(ln)
    _flush()

    for seg_items in report["segments"].values():
        for it in seg_items:
            report["source_stats"][it["level"]] = (
                report["source_stats"].get(it["level"], 0) + 1
            )

    return report


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        r = parse_report(sys.argv[1])
        print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
