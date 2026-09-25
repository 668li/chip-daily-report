#!/usr/bin/env python3
"""
芯片行业日报校验脚本（硬约束校验器）v5.0
用法: python validate_report.py <日报文件路径>

v3.1 修复（基于对抗审查报告）:
  - [C-1] 修复自检表格正则：\\d+ → [#\\d]+（兼容 | # | 格式）
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

v5.0 升级（微电子专业深度版）:
  - [R-1] 摘要句数标准从3-4句放宽至3-5句（6句WARN，≥7句FAIL）
  - [R-2] 新增#14 技术注解检查：涉及专业术语的新闻必须有[技术注解: xxx]标签
  - [R-3] 新增#15 产业链关联检查：必须包含## 产业链关联小节且≥2组关联
  - [R-4] 章节顺序检查更新：新增"产业链关联"环节
  - 脚本覆盖 15/15 项 Rubric（含WARN级提示）

v5.2 升级（来源分层 + 信号层，X17）:
  - [R-5] 新增#20 信号层检查（软指标）：每条新闻须标注'| 信号: 重要性/影响方向/情绪'
        格式错误 FAIL；覆盖率<80% WARN；0条新闻 PASS；旧日报无信号仅 WARN 不破坏退出码
  - 来源池优先级（Tier-0/1/2）在 SKILL.md Step2 强制，脚本侧不重复判定
  - 脚本覆盖 15/15 项 Rubric + 5 项 X 裁决软检查（16/17/18/19/20）

v5.3 升级（跨日记忆 + 催化剂日历，B/C）:
  - [R-6] 新增#21 持续追踪检查（B·软指标）：检测到'## 持续追踪'小节时验证结构
        '暂无持续追踪主题'降级 PASS；标题缺失/内容过短 WARN；不改变退出码
  - [R-7] 新增#22 前瞻催化剂检查（C·软指标）：检测到'## 前瞻催化剂'小节时验证表格
        '近期无已知催化剂'降级 PASS；缺表头 WARN；不改变退出码
  - 脚本覆盖 15/15 项 Rubric + 7 项 X 裁决软检查（16-22）

v5.4 升级（费曼解释，F1.3）:
  - [R-8] 新增#23 费曼解释检查（v5.4·软指标）：检测到'## 费曼解释'小节时验证结构
        须含'- **术语**：大白话解释'条目；缺失/过短 WARN；不改变退出码
  - 脚本覆盖 15/15 项 Rubric + 8 项 X 裁决软检查（16-23）

v5.6 升级（深度解读 + 未来借鉴）:
  - [R-9] 新增#24 深度解读检查（v5.6·软指标）：检测到'## 深度解读'小节时验证结构
        须含 ≥2 条'### 解读 N：标题'，每条含'这意味着什么'与'未来影响'；缺失 WARN；不改变退出码
  - [R-10] 新增#25 未来借鉴检查（v5.6·软指标）：检测到'## 未来借鉴'小节时验证结构
        须含 趋势信号/格局预判/可借鉴行动 类目；缺失 WARN；不改变退出码
  - 脚本覆盖 15/15 项 Rubric + 10 项 X 裁决软检查（16-25）

v5.8 升级（未来借鉴强化 + 今日导师课）:
  - [R-11] #25 未来借鉴增强：检测'格局时间轴'（1年内/1-3年/3-5年 分阶段）与趋势信号
        强度标注（↑强/→中/↓弱）；含则 PASS 注明增强，缺则仍 PASS（向后兼容旧日报）
  - [R-12] 新增#26 今日导师课检查（v5.8·软指标）：检测到'## 今日导师课'小节时验证结构
        须含 今日速览/深度第一课/必懂概念/课后思考 四模块；缺失 WARN；不改变退出码
  - 脚本覆盖 15/15 项 Rubric + 11 项 X 裁决软检查（16-26）

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

# === GEN:RULES:START ===
# 以下域名常量由 rules/rule_registry.yaml 自动生成（F1.2），DO NOT EDIT
# A级来源域名（只检查URL域名，不检查display text）
A_LEVEL_DOMAINS = [
    'tsmc.com',  # TSMC 官方
    'samsung.com',  # Samsung 官方（父域）
    'skhynix.com',  # SK hynix 官方
    'news.skhynix.com',  # SK hynix 新闻室
    'intel.com',  # Intel Newsroom
    'nvidia.com',  # NVIDIA 官方
    'nvidianews.nvidia.com',  # NVIDIA Newsroom
    'semi.org',  # SEMI
    'semi.org.cn',  # SEMI 大半导体产业网
    'techinsights.com',  # TechInsights
    'semianalysis.com',  # SemiAnalysis
    'edn.com',  # EDN
    'semiengineering.com',  # Semiconductor Engineering
    'eet-china.com',  # EET-China
    'chinanews.com.cn',  # 中国新闻网
    'cls.cn',  # 财联社
    'news.cn',  # 新华社
    'cnstock.com',  # 上海证券报
    'stcn.com',  # 证券时报
    'cninfo.com.cn',  # 巨潮资讯
    '21jingji.com',  # 21世纪经济报道
    'jiemian.com',  # 界面新闻
    'ce.cn',  # 经济日报
    'cet.com.cn',  # 中国经济网
    'xinhuanet.com',  # 新华网
    'people.com.cn',  # 人民网
    'cctvl.com',  # 央视网
    'chinadaily.com.cn',  # 中国日报
    'yicai.com',  # 第一财经
    'cena.com.cn',  # 中国电子报
    'digitimes.com',  # DigiTimes
    'digitimes.com.tw',  # 电子时报 DigiTimes
    'ieeexplore.ieee.org',  # IEEE Xplore
    'onlinelibrary.wiley.com',  # Wiley Online Library
    'isscc.org',  # ISSCC
    'vlsisymposium.org',  # VLSI Symposium
    'dac.com',  # DAC
    'ieee-iedm.org',  # IEDM
    'nature.com',  # Nature
    'asia.nikkei.com',  # Nikkei Asia
    'reuters.com',  # Reuters
    'bloomberg.com',  # Bloomberg
    'chosun.com',  # Chosun Ilbo
    'koreatimes.co.kr',  # Korea Times
]

# C级来源域名（精确匹配，禁止使用）
C_LEVEL_DOMAINS = [
    'weibo.com',  # 微博
    'weibo.cn',  # 微博（移动）
    'twitter.com',  # Twitter
    'x.com',  # X（Twitter）
    'douyin.com',  # 抖音
    'kuaishou.com',  # 快手
    'zhihu.com',  # 知乎帖文
    'xiaohongshu.com',  # 小红书
    'bilibili.com',  # B站
]

# 产业链5环节（章节标题关键词）
SEGMENTS = ['设计', '制造', '封测', 'EDA', '材料']
# === GEN:RULES:END ===

# 越界附录关键词（仅含真正违反中立性的"预测/建议"类标题；
# 客观的"市场/政策/资本"事实维度已合法化，不再禁止，见 SKILL.md 边界与反例7）
FORBIDDEN_APPENDICES = [
    '投资建议', '股价分析', '市场预测',
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
    """检查4: 摘要句数（v5.0: 目标3-5句，6句WARN，≥7句FAIL）"""
    checks = []
    for item in items:
        title = item['title'][:30]
        sent_count = count_sentences(item['summary'])
        ok = 3 <= sent_count <= 5
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
    """检查12: 章节顺序是否正确（v5.0: 新增"产业链关联"环节）"""
    expected_order = ['今日要点', '设计', '制造', '封测', 'EDA', '材料', '产业链关联', '自检结果']
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


# v5.0新增：需要技术注解的专业术语关键词
TECH_TERM_KEYWORDS = [
    # 晶体管结构
    'GAA', 'FinFET', 'TFET', 'Gate-All-Around',
    # 封装技术
    'CoWoS', 'InFO', 'MR-MUF', 'Chiplet', '2.5D', '3D IC', '3DIC',
    '先进封装', '混合键合', '热压键合',
    # 存储技术
    'HBM3E', 'HBM4', 'HBM3', 'LPDDR', 'DRAM', 'NAND',
    # 制程相关
    'EUV', 'DUV', 'SADP', 'SAQP', '极紫外',
    # 材料规格
    '6N', '电子特气', '光刻胶', '碳化硅', '氮化镓', 'SiC', 'GaN',
    # 架构技术
    'NPU', 'TPU', '存算一体', 'RISC-V',
    # 制程节点
    '2nm', '3nm', '5nm', '7nm', '14nm', '28nm',
]


def check_tech_annotations(items):
    """检查14: 技术注解（v5.0新增）——涉及专业术语的新闻必须有[技术注解: xxx]标签"""
    missing = []
    has_annotation_count = 0
    needs_annotation_count = 0

    for item in items:
        if '今日暂无' in item['title']:
            continue
        # 检查摘要+标题中是否包含专业术语
        full_text = item['title'] + ' ' + item['summary']
        has_tech_term = any(kw.lower() in full_text.lower() for kw in TECH_TERM_KEYWORDS)

        if has_tech_term:
            needs_annotation_count += 1
            has_annotation = '[技术注解' in item['summary'] or '[技术注解' in item['title']
            if has_annotation:
                has_annotation_count += 1
            else:
                missing.append(item['title'][:30])

    return {
        'needs_annotation': needs_annotation_count,
        'has_annotation': has_annotation_count,
        'missing': missing,
    }


def check_industry_chain(content):
    """检查15: 产业链关联（v5.0新增）——必须包含## 产业链关联小节且≥2组关联"""
    # 检查章节是否存在
    match = re.search(r'^##\s+产业链关联\s*$', content, re.MULTILINE)
    if not match:
        return False, "缺少'## 产业链关联'章节", 0

    # 提取章节内容
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    if next_section:
        section_content = content[section_start:section_start + next_section.start()]
    else:
        section_content = content[section_start:]

    # 统计关联组数（以 - ** 开头的条目）
    groups = re.findall(r'^-\s+\*\*', section_content, re.MULTILINE)
    group_count = len(groups)

    # 检查每组是否涉及产业链环节
    segment_keywords = ['设计', '制造', '封测', 'EDA', '材料', '设备']
    segments_mentioned = sum(1 for kw in segment_keywords if kw in section_content)

    if group_count >= 2 and segments_mentioned >= 2:
        return True, f"产业链关联{group_count}组，涉及{segments_mentioned}个环节", group_count
    elif group_count >= 2:
        return True, f"产业链关联{group_count}组（WARN: 环节覆盖不足{segments_mentioned}个）", group_count
    elif group_count == 1:
        return False, f"产业链关联仅{group_count}组（需≥2组）", group_count
    else:
        return False, "产业链关联章节为空", group_count


