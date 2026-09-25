#!/usr/bin/env python3
"""report_viz.views — 视图注册表（扩展点）。

新增一个可视化视图的步骤：
  1. 在 views/ 下新建一个模块，导出 render(report: dict) -> str
  2. 在此处 import 并加入 VIEW_REGISTRY
装配器（report_viz/__init__.py）会自动为其生成标签页与面板，无需改动其它代码。

视图一览：
  report     日报视图     新闻卡片 + 来源徽章 + 信号标签 + 费曼解释 + 深度解读 + 未来借鉴 + 自检
  chain      产业链全貌   价值链条形图 + 产业链关联流图
  dimensions 多维透视     市场 / 政策 / 资本 横向维度
  trend      趋势图       历史走势（条数 / A 级占比）+ 质量聚合 + 环节分布 + 持续追踪（v5.5）
  weekly     周报对比     跨期对比表 + 条数×质量走势 + 环节堆叠 + 追踪对比（v5.5）
  tutor      导师课堂     今日速览 + 深度第一课 + 必懂概念 + 课后思考（v5.8）
"""
from . import report_view, chain_view, dimensions_view, trend_view, weekly_view, tutor_view

# (view_id, 标签文字, render 函数) —— 顺序即标签页顺序
VIEW_REGISTRY = [
    ("report", "日报视图", report_view.render),
    ("chain", "产业链全貌", chain_view.render),
    ("dimensions", "多维透视", dimensions_view.render),
    ("trend", "趋势图", trend_view.render),
    ("weekly", "周报对比", weekly_view.render),
    ("tutor", "导师课堂", tutor_view.render),
]
