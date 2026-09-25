#!/usr/bin/env python3
"""
report_viz — 芯片行业日报可视化前端（可扩展装配器）。

架构（便于未来增加功能模块与借鉴复用）：
  parser.py            解析日报 md -> 结构化 dict（单一数据源）
  views/               各可视化视图，每个导出一个 render(report)->str
    report_view.py      日报卡片视图
    chain_view.py       产业链全貌（SVG 节点-连线）
    dimensions_view.py  多维透视（市场/政策/资本）
    trend_view.py       趋势图（历史走势+质量聚合+环节分布+持续追踪）
    weekly_view.py      周报对比（跨期表+走势+环节堆叠+追踪对比）
    _charts.py          SVG 折线/条形/堆叠条 共用工具
    __init__.py         VIEW_REGISTRY（扩展点）
  build_report_html.py  CLI 入口

build_report_html(report) 读取 VIEW_REGISTRY，为每个视图生成标签页 + 面板，
套入统一 HTML 模板（内联 CSS + 少量原生 JS 做标签页切换 / 节点跳转）。
新增视图 = 在 views/ 加一个文件并在 VIEW_REGISTRY 注册，装配器零改动即可生效。

产物为零依赖的单文件 HTML（内联样式与 SVG），可直接双击打开或部署。
"""
from __future__ import annotations

from pathlib import Path

from . import parser
from .views import VIEW_REGISTRY