# ============================================================
# v5.0 增强检查（X12 / X14 / X15 / X16 裁决固化，F3）
# ============================================================

def check_news_count(actual_count):
    """检查16（X12 软指标）：单期新闻条数 15-20 为目标区间，WARN 级。
    落区间 PASS；10-14 或 21-25 WARN；<10 或 >25 FAIL；0 条（节假日）自动 PASS。
    """
    if actual_count == 0:
        return 'PASS', "0 条新闻（节假日），条数检查自动 PASS"
    if actual_count < 10:
        return 'FAIL', f"新闻条数 {actual_count} 条（<10，信息密度过低）"
    if actual_count > 25:
        return 'FAIL', f"新闻条数 {actual_count} 条（>25，疑似重复/冗余）"
    if 10 <= actual_count < 15 or 21 <= actual_count <= 25:
        return 'WARN', f"新闻条数 {actual_count} 条（偏离目标区间 15-20，建议调整）"
    return 'PASS', f"新闻条数 {actual_count} 条（落入目标区间 15-20）"


def check_source_stats_location(content):
    """检查17（X14 软指标/WARN）：来源分级统计必须位于 ## 自检结果 小节内部，
    不得作为独立一级章节。检测到独立 '## 来源分级统计' 标题则 WARN。
    """
    self_idx = content.find('## 自检结果')
    standalone = re.search(r'^##\s+来源分级统计\s*$', content, re.MULTILINE)
    if standalone and (self_idx == -1 or standalone.start() < self_idx):
        return 'WARN', "检测到独立 '## 来源分级统计' 一级章节，应移入 '## 自检结果' 小节内部（X14）"
    return 'PASS', "来源分级统计位于自检结果小节内（或未见独立章节）"


