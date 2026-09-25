# 前瞻催化剂源注册表（C · v5.3，手工维护）

> **作用**：供生成流程 Step 2 第五层「催化剂搜索」使用。只收录**已公开公告**的确定时点
> （法说会 / 财报日 / 政策生效日 / 监管审议日 / 行业会议），**严禁预测未公告事件**。
> 每条入日报时须附来源链接（A/B 级）。

## 行业会议（固定时点，每年可复用）
| 会议 | 主办 | 常见时间 | 覆盖环节 |
|------|------|---------|---------|
| ISSCC | IEEE | 每年 2 月 | 设计 / 制造 |
| DAC | ACM/IEEE | 每年 6-7 月 | EDA |
| VLSI Symposium | IEEE | 每年 6 月 | 设计 / 制造 |
| IEDM | IEEE | 每年 12 月 | 制造 / 材料 |
| SEMICON China | SEMI | 每年 3 月 | 材料 / 设备 |
| Computex | TAITRA | 每年 6 月 | 设计 / 终端 |

## 财报季固定节奏（Tier-0 法说会 + Tier-2 8-K，X17 强制覆盖）
| 时间段 | 覆盖对象 | 来源 |
|--------|---------|------|
| 1 月中下旬 | 台积电/三星/SK海力士/美光 Q4 法说会 | IR 官网 / SEC 8-K |
| 4 月中下旬 | 台积电/三星 Q1 法说会 | IR 官网 / SEC 8-K |
| 7 月中下旬 | 台积电/三星/英特尔 Q2 法说会 | IR 官网 / SEC 8-K |
| 10 月中下旬 | 台积电/三星 Q3 法说会 | IR 官网 / SEC 8-K |

## 搜索关键词模板（Step 2 第五层直接使用）
- 法说会：`TSMC earnings call date 2026` / `earnings date semiconductor 2026` / `台积电 法说会 日期`
- 政策时点：`semiconductor export control effective date` / `CHIPS Act deadline` / `BIS rule effective`
- 监管审议：`US Congress semiconductor bill vote date` / `EU chip act review`
- 行业会议：`ISSCC 2027 dates` / `DAC 2026 conference dates` / `SEMICON China 2026`

## 生成纪律
1. 只收已公告日期，未公告一律不收（即使传闻"预计X月"）。
2. 每条催化剂入日报须附来源链接，重要度=高/中/低。
3. 时间窗口=未来 7 天；超窗自动清出，不跨期残留。
4. 0 条时在日报标注"近期无已知催化剂"，不 FAIL。