CSS = """
:root{
  --bg:#f1f5f9; --card:#ffffff; --ink:#1e293b; --muted:#64748b;
  --line:#e2e8f0; --accent:#0f172a;
  --seg-design:#2563eb; --seg-make:#7c3aed; --seg-pack:#0891b2;
  --seg-eda:#db2777; --seg-mat:#16a34a;
}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{max-width:1080px;margin:0 auto;padding:24px 18px 56px}
header.top{background:linear-gradient(120deg,#0f172a,#1e3a8a);color:#fff;border-radius:16px;
  padding:22px 26px;box-shadow:0 8px 24px rgba(15,23,42,.18)}
header.top h1{margin:0 0 6px;font-size:23px;letter-spacing:.5px}
.meta-row{display:flex;flex-wrap:wrap;gap:10px 22px;font-size:13px;opacity:.92}
.meta-row b{font-weight:600;opacity:.8;margin-right:4px}
.tabs{display:flex;gap:8px;margin:20px 0 14px;flex-wrap:wrap}
.tab{border:1px solid var(--line);background:#fff;color:var(--muted);padding:9px 18px;
  border-radius:999px;cursor:pointer;font-size:14px;font-weight:600;transition:.15s}
.tab:hover{border-color:#94a3b8}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.panel{display:none;animation:fade .25s ease}
.panel.active{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

/* 今日要点 */
.highlights{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin-bottom:18px}
.hl-title{margin:0 0 10px;font-size:16px;color:var(--accent)}
.hl-list{margin:0;padding-left:0;list-style:none;display:grid;gap:8px}
.hl-item{position:relative;padding:10px 14px 10px 38px;background:#f8fafc;border-radius:10px;font-size:14px}
.hl-item::before{content:"★";position:absolute;left:14px;top:10px;color:#f59e0b}

/* 环节分区 */
.seg{margin-bottom:22px}
.seg-title{display:flex;align-items:center;gap:10px;font-size:18px;margin:0 0 12px;
  padding-bottom:8px;border-bottom:2px solid var(--seg)}
.seg-title .dot{width:12px;height:12px;border-radius:50%}
.seg-count{font-size:13px;color:var(--muted);font-weight:500}
.seg-stat{margin-left:auto;font-size:12px;color:var(--muted);font-weight:500}
.news-list{display:grid;gap:12px}
.news{background:#fff;border:1px solid var(--line);border-left:4px solid var(--seg);
  border-radius:12px;padding:14px 16px}
.news-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.news-title{margin:0;font-size:15.5px;line-height:1.4}
.news-summary{margin:6px 0 10px;font-size:14px;color:#334155}
.annot{background:#f8fafc;border:1px dashed #cbd5e1;border-radius:10px;padding:8px 12px;
  font-size:13px;color:#475569;display:flex;gap:6px;align-items:baseline}
.annot-ico{font-size:14px}
.annot-label{font-weight:700;color:#0f766e;white-space:nowrap}
.annot-body{flex:1}
.news-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--muted)}
.srcs{display:flex;gap:6px;flex-wrap:wrap}
.src-link{color:#1d4ed8;text-decoration:none;font-weight:600}
.src-link:hover{text-decoration:underline}
.badge{font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:999px;white-space:nowrap}
.badge-review{background:#fef3c7;color:#b45309}
.sig-group{display:inline-flex;gap:5px;flex-wrap:wrap}
.sig-badge{font-size:11px;font-weight:700;padding:1px 8px;border-radius:999px;white-space:nowrap}
.tag-origin{background:#eef2ff;color:#4338ca;padding:2px 9px;border-radius:999px;font-size:11.5px}
.ts{white-space:nowrap}

/* 自检 */
.selfcheck{background:#fff;border:1px solid var(--line);border-radius:12px;padding:6px 14px;margin-top:6px}
.selfcheck summary{cursor:pointer;font-weight:600;padding:8px 0;color:var(--accent)}
.sc-table{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 12px}
.sc-table th,.sc-table td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left}.sc-table th{color:var(--muted);font-weight:600}
.sc-pill{font-weight:700;padding:1px 9px;border-radius:999px;font-size:12px}
.sc-pass{background:#dcfce7;color:#15803d}
.sc-warn{background:#fef3c7;color:#b45309}
.sc-fail{background:#fee2e2;color:#b91c1c}
/* 持续追踪（B v5.3） */
.tracking-block{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.tk-title{font-size:16.5px;margin:0 0 10px;color:#0f766e}
.tk-sub{font-size:12.5px;color:var(--muted);font-weight:500;margin-left:8px}
.tk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.tk-card{background:#f0fdfa;border:1px solid #99f6e4;border-radius:10px;padding:10px 12px}
.tk-head{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.tk-dir{font-size:11.5px;font-weight:700;color:#0f766e;background:#ccfbf1;border-radius:999px;padding:1px 8px;white-space:nowrap}
.tk-topic{font-weight:700;font-size:14px;color:#134e4a}
.tk-detail{margin:0;font-size:13px;color:#475569;line-height:1.5}
/* 前瞻催化剂（C v5.3） */
.catalyst-block{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.ct-title{font-size:16.5px;margin:0 0 10px;color:#1d4ed8}
.ct-sub{font-size:12.5px;color:var(--muted);font-weight:500;margin-left:8px}
.ct-table{width:100%;border-collapse:collapse;font-size:13.5px}
.ct-table th,.ct-table td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left}
.ct-table th{color:var(--muted);font-weight:600}
.ct-date{font-weight:700;color:#1e293b;white-space:nowrap}
.ct-imp{font-weight:700;border:1.5px solid;border-radius:999px;padding:0 9px;font-size:12px;white-space:nowrap}
.sc-fail{background:#fee2e2;color:#b91c1c}

/* 费曼解释（F1.3 v5.4） */
.feynman-block{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.fk-title{font-size:16.5px;margin:0 0 10px;color:#6d28d9}
.fk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.fk-card{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:10px;padding:10px 12px}
.fk-term{font-weight:700;font-size:14px;color:#5b21b6;margin-bottom:4px}
.fk-text{margin:0;font-size:13px;color:#475569;line-height:1.55}

/* 深度解读（v5.6） */
.deep-block{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.dd-title{font-size:16.5px;margin:0 0 10px;color:#b91c1c}
.dd-list{display:grid;gap:12px}
.dd-card{background:#fff7f7;border:1px solid #fecaca;border-radius:10px;padding:12px 14px}
.dd-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.dd-num{width:22px;height:22px;border-radius:50%;background:#b91c1c;color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.dd-title{font-size:15px;font-weight:700;color:#7f1d1d}
.dd-part{margin-bottom:8px}
.dd-part:last-child{margin-bottom:0}
.dd-part-title{font-size:13px;font-weight:700;color:#b91c1c;margin-bottom:2px}
.dd-part-text{font-size:13.5px;color:#334155;line-height:1.7;text-align:justify}

/* 未来借鉴（v5.6） */
.future-block{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.fu-title{font-size:16.5px;margin:0 0 10px;color:#0f766e}
.fu-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.fu-card{background:#f8fafc;border:1px solid var(--line);border-top:3px solid var(--line);border-radius:10px;padding:10px 12px}
.fu-head{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.fu-ico{font-size:14px}
.fu-cat{font-weight:700;font-size:14px}
.fu-text{margin:0;font-size:13px;color:#475569;line-height:1.6}
/* 未来借鉴 v5.8 增强：强度徽章 + 格局时间轴 */
.fu-strength{display:inline-block;font-size:11px;font-weight:700;padding:0 8px;border-radius:999px;margin:0 3px;white-space:nowrap;vertical-align:1px}
.tl-track{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0;margin-top:2px}
.tl-stage{position:relative;padding:8px 10px 8px 16px;border-left:3px solid #0f766e;margin-right:8px}
.tl-stage:last-child{margin-right:0}
.tl-dot{font-size:11px;font-weight:700;color:#fff;background:#0f766e;border-radius:999px;padding:0 8px;display:inline-block;margin-bottom:3px}
.tl-period{font-size:13.5px;font-weight:800;color:#134e4a;margin-bottom:3px}
.tl-desc{margin:0;font-size:12.5px;color:#475569;line-height:1.55;text-align:justify}

/* 导师课堂（v5.8） */
.tutor-view{display:grid;gap:16px}
.tu-intro{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;font-size:13.5px;color:#475569;line-height:1.7}
.tu-intro b{color:#7c3aed}
.tu-block{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.tu-title{font-size:16.5px;margin:0 0 12px;color:#7c3aed}
.tu-sub{font-size:12.5px;color:var(--muted);font-weight:500;margin-left:8px}
.tu-board{background:linear-gradient(135deg,#312e81,#1e1b4b);color:#e0e7ff;border-radius:12px;padding:16px 18px}
.tu-board p{margin:0 0 10px;font-size:14.5px;line-height:1.85}
.tu-board p:last-child{margin-bottom:0}
.tu-board b{color:#fde68a}
.tu-board ul,.tu-board ol{margin:6px 0;padding-left:22px}
.tu-board li{margin-bottom:5px;font-size:13.5px;line-height:1.7}
.tu-lesson-card{background:#faf5ff;border:1px solid #e9d5ff;border-radius:12px;padding:14px 16px}
.tu-lead{font-size:14.5px;font-weight:700;color:#6b21a8;background:#f3e8ff;border-radius:8px;padding:8px 12px;margin-bottom:10px;line-height:1.7}
.tu-lesson-card ul,.tu-lesson-card ol{margin:4px 0 8px;padding-left:22px}
.tu-lesson-card li{margin-bottom:6px;font-size:13.5px;color:#334155;line-height:1.7}
.tu-lesson-card li b{color:#6b21a8}
.tu-concept-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.tu-concept{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:10px 12px}
.tu-concept-term{font-weight:800;font-size:13.5px;color:#166534;margin-bottom:3px}
.tu-concept-text{font-size:13px;color:#475569;line-height:1.6}
.tu-concept-text b{color:#166534}
.tu-q-list{display:grid;gap:10px}
.tu-q{display:flex;gap:10px;align-items:flex-start;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:11px 13px}
.tu-q-num{width:24px;height:24px;border-radius:50%;background:#b45309;color:#fff;font-size:13px;font-weight:800;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.tu-q-text{font-size:13.5px;color:#334155;line-height:1.7}
.tu-q-text b{color:#92400e}
.tu-empty{padding:20px;text-align:center;color:var(--muted);background:#fff;border:1px solid var(--line);border-radius:12px}

/* 产业链全貌 */
.chain-intro{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;
  font-size:14px;color:#334155;margin-bottom:14px;line-height:1.7}
.chain-intro b{color:var(--accent)}
.seg-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}
.ss-cell{border:1px solid var(--line);border-top:3px solid;border-radius:12px;background:#fff;
  padding:12px 8px;text-align:center}
.ss-name{font-size:13px;font-weight:700}
.ss-num{font-size:20px;font-weight:800;margin:4px 0 2px}
.ss-ab{font-size:11.5px;color:var(--muted)}
.chain-svg-wrap{background:linear-gradient(180deg,#fbfdff,#eef2f7);border:1px solid var(--line);
  border-radius:14px;padding:14px 10px;margin-bottom:18px}
.chain-svg{display:block;margin:0 auto}
.stage{cursor:pointer;transition:transform .15s}
.stage:hover{transform:translateY(-3px)}
.chain-detail-title{font-size:16px;margin:4px 0 12px;color:var(--accent)}
.chain-ribbons{display:grid;gap:12px;margin-left:2px}
.chain-ribbon{border:1px solid var(--line);border-radius:12px;background:#fff;padding:12px 16px;
  border-left-width:4px}
.cr-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.cr-num{width:24px;height:24px;border-radius:50%;color:#fff;font-weight:700;font-size:13px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.cr-title{font-weight:700;font-size:14.5px;color:#1e293b}
.cr-flow{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.cr-step{border:1.5px solid;border-radius:999px;padding:3px 13px;font-size:13px;font-weight:600;
  background:#f8fafc;transition:.15s}
.cr-step.hl{background:#e0e7ff}
.cr-arrow{color:#94a3b8;font-weight:700;font-size:15px}
.cr-body{margin:0;font-size:13.5px;color:#475569;line-height:1.55}
.flow{stroke-dasharray:7 5;animation:dash 1.1s linear infinite}
@keyframes dash{to{stroke-dashoffset:-24}}

/* 横向维度视图（多维透视） */
.dim-block{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:18px}
.dim-head{display:flex;align-items:center;gap:12px;padding-bottom:12px;margin-bottom:12px;
  border-bottom:2px solid var(--line)}
.dim-ico{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  font-size:19px;color:#fff;flex-shrink:0}
.dim-name{font-size:17px;font-weight:800;color:var(--ink)}
.dim-desc{font-size:12.5px;color:var(--muted);margin-top:2px}
.dim-intro{background:#f8fafc;border-left:3px solid var(--line);border-radius:8px;padding:8px 12px;
  font-size:13px;color:#475569;margin-bottom:12px;line-height:1.6}
.dim-sub{padding:12px 0;border-top:1px solid var(--line)}
.dim-sub:first-of-type{border-top:none;padding-top:0}
.ds-title{font-size:15px;font-weight:700;color:#1e293b;margin-bottom:6px}
.ds-body{font-size:13.8px;color:#334155;line-height:1.75}
.ds-srcs{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.badge-a{background:#dcfce7;color:#15803d}
.badge-b{background:#fef3c7;color:#b45309}
.dim-empty{padding:20px;text-align:center;color:var(--muted);background:#fff;border:1px solid var(--line);border-radius:12px}

/* v5.5 趋势图 + 周报对比 */
.tr-block{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:18px}
.tr-title{font-size:16.5px;margin:0 0 12px;color:var(--accent)}
.tr-sub{font-size:12.5px;color:var(--muted);font-weight:500;margin-left:8px}
.chart-card{background:#fbfdff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;overflow-x:auto}
.viz-svg{display:block;width:100%;height:auto;min-width:560px}
.chart-legend{display:flex;gap:16px;margin-top:8px;font-size:12.5px;color:var(--muted);flex-wrap:wrap}
.lg-chip{display:inline-flex;align-items:center;gap:6px}
.lg-chip i{width:12px;height:12px;border-radius:3px;display:inline-block}
.tr-note{font-size:12px;color:var(--muted);margin:8px 0 0}
.tr-dir{font-size:11.5px;font-weight:700;border:1.5px solid;border-radius:999px;padding:1px 9px;white-space:nowrap}
.tk-delta{font-size:12px;font-weight:600;color:#0f766e;margin:2px 0 4px}
.wk-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:6px}
.wk-card{background:#f8fafc;border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center}
.wk-num{font-size:22px;font-weight:800;color:var(--accent)}
.wk-label{font-size:12px;color:var(--muted);margin-top:2px}
.x12-card{margin-top:12px}
.x12-title{font-size:13px;font-weight:700;color:#475569;margin-bottom:8px}
.x12-row{display:flex;align-items:center;gap:10px;margin-bottom:6px;font-size:12.5px}
.x12-lab{width:46px;font-weight:700}
.x12-track{flex:1;background:#f1f5f9;border-radius:999px;height:12px;overflow:hidden}
.x12-fill{height:100%;border-radius:999px}
.x12-num{width:22px;text-align:right;color:var(--muted)}
.wk-table{width:100%;border-collapse:collapse;font-size:13px}
.wk-table th,.wk-table td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:middle}
.wk-table th{color:var(--muted);font-weight:600;white-space:nowrap}
.mini-bar{display:inline-block;width:74px;height:9px;background:#f1f5f9;border-radius:999px;overflow:hidden;vertical-align:middle;margin-right:6px}
.mini-fill{height:100%;background:#16a34a;border-radius:999px}
.mini-val{font-weight:700;color:#1e293b}
.cov-dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:3px;vertical-align:middle}
.wk-topic{font-weight:700;color:#1e293b}
.wk-detail{font-size:12.5px;color:#64748b;max-width:380px}

footer.foot{margin-top:30px;text-align:center;font-size:12px;color:var(--muted)}

@media(max-width:720px){
  .seg-strip{grid-template-columns:repeat(2,1fr)}
  .wrap{padding:16px 12px 40px}
}
"""