def check_section_title_fullname(content):
    """检查18（X15 软指标/WARN）：环节章节须用全称。
    '## EDA' / '## 材料' 简写废止，应为 '## EDA / 工具' / '## 材料 / 设备'。
    """
    bad = []
    if re.search(r'^##\s+EDA\s*$', content, re.MULTILINE):
        bad.append('## EDA')
    if re.search(r'^##\s+材料\s*$', content, re.MULTILINE):
        bad.append('## 材料')
    if bad:
        return 'WARN', f"环节标题使用了简写 {bad}，应统一为全称 '## EDA / 工具' / '## 材料 / 设备'（X15）"
    return 'PASS', "环节章节标题均使用全称"


def check_title_date(content):
    """检查19（X16 软指标/WARN）：一级标题须附日期，元信息须为 blockquote 半角冒号。
    """
    warns = []
    title_match = re.search(r'^#\s+芯片行业日报([^\n]*)$', content, re.MULTILINE)
    if not title_match:
        warns.append("缺少 '# 芯片行业日报' 一级标题")
    else:
        tail = title_match.group(1)
        if not re.search(r'\d{4}\s*[-—年]\s*\d{1,2}', tail):
            warns.append("一级标题未附日期（应为 '# 芯片行业日报 — 年月日'）")
    meta_ok = bool(re.search(r'^>\s*生成时间\s*:', content, re.MULTILINE))
    if not meta_ok:
        warns.append("头部元信息未使用 '> 生成时间:' 形式的 blockquote 半角冒号（X16）")
    if warns:
        return 'WARN', "；".join(warns)
    return 'PASS', "标题附日期且元信息为 blockquote 半角冒号格式"


