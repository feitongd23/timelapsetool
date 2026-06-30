# Copyright (c) 2026 杜非同. All rights reserved.
# Part of Timelapse Tool — proprietary software.
# Unauthorized copying, modification, or distribution is prohibited.

import pytest

from pipeline import workflows


def test_builtin_templates_present():
    assert workflows.BUILTIN["全流程"] == ["BR", "LRT", "AE", "导出"]
    assert workflows.BUILTIN["跳过BR"] == ["LRT", "AE", "导出"]
    assert workflows.BUILTIN["无导出"] == ["BR", "LRT", "AE"]
    assert workflows.BUILTIN["极简"] == ["LRT", "AE"]


def test_validate_ok():
    workflows.validate_workflow(["BR", "LRT", "AE", "导出"])
    workflows.validate_workflow(["LRT", "AE"])


def test_validate_empty_fails():
    with pytest.raises(ValueError, match="空"):
        workflows.validate_workflow([])


def test_validate_unknown_stage():
    with pytest.raises(ValueError, match="未知阶段"):
        workflows.validate_workflow(["LRT", "XX"])


def test_validate_export_requires_ae():
    with pytest.raises(ValueError, match="导出"):
        workflows.validate_workflow(["LRT", "导出"])


def test_normalize_orders_canonically():
    assert workflows.normalize(["导出", "AE", "BR", "LRT"]) == ["BR", "LRT", "AE", "导出"]
    assert workflows.normalize(["AE", "AE", "LRT"]) == ["LRT", "AE"]


def test_build_stages_returns_stage_instances():
    stages = workflows.build_stages(["LRT", "AE"])
    assert [s.name for s in stages] == ["LRT", "AE"]


def test_store_save_and_list(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {}}')
    store = workflows.WorkflowStore(p)
    store.save("我的", ["LRT", "AE", "导出"])
    reloaded = workflows.WorkflowStore(p)
    assert reloaded.custom()["我的"] == ["LRT", "AE", "导出"]


def test_store_save_validates(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {}}')
    store = workflows.WorkflowStore(p)
    with pytest.raises(ValueError, match="导出"):
        store.save("坏的", ["LRT", "导出"])


def test_store_all_merges_builtin_and_custom(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {"我的": ["LRT", "AE"]}}')
    store = workflows.WorkflowStore(p)
    allw = store.all()
    assert "全流程" in allw and "我的" in allw
