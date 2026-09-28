#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_discover_accounting — 发现层产出问责（v8 R4）回归。

根因背景（v7 复盘）：机制自主≠产出自主——引擎在跑、候选在进，
但非种子渠道 validated 长期为零时，必须如实宣布「机制演示」，
不许让「池子总数」掩盖「自主发现零产出」。

对抗样本：
  - 全种子 validated → demo_mode=True（哪怕池子很大）
  - 存在非种子 validated → demo_mode=False，域名点名正确
  - 非种子但还在 candidate（未转正）→ 不算产出（validated 才算）
  - discovered_via 缺失/未知渠道 → 按种子处理（宁严勿宽，不做机器豁免）
  - 空池 → demo_mode=True
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MS = ROOT / "scripts" / "multi_source"
if str(MS) not in sys.path:
    sys.path.insert(0, str(MS))

spec = importlib.util.spec_from_file_location(
    "discover", MS / "discover.py")
discover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discover)


def _state_file(tmp_path, sources):
    p = tmp_path / "disc_state.json"
    p.write_text(json.dumps(
        {"version": 1, "updated": "2026-09-28T00:00:00Z", "sources": sources},
        ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_all_seed_validated_is_demo_mode(tmp_path):
    p = _state_file(tmp_path, [
        {"domain": "a.com", "state": "active", "discovered_via": "hint"},
        {"domain": "b.com", "state": "trial", "discovered_via": "opml"},
        {"domain": "c.com", "state": "candidate", "discovered_via": "gnews"},
    ])
    acc = discover.production_accounting(p)
    assert acc["validated"] == 2 and acc["seed_validated"] == 2
    assert acc["nonseed_validated"] == 0 and acc["demo_mode"] is True


def test_nonseed_validated_counts(tmp_path):
    p = _state_file(tmp_path, [
        {"domain": "seed1.com", "state": "active", "discovered_via": "hint"},
        {"domain": "found.io", "state": "active", "discovered_via": "gnews"},
        {"domain": "hot.cn", "state": "trial", "discovered_via": "newsnow"},
        {"domain": "notyet.com", "state": "candidate", "discovered_via": "gnews"},
    ])
    acc = discover.production_accounting(p)
    assert acc["validated"] == 3
    assert acc["nonseed_validated"] == 2
    assert set(acc["nonseed_domains"]) == {"found.io", "hot.cn"}
    assert acc["demo_mode"] is False


def test_missing_via_counts_as_seed(tmp_path):
    # 宁严勿宽：渠道字段缺失 = 不能自证非种子 → 按种子计
    p = _state_file(tmp_path, [
        {"domain": "mystery.com", "state": "active"},
        {"domain": "x.com", "state": "active", "discovered_via": ""},
    ])
    acc = discover.production_accounting(p)
    assert acc["validated"] == 2 and acc["nonseed_validated"] == 0
    assert acc["demo_mode"] is True


def test_empty_pool_is_demo_mode(tmp_path):
    p = _state_file(tmp_path, [])
    acc = discover.production_accounting(p)
    assert acc["state_total"] == 0 and acc["demo_mode"] is True


def test_banner_printed_on_demo_mode(capsys, tmp_path):
    p = _state_file(tmp_path, [
        {"domain": "a.com", "state": "active", "discovered_via": "hint"}])
    discover.print_accounting(discover.production_accounting(p))
    out = capsys.readouterr().out
    assert "机制演示" in out and "validated=1" in out


def test_banner_names_domain_when_productive(capsys, tmp_path):
    p = _state_file(tmp_path, [
        {"domain": "found.io", "state": "active", "discovered_via": "gnews"}])
    discover.print_accounting(discover.production_accounting(p))
    out = capsys.readouterr().out
    assert "有产出" in out and "found.io" in out


def test_real_state_baseline():
    # 真实状态文件基线（2026-09-28）：validated=7、非种子=1（shattered.io）。
    # 只断言结构一致不断言具体数字（池子会自然演化），防止测试脆裂。
    acc = discover.production_accounting()
    assert acc["validated"] <= acc["state_total"]
    assert acc["seed_validated"] + acc["nonseed_validated"] == acc["validated"]
    assert acc["demo_mode"] == (acc["nonseed_validated"] == 0)