# ============================================================
# v5.2 信号层（X17 来源池 + 信号三要素），F3 扩展
# ============================================================

# 信号标签格式：信号: 重要性/影响方向/情绪
#   重要性: 高|中|低；影响方向: 利好|利空|中性；情绪: 正面|负面|中性
SIGNAL_RE = re.compile(r"信号[:：]\s*(高|中|低)\s*/\s*(利好|利空|中性)\s*/\s*(正面|负面|中性)")


def check_signal_layer(items):
    """检查20（v5.2 信号层，软指标）：每条新闻应标注 '| 信号: 重要性/影响方向/情绪'。

    语义（与 SKILL.md v5.2 一致）：
      - 重要性（高/中/低）：影响范围大、牵动全链或龙头 → 高；局部/单点 → 低
      - 影响方向（利好/利空/中性）：对产业链/公司基本面的**事实**影响方向，不做股价预测
      - 情绪（正面/负面/中性）：市场/业内对事件的普遍解读情绪
    判定：
      - 信号格式错误（含"信号"字样但不匹配 SIGNAL_RE）→ FAIL
      - 覆盖率 < 80%（含旧日报完全无信号）→ WARN，不改变退出码
      - 0 条新闻（节假日）→ PASS
    """
    total = len([it for it in items if '今日暂无' not in it['title']])
    if total == 0:
        return 'PASS', "0 条新闻（节假日），信号层自动 PASS", 0
    has_signal = 0
    malformed = []
    missing = []
    for it in items:
        if '今日暂无' in it['title']:
            continue
        tail = it['timestamp']
        if SIGNAL_RE.search(tail):
            has_signal += 1
        elif '信号' in tail:
            malformed.append(it['title'][:25])
        else:
            missing.append(it['title'][:25])
    rate = has_signal / total * 100
    if malformed:
        return (
            'FAIL',
            f"{len(malformed)} 条新闻信号格式错误（应为 信号: 高|中|低/利好|利空|中性/正面|负面|中性）："
            + "、".join(malformed),
            rate,
        )
    if rate < 80:
        return (
            'WARN',
            f"信号覆盖率 {rate:.0f}%（{has_signal}/{total}，目标 ≥80%），"
            f"缺失 {len(missing)} 条：{'、'.join(missing[:5])}",
            rate,
        )
    return 'PASS', f"信号覆盖率 {rate:.0f}%（{has_signal}/{total}，目标 ≥80%）", rate


