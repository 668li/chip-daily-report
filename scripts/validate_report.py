#!/usr/bin/env python3
"""
芯片行业日报校验脚本（硬约束校验器）v3.2
用法: python validate_report.py <日报文件路径>

v3.1 修复（基于对抗审查报告）:
  - [C-1] 修复自检表格正则：\d+ → [#\d]+（兼容 | # | 格式）
  - [A-3] 来源级别改为只检查URL域名，不检查display text（防注入攻击）
  - [C-2] 句数统计兼容英文标点 . ! ?，排除小数点
  - [C-3] 0条新闻时跳过A级占比检查
  - [C-4] em-dash兼容多种dash变体（— – - --）
  - [C-6] C级域名改为精确匹配（防x.com误匹配fox.com）
  - [C-7] 新增今日要点数量检查（1-3条）
  - [C-8] 新增中立性检查（投资建议关键词检测）
  - [B-5] A级占比分母改为 a_count + b_count（与rubric.md一致）
  - [B-9] 新增未来日期新闻检测
  - [C-9] 文件编码fallback（utf-8 → gbk → utf-16）
  - [C-10] 路径检查（区分文件和目录）
  - [E-1] 内联投资建议检测（摘要中的股价分析）

v3.2 修复（剩余Medium/Low漏洞）:
  - [B-7] 0条新闻时今日要点自动PASS
  - [E-4] 新增免责声明+分隔线检查、章节顺序检查
  - [A-4] 新增去重检查（标题高度相似检测）
  - 脚本覆盖 13/13 项 Rubric（含WARN级提示）

退出码：
  0 = 全部通过
  1 = 存在未通过项
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# 配置区
# ============================================================

# A级来源域名（只检查URL域名，不检查display text）
A_LEVEL_DOMAINS = [
    # 国际厂商官方
    'tsmc.com', 'news.samsung.com', 'skhynix.com', 'news.skhynix.com',
    'intel.com', 'nvidia.com', 'nvidianews.nvidia.com',
    # 行业组织/权威分析
    'semi.org', 'techinsights.com', 'semianalysis.com',
    # 权威媒体
    'edn.com', 'semiengineering.com', 'eet-china.com',
    # 国内权威
    'chinanews.com.cn', 'cls.cn', 'news.cn', 'cnstock.com',
    'stcn.com', 'cninfo.com.cn', '21jingji.com', 'jiemian.com',
    # 台港权威
    'digitimes.com', 'digitimes.com.tw',
    # 学术
    'ieeexplore.ieee.org', 'onlinelibrary.wiley.com',
]

# C级来源域名（精确匹配，禁止使用）
C_LEVEL_DOMAINS = [
    'weibo.com', 'weibo.cn', 'twitter.com', 'x.com',
    'douyin.com', 'kuaishou.com', 'zhihu.com',
    'xiaohongshu.com', 'bilibili.com',
]

# 产业链5环节（章节标题关键词）
SEGMENTS = ['设计', '制造', '封测', 'EDA', '材料']

# 越界附录关键词
FORBIDDEN_APPENDICES = [
    '市场与政策动态', '市场动态', '市场分析',
    '股价分析', '财经动态', '投资建议',
]

# 投资建议关键词（用于中立性检查）
INVESTMENT_ADVICE_KEYWORDS = [
    '建议买入', '值得投资', '前景光明', '看涨', '看跌',
    '强烈推荐', '买入评级', '目标价', '预测涨', '预计下跌',
    '股价有望', '建议卖出', '增持', '减持', '建议加仓',
    '建议减仓', '投资价值', '上涨空间', '下跌空间',
]


# ============================================================
# 工具函数
# ============================================================

def read_file(filepath):
    """读取日报文件（支持多种编码）"""
    path = Path(filepath)
    if not path.exists():
        print(f"错误：文件不存在 {filepath}")
        sys.exit(1)
    if not path.is_file():
        print(f"错误：路径不是文件 {filepath}")
        sys.exit(1)
    for enc in ['utf-8', 'gbk', 'utf-16']:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    print(f"错误：无法解码文件 {filepath}（尝试了utf-8/gbk/utf-16）")
    sys.exit(1)


def domain_matches(domain, pattern):
    """检查域名是否匹配（精确或子域名匹配）"""
    domain = domain.lower().lstrip('www.')
    pattern = pattern.lower()
    return domain == pattern or domain.endswith('.' + pattern)


def extract_urls(source_str):
    """从来源字符串中提取所有URL域名"""
    if not source_str:
        return []
    # 匹配 http:// 或 https:// 后面的域名
    urls = re.findall(r'https?://([^\s/)]+)', source_str)
    return [u.lower().lstrip('www.') for u in urls]


def count_sentences(summary):
    """统计句数（兼容中英文标点，排除小数点）"""
    # 先将小数点替换为占位符（如 3.5nm → 3<DOT>5nm）
    temp = re.sub(r'(\d)\.(\d)', r'\1<DOT>\2', summary)
    # 计算中英文句末标点
    sentence_count = len(re.findall(r'[。！？.!?]', temp))
    if sentence_count == 0:
        # 无标点的情况，按长度估算
        if len(summary) > 20:
            sentence_count = 2
        else:
            sentence_count = 1
    return sentence_count


# ============================================================
# 校验函数
# ============================================================

def extract_generation_time(content):
    """提取日报生成时间"""
    match = re.search(r'生成时间[:：]\s*(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2})?', content)
    if match:
        date_str = match.group(1)
        time_str = match.group(2) or '00:00'
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            return None
    return None


def check_metadata(content):
    """检查1: 元信息完整性"""
    checks = []
    checks.append(('生成时间', bool(re.search(r'生成时间[:：]\s*\d{4}-\d{2}-\d{2}', content))))
    checks.append(('覆盖范围', bool(re.search(r'覆盖范围[:：]\s*\S', content))))
    news_count_match = re.search(r'新闻总数[:：]\s*(\d+)\s*条', content)
    checks.append(('新闻总数', news_count_match is not None))
    return checks, news_count_match


def check_segments(content):
    """检查2: 产业链完整性（5环节是否都出现）"""
    checks = []
    for seg in SEGMENTS:
        pattern = rf'^##\s+{re.escape(seg)}'
        found = bool(re.search(pattern, content, re.MULTILINE))
        checks.append((seg, found))
    return checks


def extract_news_items(content):
    """提取所有新闻条目（兼容多种dash变体）"""
    # 兼容 — (em-dash U+2014), – (en-dash U+2013), -- (双连字符), - (单连字符)
    pattern = r'^-\s+\*\*(.+?)\*\*\s+[—–\-]+\s+(.+?)(?:\s*\|\s*来源[:：]\s*(.+?))?(?:\s*\|\s*(.+))?$'
    items = []
    for match in re.finditer(pattern, content, re.MULTILINE):
        title = match.group(1).strip()
        summary = match.group(2).strip()
        source_part = match.group(3) or ''
        # 时间戳可能含空格（如 2026-07-20 16:30），取最后一个 | 后的全部内容
        timestamp = (match.group(4) or '').strip()
        items.append({
            'title': title,
            'summary': summary,
            'source': source_part,
            'timestamp': timestamp,
        })
    return items


def check_source_links(items):
    """检查3: 来源可追溯（每条新闻是否有可点击链接）"""
    checks = []
    for item in items:
        title = item['title'][:30]
        has_link = bool(re.search(r'\[.+?\]\(https?://.+?\)', item['source']))
        checks.append((title, has_link))
    return checks


def check_summary_sentences(items):
    """检查4: 摘要句数（目标3-4句，5句WARN，≥6句FAIL）"""
    checks = []
    for item in items:
        title = item['title'][:30]
        sent_count = count_sentences(item['summary'])
        ok = 3 <= sent_count <= 4
        checks.append((title, ok, sent_count))
    return checks


def check_timeliness(content, items, gen_time):
    """检查5: 时效性（超72h标注[回顾]，未来日期FAIL）"""
    checks = []
    if not gen_time:
        return checks, False
    
    skip = True
    for item in items:
        title = item['title'][:30]
        timestamp = item['timestamp']
        
        # 跳过"日期待确认"
        if '日期待确认' in timestamp or not timestamp:
            continue
        
        # 提取日期
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', timestamp)
        if not date_match:
            continue
        
        try:
            news_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            diff_hours = (gen_time - news_date).total_seconds() / 3600
            skip = False
            
            # 未来日期检测
            if diff_hours < 0:
                checks.append((title, False, f'未来日期{abs(diff_hours):.0f}h'))
                continue
            
            if diff_hours > 72:
                # 超72小时，应标注[回顾]
                has_review_tag = '[回顾]' in item['title']
                checks.append((title, has_review_tag, f'{diff_hours:.0f}h'))
            else:
                # 未超72小时，不应标注[回顾]
                has_wrong_tag = '[回顾]' in item['title']
                if has_wrong_tag:
                    checks.append((title, False, '误标[回顾]'))
        except ValueError:
            pass
    
    return checks, skip


def check_today_highlight(content, actual_news_count=0):
    """检查6: 今日要点（1-3条），0条新闻时自动PASS"""
    match = re.search(r'^##\s+今日要点\s*$', content, re.MULTILINE)
    if not match:
        return False, "缺少今日要点章节"

    # 提取今日要点章节内容
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    if next_section:
        section_content = content[section_start:section_start + next_section.start()]
    else:
        section_content = content[section_start:]

    # 统计条目数
    items = re.findall(r'^-\s+', section_content, re.MULTILINE)
    count = len(items)

    # B-7修复: 0条新闻时（节假日），今日要点可标注"无重要动态"，自动PASS
    if actual_news_count == 0:
        if count == 0 or '无' in section_content or '暂无' in section_content:
            return True, "0条新闻（节假日），今日要点自动PASS"
        return True, f"0条新闻（节假日），今日要点自动PASS"

    if count == 0:
        return False, "今日要点为空（但有新闻可选）"
    if count > 3:
        return False, f"今日要点{count}条（超过3条上限）"
    return True, f"今日要点{count}条"


def check_self_check_section(content):
    """检查7: 自检结果小节是否存在"""
    has_section = bool(re.search(r'^##\s+自检结果', content, re.MULTILINE))
    # 修复[C-1]: 兼容 | # | 和 | 1 | 两种格式
    has_table = bool(re.search(r'\|\s*[#\d]+\s*\|\s*检查项\s*\|\s*结果', content))
    return has_section, has_table


def check_forbidden_appendices(content):
    """检查8: 是否有越界附录"""
    violations = []
    for keyword in FORBIDDEN_APPENDICES:
        if re.search(rf'^##\s+.*{re.escape(keyword)}', content, re.MULTILINE):
            violations.append(keyword)
    return violations


def check_neutrality(items):
    """检查9: 中立性（不含投资建议关键词）"""
    violations = []
    for item in items:
        for kw in INVESTMENT_ADVICE_KEYWORDS:
            if kw in item['summary']:
                violations.append((item['title'][:20], kw))
    return violations


def classify_source_level(source_str):
    """判定来源级别（A/B/C）——只检查URL域名，不检查display text"""
    if not source_str:
        return 'unknown'
    
    urls = extract_urls(source_str)
    if not urls:
        return 'unknown'  # 无URL，无法判定
    
    # 先检查C级（禁止）——任何一个URL是C级则整条新闻为C级
    for domain in urls:
        for c_pattern in C_LEVEL_DOMAINS:
            if domain_matches(domain, c_pattern):
                return 'C'
    
    # 检查A级——任何一个URL是A级则整条新闻为A级
    for domain in urls:
        for a_pattern in A_LEVEL_DOMAINS:
            if domain_matches(domain, a_pattern):
                return 'A'
    
    # 默认B级（聚合源）
    return 'B'


def check_source_quality(items):
    """检查10: A级来源占比 + C级检测"""
    a_count = 0
    b_count = 0
    c_count = 0
    unknown_count = 0
    a_sources = []
    c_sources = []
    unknown_sources = []
    
    for item in items:
        level = classify_source_level(item['source'])
        if level == 'A':
            a_count += 1
            a_sources.append(item['title'][:20])
        elif level == 'B':
            b_count += 1
        elif level == 'C':
            c_count += 1
            c_sources.append(item['title'][:20])
        else:
            unknown_count += 1
            unknown_sources.append(item['title'][:20])
    
    # 修复[B-5]: 分母为 a_count + b_count（不含C级，与rubric.md一致）
    total = a_count + b_count
    a_ratio = (a_count / total * 100) if total > 0 else 0
    
    return {
        'a_count': a_count,
        'b_count': b_count,
        'c_count': c_count,
        'unknown_count': unknown_count,
        'total': total,
        'a_ratio': a_ratio,
        'a_sources': a_sources,
        'c_sources': c_sources,
        'unknown_sources': unknown_sources,
    }


def count_actual_news(items):
    """统计实际新闻条数（排除'今日暂无重要动态'）"""
    return len([item for item in items if '今日暂无' not in item['title']])


def check_disclaimer(content):
    """检查11: 免责声明是否存在（E-4修复）"""
    has_disclaimer = bool(re.search(r'chip-daily-report\s*skill\s*生成', content))
    has_separator = bool(re.search(r'^---\s*$', content, re.MULTILINE))
    return has_disclaimer, has_separator


def check_section_order(content):
    """检查12: 章节顺序是否正确（E-4修复）"""
    expected_order = ['今日要点', '设计', '制造', '封测', 'EDA', '材料', '自检结果']
    sections_found = []
    for match in re.finditer(r'^##\s+(.+?)\s*$', content, re.MULTILINE):
        title = match.group(1).strip()
        for expected in expected_order:
            if expected in title:
                sections_found.append(expected)
                break
    # 检查顺序是否非递减（允许跳过不存在的环节）
    order_indices = []
    for seg in sections_found:
        idx = expected_order.index(seg)
        order_indices.append(idx)
    is_ordered = all(order_indices[i] <= order_indices[i+1] for i in range(len(order_indices)-1))
    return is_ordered, sections_found


def check_dedup(items):
    """检查13: 去重——检测标题高度相似的重复条目（A-4修复）"""
    duplicates = []
    seen_titles = []
    for item in items:
        if '今日暂无' in item['title']:
            continue
        title_lower = item['title'].lower()
        # 检查与已见标题的相似度（简单方法：共享关键词≥4个字）
        for seen in seen_titles:
            # 提取共同子串
            common = sum(1 for c in title_lower if c in seen.lower())
            if common >= len(title_lower) * 0.7 and len(title_lower) > 5:
                duplicates.append((item['title'][:30], seen[:30]))
                break
        seen_titles.append(item['title'])
    return duplicates


# ============================================================
# 主函数
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("用法: python validate_report.py <日报文件路径>")
        print("示例: python validate_report.py 芯片行业日报_20260720.md")
        sys.exit(1)
    
    filepath = sys.argv[1]
    content = read_file(filepath)
    
    print("=" * 70)
    print(f"  芯片行业日报校验报告 v3.2")
    print(f"  文件: {filepath}")
    print("=" * 70)
    
    all_pass = True
    
    # 检查1: 元信息完整性
    print("\n【检查1】元信息完整性")
    meta_checks, news_count_match = check_metadata(content)
    for name, ok in meta_checks:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status}  {name}")
        if not ok:
            all_pass = False
    
    # 提取生成时间
    gen_time = extract_generation_time(content)
    
    # 检查2: 产业链完整性
    print("\n【检查2】产业链完整性（5环节）")
    seg_checks = check_segments(content)
    for seg, found in seg_checks:
        status = "✓ PASS" if found else "✗ FAIL"
        print(f"  {status}  {seg}")
        if not found:
            all_pass = False
    
    # 提取新闻条目
    items = extract_news_items(content)
    actual_count = count_actual_news(items)
    print(f"\n  实际新闻条数: {actual_count}")
    
    # 检查新闻总数一致性
    if news_count_match:
        declared_count = int(news_count_match.group(1))
        if declared_count != actual_count:
            print(f"  ✗ FAIL  新闻总数不一致：声明{declared_count}条，实际{actual_count}条")
            all_pass = False
        else:
            print(f"  ✓ PASS  新闻总数一致：{actual_count}条")
    
    # 检查3: 来源可追溯
    print("\n【检查3】来源可追溯")
    source_checks = check_source_links(items)
    fail_count = 0
    for title, has_link in source_checks:
        if not has_link:
            print(f"  ✗ FAIL  {title}... 缺少来源链接")
            fail_count += 1
    if fail_count == 0:
        print(f"  ✓ PASS  全部{len(source_checks)}条新闻均有来源链接")
    else:
        all_pass = False
    
    # 检查4: 摘要句数
    print("\n【检查4】摘要规范（3-4句PASS，5句WARN，≥6句FAIL）")
    summary_checks = check_summary_sentences(items)
    fail_count = 0
    warn_count = 0
    for title, ok, sent_count in summary_checks:
        if sent_count >= 6:
            print(f"  ✗ FAIL  {title}... 句数={sent_count}（过长）")
            fail_count += 1
        elif sent_count == 5:
            print(f"  ⚠ WARN  {title}... 句数={sent_count}（建议压缩到3-4句）")
            warn_count += 1
    if fail_count == 0:
        if warn_count > 0:
            print(f"  ✓ PASS  句数检查通过（{warn_count}条WARN）")
        else:
            print(f"  ✓ PASS  全部{len(summary_checks)}条摘要句数合格")
    else:
        all_pass = False
    
    # 检查5: 时效性
    print("\n【检查5】时效性（超72h标注[回顾]，未来日期FAIL）")
    time_checks, skipped = check_timeliness(content, items, gen_time)
    if skipped:
        print("  ⚠ SKIP  无可判定时间的新闻，跳过时效性检查")
    else:
        fail_count = 0
        for check in time_checks:
            if len(check) == 3:
                title, ok, info = check
                if not ok:
                    print(f"  ✗ FAIL  {title}... {info}")
                    fail_count += 1
        if fail_count == 0:
            print(f"  ✓ PASS  时效标签检查通过")
        else:
            all_pass = False
    
    # 检查6: 今日要点（新增）
    print("\n【检查6】今日要点（1-3条，0条新闻自动PASS）")
    highlight_ok, highlight_msg = check_today_highlight(content, actual_count)
    if highlight_ok:
        print(f"  ✓ PASS  {highlight_msg}")
    else:
        print(f"  ✗ FAIL  {highlight_msg}")
        all_pass = False
    
    # 检查7: 自检结果小节
    print("\n【检查7】自检结果小节")
    has_section, has_table = check_self_check_section(content)
    if has_section and has_table:
        print(f"  ✓ PASS  自检结果小节存在且包含表格")
    else:
        if not has_section:
            print(f"  ✗ FAIL  缺少'## 自检结果'小节")
        if not has_table:
            print(f"  ✗ FAIL  自检结果表格格式不匹配（应为 | # | 检查项 | 结果 |）")
        all_pass = False
    
    # 检查8: 越界附录
    print("\n【检查8】无附录越界")
    violations = check_forbidden_appendices(content)
    if not violations:
        print(f"  ✓ PASS  未发现越界附录")
    else:
        print(f"  ✗ FAIL  发现越界附录: {', '.join(violations)}")
        all_pass = False
    
    # 检查9: 中立性（新增）
    print("\n【检查9】中立性（不含投资建议）")
    neutrality_violations = check_neutrality(items)
    if not neutrality_violations:
        print(f"  ✓ PASS  未发现投资建议关键词")
    else:
        for title, kw in neutrality_violations:
            print(f"  ✗ FAIL  {title}... 含'{kw}'")
        all_pass = False
    
    # 检查10: 来源质量
    print("\n【检查10】来源质量（A级≥30%，C级=0，基于URL域名判定）")
    quality = check_source_quality(items)
    print(f"  A级: {quality['a_count']}条")
    print(f"  B级: {quality['b_count']}条")
    print(f"  C级: {quality['c_count']}条")
    if quality['unknown_count'] > 0:
        print(f"  未知(无URL): {quality['unknown_count']}条")
    
    if quality['c_count'] > 0:
        print(f"  ✗ FAIL  发现C级禁止来源: {', '.join(quality['c_sources'])}")
        all_pass = False
    
    if quality['unknown_count'] > 0:
        print(f"  ⚠ WARN  {quality['unknown_count']}条新闻无URL，无法判定级别: {', '.join(quality['unknown_sources'])}")
    
    # 修复[C-3]: 0条新闻时跳过
    if quality['total'] == 0:
        print(f"  ⚠ SKIP  无可分级来源的新闻，跳过A级占比检查")
    elif quality['a_ratio'] >= 30:
        print(f"  ✓ PASS  A级占比{quality['a_ratio']:.1f}% ≥ 30%")
    else:
        print(f"  ✗ FAIL  A级占比{quality['a_ratio']:.1f}% < 30%（需补充权威源）")
        all_pass = False

    # 检查11: 免责声明与分隔线（E-4修复）
    print("\n【检查11】免责声明与结构完整性")
    has_disclaimer, has_separator = check_disclaimer(content)
    if has_disclaimer and has_separator:
        print(f"  ✓ PASS  免责声明和分隔线均存在")
    else:
        if not has_disclaimer:
            print(f"  ✗ FAIL  缺少免责声明（应含'chip-daily-report skill 生成'）")
            all_pass = False
        if not has_separator:
            print(f"  ⚠ WARN  缺少'---'分隔线（建议在免责声明前添加）")

    # 检查12: 章节顺序（E-4修复）
    print("\n【检查12】章节顺序正确性")
    is_ordered, sections = check_section_order(content)
    if is_ordered:
        print(f"  ✓ PASS  章节顺序正确: {' → '.join(sections)}")
    else:
        print(f"  ✗ FAIL  章节顺序错误（应为: 今日要点 → 设计 → 制造 → 封测 → EDA → 材料 → 自检结果）")
        all_pass = False

    # 检查13: 去重（A-4修复）
    print("\n【检查13】去重检查（标题高度相似检测）")
    duplicates = check_dedup(items)
    if not duplicates:
        print(f"  ✓ PASS  未发现重复条目")
    else:
        for dup_title, seen_title in duplicates:
            print(f"  ⚠ WARN  疑似重复: '{dup_title}...' 与 '{seen_title}...'")
        print(f"  共{len(duplicates)}处疑似重复，请人工确认是否需要合并")
    
    # 汇总
    print("\n" + "=" * 70)
    if all_pass:
        print("  ✓ 全部检查通过")
        print("=" * 70)
        sys.exit(0)
    else:
        print("  ✗ 存在未通过项，请修正后重新校验")
        print("=" * 70)
        sys.exit(1)


if __name__ == '__main__':
    main()