JS = """
<script>
function switchTab(id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab===id));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active', p.id==='panel-'+id));
  try{localStorage.setItem('rv_tab', id);}catch(e){}
}
document.addEventListener('DOMContentLoaded', function(){
  document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click', ()=>switchTab(t.dataset.tab)));
  // 产业链节点点击 -> 跳转到日报对应环节
  document.querySelectorAll('.stage').forEach(n=>{
    n.style.cursor='pointer';
    n.addEventListener('click', ()=>{
      const seg = n.getAttribute('data-seg');
      const el = document.getElementById('seg-'+seg);
      if(el){ switchTab('report'); el.scrollIntoView({behavior:'smooth', block:'center'});
        el.style.transition='background .4s'; el.style.background='#fffbeb';
        setTimeout(()=>el.style.background='', 900); }
    });
    // 悬停联动：高亮相关传导链步骤
    n.addEventListener('mouseenter', ()=>{
      const seg = n.getAttribute('data-seg');
      document.querySelectorAll('.cr-step').forEach(st=>
        st.classList.toggle('hl', st.getAttribute('data-seg')===seg));
    });
    n.addEventListener('mouseleave', ()=>
      document.querySelectorAll('.cr-step').forEach(st=>st.classList.remove('hl')));
  });
  try{ const last=localStorage.getItem('rv_tab'); if(last) switchTab(last); }catch(e){}
});
</script>
"""