def check_tracking_section(content):
    """检查21（B·v5.3 跨日记忆，软指标）：检测到 '## 持续追踪' 小节时验证结构。

    小节出现时须包含 '## 持续追踪' 标题；内容为空或标题缺失 → WARN 不改变退出码。
    小节缺失（旧日报）→ WARN 提示（B 为建议覆盖）。
    0 条新闻（节假日）→ PASS。
    """
    match = re.search(r'^##\s+持续追踪\s*$', content, re.MULTILINE)
    if not match:
        return 'WARN', "未检测到 '## 持续追踪' 小节（B 跨日记忆，建议覆盖；0条新闻自动PASS）"
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_section.start()]
        if next_section
        else content[section_start:]
    )
    body = section_content.strip()
    if '暂无持续追踪主题' in body:
        return 'PASS', "持续追踪小节存在，标注'暂无持续追踪主题'（降级模式）"
    if len(body) < 10:
        return 'WARN', "持续追踪小节存在但内容过短，请核对状态文件主题"
    return 'PASS', "持续追踪小节存在且含主题对比"


def check_catalyst_section(content):
    """检查22（C·v5.3 前瞻催化剂，软指标）：检测到 '## 前瞻催化剂' 小节时验证结构。

    小节出现时须含表头 '| 日期 |' 与 '| 来源 |'；0 条标注 '近期无已知催化剂' → PASS；
    标题缺失 → WARN 不改变退出码。
    """
    match = re.search(r'^##\s+前瞻催化剂\s*$', content, re.MULTILINE)
    if not match:
        return 'WARN', "未检测到 '## 前瞻催化剂' 小节（C 催化剂日历，建议覆盖）"
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_section.start()]
        if next_section
        else content[section_start:]
    )
    if '近期无已知催化剂' in section_content:
        return 'PASS', "前瞻催化剂小节存在，标注'近期无已知催化剂'（降级模式）"
    has_header = bool(
        re.search(r'\|\s*日期\s*\|\s*事件\s*\|', section_content)
        and re.search(r'\|\s*来源\s*\|', section_content)
    )
    if not has_header:
        return 'WARN', "前瞻催化剂小节存在但缺少表格（应为 | 日期 | 事件 | 环节 | 重要度 | 来源 |）"
    return 'PASS', "前瞻催化剂小节存在且含表格"


