import pytest

from pipeline import workflows


def test_builtin_templates_present():
    assert workflows.BUILTIN["全流程"] == ["BR", "LRT", "AE", "PR"]
    assert workflows.BUILTIN["跳过BR"] == ["LRT", "AE", "PR"]
    assert workflows.BUILTIN["无PR"] == ["BR", "LRT", "AE"]
    assert workflows.BUILTIN["极简"] == ["LRT", "AE"]


def test_validate_ok():
    workflows.validate_workflow(["BR", "LRT", "AE", "PR"])
    workflows.validate_workflow(["LRT", "AE"])


def test_validate_empty_fails():
    with pytest.raises(ValueError, match="空"):
        workflows.validate_workflow([])


def test_validate_unknown_stage():
    with pytest.raises(ValueError, match="未知阶段"):
        workflows.validate_workflow(["LRT", "XX"])


def test_validate_pr_requires_ae():
    with pytest.raises(ValueError, match="PR"):
        workflows.validate_workflow(["LRT", "PR"])


def test_normalize_orders_canonically():
    assert workflows.normalize(["PR", "AE", "BR", "LRT"]) == ["BR", "LRT", "AE", "PR"]
    assert workflows.normalize(["AE", "AE", "LRT"]) == ["LRT", "AE"]


def test_build_stages_returns_stage_instances():
    stages = workflows.build_stages(["LRT", "AE"])
    assert [s.name for s in stages] == ["LRT", "AE"]


def test_store_save_and_list(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {}}')
    store = workflows.WorkflowStore(p)
    store.save("我的", ["LRT", "AE", "PR"])
    reloaded = workflows.WorkflowStore(p)
    assert reloaded.custom()["我的"] == ["LRT", "AE", "PR"]


def test_store_save_validates(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {}}')
    store = workflows.WorkflowStore(p)
    with pytest.raises(ValueError, match="PR"):
        store.save("坏的", ["LRT", "PR"])


def test_store_all_merges_builtin_and_custom(tmp_path):
    p = tmp_path / "workflows.json"
    p.write_text('{"workflows": {"我的": ["LRT", "AE"]}}')
    store = workflows.WorkflowStore(p)
    allw = store.all()
    assert "全流程" in allw and "我的" in allw