def build_report_html(report: dict) -> str:
    """装配完整 HTML 页面：头部 + 标签页 + 各视图面板 + 脚注。"""
    tabs = "".join(
        f'<button class="tab" data-tab="{vid}">{label}</button>' for vid, label, _ in VIEW_REGISTRY
    )
    panels = "".join(
        f'<div class="panel" id="panel-{vid}">{fn(report)}</div>'
        for vid, _, fn in VIEW_REGISTRY
    )

    stats = report.get("source_stats", {})
    a_ratio = (
        f"{(stats.get('A',0)/(stats.get('A',0)+stats.get('B',0))*100):.0f}%"
        if (stats.get("A", 0) + stats.get("B", 0)) > 0
        else "—"
    )

    meta = (
        f'<div class="meta-row">'
        f'<span><b>生成时间</b>{_esc(report.get("gen_time","—"))}</span>'
        f'<span><b>覆盖范围</b>{_esc(report.get("coverage","—"))}</span>'
        f'<span><b>新闻总数</b>{report.get("news_count","—")} 条</span>'
        f'<span><b>A 级占比</b>{a_ratio}</span>'
        f"</div>"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(report.get('title','芯片行业日报'))} · 可视化</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>{_esc(report.get('title','芯片行业日报'))}</h1>
    {meta}
  </header>

  <nav class="tabs">{tabs}</nav>
  {panels}

  <footer class="foot">由 chip-daily-report · report_viz 生成 · 单文件零依赖 · 视图模块可扩展</footer>
</div>
{JS}
</body>
</html>"""


def _esc(text):
    import html

    return html.escape(str(text or ""), quote=True)


def build_from_file(md_path) -> str:
    """从日报 md 文件生成完整 HTML 字符串。"""
    return build_report_html(parser.parse_report(md_path))