def check_feynman_section(content):
    """检查23（v5.4 费曼解释，软指标）：检测到 '## 费曼解释' 小节时验证结构。

    小节出现时须含条目（'**' 加粗术语，非空）；缺失 → WARN 不改变退出码。
    """
    match = re.search(r'^##\s+费曼解释\s*$', content, re.MULTILINE)
    if not match:
        return 'WARN', "未检测到 '## 费曼解释' 小节（v5.4 大白话术语表，建议覆盖）"
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_section.start()]
        if next_section
        else content[section_start:]
    )
    body = section_content.strip()
    if len(body) < 10:
        return 'WARN', "费曼解释小节存在但内容过短（应含 ≥1 条'**术语**：大白话解释'条目）"
    entry_count = len(re.findall(r'^\s*-\s*\*\*', body, re.MULTILINE))
    if entry_count == 0:
        return 'WARN', "费曼解释小节存在但缺少'- **术语**：解释'格式条目"
    return 'PASS', f"费曼解释小节存在且含 {entry_count} 条术语解释"


def check_deep_dive_section(content):
    """检查24（v5.6 深度解读，软指标）：检测到 '## 深度解读' 小节时验证结构。

    小节须含 ≥2 条 '### 解读 N：标题'，每条含 '这意味着什么' 与 '未来影响'。
    缺失/结构不足 → WARN 不改变退出码。
    """
    match = re.search(r'^##\s+深度解读\s*$', content, re.MULTILINE)
    if not match:
        return 'WARN', "未检测到 '## 深度解读' 小节（v5.6 最重要新闻的意义解读，建议覆盖）"
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_section.start()]
        if next_section
        else content[section_start:]
    )
    body = section_content.strip()
    if len(body) < 20:
        return 'WARN', "深度解读小节存在但内容过短（应含 ≥2 条'### 解读 N：标题'）"
    dive_count = len(re.findall(r'^###\s+解读\s*\d+', body, re.MULTILINE))
    if dive_count < 2:
        return 'WARN', "深度解读小节应含 ≥2 条'### 解读 N：标题'（当前 %d 条）" % dive_count
    has_meaning = bool(re.search(r'这意味着什么', body))
    has_future = bool(re.search(r'未来影响', body))
    if not (has_meaning and has_future):
        return 'WARN', "深度解读条目应包含'这意味着什么'与'未来影响'两个部分"
    return 'PASS', f"深度解读小节存在且含 {dive_count} 条解读（意味着什么/未来影响/格局意义）"


def check_future_lessons_section(content):
    """检查25（v5.6 未来借鉴，软指标）：检测到 '## 未来借鉴' 小节时验证结构。

    小节须含 趋势信号 / 格局预判 / 可借鉴行动 三类内容。缺失 → WARN 不改变退出码。
    v5.8 增强（R-11）：检测'格局时间轴'（1年内/1-3年/3-5年 分阶段）与趋势信号强度标注
    （↑强/→中/↓弱）；含则 PASS 注明增强，缺则仍 PASS（向后兼容旧日报）。
    """
    match = re.search(r'^##\s+未来借鉴\s*$', content, re.MULTILINE)
    if not match:
        return 'WARN', "未检测到 '## 未来借鉴' 小节（v5.6 趋势信号/格局预判/可借鉴行动，建议覆盖）"
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_section.start()]
        if next_section
        else content[section_start:]
    )
    body = section_content.strip()
    if len(body) < 20:
        return 'WARN', "未来借鉴小节存在但内容过短（应含趋势信号/格局预判/可借鉴行动）"
    keys = {
        "趋势信号": "趋势信号" in body,
        "格局预判": "格局预判" in body,
        "可借鉴行动": "可借鉴行动" in body,
    }
    missing = [k for k, ok in keys.items() if not ok]
    if missing:
        return 'WARN', "未来借鉴小节缺少内容类目：" + "、".join(missing)
    extra = []
    if "格局时间轴" in body:
        extra.append("格局时间轴")
    if re.search(r'强度[:：]\s*[↑→↓]\s*[强中弱]', body):
        extra.append("强度标注")
    if extra:
        return 'PASS', "未来借鉴小节存在且含 趋势信号/格局预判/可借鉴行动，并带增强：" + "/".join(extra)
    return 'PASS', "未来借鉴小节存在且含 趋势信号/格局预判/可借鉴行动 类目"


def check_tutor_section(content):
    """检查26（v5.8 今日导师课，软指标）：检测到 '## 今日导师课' 小节时验证结构。

    小节须含 今日速览 / 深度第一课 / 必懂概念 / 课后思考 四模块（学生视角讲解）。
    缺失/结构不足 → WARN 不改变退出码。
    """
    match = re.search(r'^##\s+今日导师课\s*$', content, re.MULTILINE)
    if not match:
        return 'WARN', "未检测到 '## 今日导师课' 小节（v5.8 导师课堂，建议覆盖）"
    section_start = match.end()
    next_section = re.search(r'^##\s+', content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_section.start()]
        if next_section
        else content[section_start:]
    )
    body = section_content.strip()
    if len(body) < 30:
        return 'WARN', "今日导师课小节存在但内容过短（应含 今日速览/深度第一课/必懂概念/课后思考）"
    keys = {
        "今日速览": "今日速览" in body,
        "深度第一课": "深度第一课" in body,
        "必懂概念": "必懂概念" in body,
        "课后思考": "课后思考" in body,
    }
    missing = [k for k, ok in keys.items() if not ok]
    if missing:
        return 'WARN', "今日导师课小节缺少模块：" + "、".join(missing)
    return 'PASS', "今日导师课小节存在且含 今日速览/深度第一课/必懂概念/课后思考 四模块"


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
    print(f"  芯片行业日报校验报告 v5.0")
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
    print("\n【检查4】摘要规范（v5.0: 3-5句PASS，6句WARN，≥7句FAIL）")
    summary_checks = check_summary_sentences(items)
    fail_count = 0
    warn_count = 0
    for title, ok, sent_count in summary_checks:
        if sent_count >= 7:
            print(f"  ✗ FAIL  {title}... 句数={sent_count}（过长）")
            fail_count += 1
        elif sent_count == 6:
            print(f"  ⚠ WARN  {title}... 句数={sent_count}（建议压缩到3-5句）")
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
        print(f"  ✗ FAIL  章节顺序错误（应为: 今日要点 → 设计 → 制造 → 封测 → EDA → 材料 → 产业链关联 → 自检结果）")
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

    # 检查14: 技术注解（v5.0新增）
    print("\n【检查14】技术注解（v5.0: 涉及专业术语的新闻必须有[技术注解]）")
    tech_result = check_tech_annotations(items)
    if tech_result['needs_annotation'] == 0:
        print(f"  ⚠ SKIP  无涉及专业术语的新闻（可能新闻条数不足或未覆盖技术类新闻）")
    elif len(tech_result['missing']) == 0:
        print(f"  ✓ PASS  {tech_result['has_annotation']}/{tech_result['needs_annotation']}条涉及术语的新闻均含[技术注解]")
    else:
        print(f"  ✗ FAIL  {len(tech_result['missing'])}条涉及术语的新闻缺少[技术注解]:")
        for title in tech_result['missing']:
            print(f"         - {title}...")
        all_pass = False

    # 检查15: 产业链关联（v5.0新增）
    print("\n【检查15】产业链关联（v5.0: 必须包含≥2组上下游关联分析）")
    chain_ok, chain_msg, group_count = check_industry_chain(content)
    if chain_ok:
        print(f"  ✓ PASS  {chain_msg}")
    else:
        print(f"  ✗ FAIL  {chain_msg}")
        all_pass = False

    # 检查16: 新闻条数（X12 软指标）
    print("\n【检查16】新闻条数（X12 软指标，不入 Rubric 表）")
    count_status, count_msg = check_news_count(actual_count)
    if count_status == 'FAIL':
        print(f"  ✗ FAIL  {count_msg}")
        all_pass = False
    elif count_status == 'WARN':
        print(f"  ⚠ WARN  {count_msg}")
    else:
        print(f"  ✓ PASS  {count_msg}")

    # 检查17: 来源分级统计位置（X14 WARN 软指标）
    print("\n【检查17】来源分级统计位置（X14 软指标）")
    loc_status, loc_msg = check_source_stats_location(content)
    if loc_status == 'WARN':
        print(f"  ⚠ WARN  {loc_msg}")
    else:
        print(f"  ✓ PASS  {loc_msg}")

    # 检查18: 环节标题全称（X15 WARN 软指标）
    print("\n【检查18】环节章节标题全称（X15 软指标）")
    title_status, title_msg = check_section_title_fullname(content)
    if title_status == 'WARN':
        print(f"  ⚠ WARN  {title_msg}")
    else:
        print(f"  ✓ PASS  {title_msg}")

    # 检查19: 标题日期与元信息格式（X16 WARN 软指标）
    print("\n【检查19】标题日期与元信息格式（X16 软指标）")
    td_status, td_msg = check_title_date(content)
    if td_status == 'WARN':
        print(f"  ⚠ WARN  {td_msg}")
    else:
        print(f"  ✓ PASS  {td_msg}")

    # 检查20: 信号层（v5.2 X17 软指标）
    print("\n【检查20】信号层（v5.2 X17 软指标：重要性/影响方向/情绪）")
    sig_status, sig_msg, _sig_rate = check_signal_layer(items)
    if sig_status == 'FAIL':
        print(f"  ✗ FAIL  {sig_msg}")
        all_pass = False
    elif sig_status == 'WARN':
        print(f"  ⚠ WARN  {sig_msg}")
    else:
        print(f"  ✓ PASS  {sig_msg}")

    # 检查21: 持续追踪（B v5.3 软指标）
    print("\n【检查21】持续追踪（B v5.3 跨日记忆，软指标）")
    tr_status, tr_msg = check_tracking_section(content)
    if tr_status == 'WARN':
        print(f"  ⚠ WARN  {tr_msg}")
    else:
        print(f"  ✓ PASS  {tr_msg}")

    # 检查22: 前瞻催化剂（C v5.3 软指标）
    print("\n【检查22】前瞻催化剂（C v5.3 催化剂日历，软指标）")
    ct_status, ct_msg = check_catalyst_section(content)
    if ct_status == 'WARN':
        print(f"  ⚠ WARN  {ct_msg}")
    else:
        print(f"  ✓ PASS  {ct_msg}")

    # 检查23: 费曼解释（v5.4 软指标）
    print("\n【检查23】费曼解释（v5.4 大白话术语表，软指标）")
    fy_status, fy_msg = check_feynman_section(content)
    if fy_status == 'WARN':
        print(f"  ⚠ WARN  {fy_msg}")
    else:
        print(f"  ✓ PASS  {fy_msg}")

    # 检查24: 深度解读（v5.6 软指标）
    print("\n【检查24】深度解读（v5.6 最重要新闻的意义解读，软指标）")
    dd_status, dd_msg = check_deep_dive_section(content)
    if dd_status == 'WARN':
        print(f"  ⚠ WARN  {dd_msg}")
    else:
        print(f"  ✓ PASS  {dd_msg}")

    # 检查25: 未来借鉴（v5.6 软指标，v5.8 增强）
    print("\n【检查25】未来借鉴（v5.6 趋势信号/格局预判/可借鉴行动，软指标）")
    fl_status, fl_msg = check_future_lessons_section(content)
    if fl_status == 'WARN':
        print(f"  ⚠ WARN  {fl_msg}")
    else:
        print(f"  ✓ PASS  {fl_msg}")

    # 检查26: 今日导师课（v5.8 软指标）
    print("\n【检查26】今日导师课（v5.8 导师课堂：今日速览/深度第一课/必懂概念/课后思考，软指标）")
    tu_status, tu_msg = check_tutor_section(content)
    if tu_status == 'WARN':
        print(f"  ⚠ WARN  {tu_msg}")
    else:
        print(f"  ✓ PASS  {tu_msg}")

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
