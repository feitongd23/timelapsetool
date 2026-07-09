import json
from types import SimpleNamespace

from skyfire.llm import LlmResult, MODEL_DEEP, MODEL_FAST, build_content, explain, interpret, predict_pct


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        block = SimpleNamespace(type="text", text=self._text)
        return SimpleNamespace(content=[block], stop_reason="end_turn")


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def _today():
    return {"date": "2026-07-04", "event": "sunset_glow", "rule_score": 7.5,
            "confidence": "high",
            "payload": {"cloud_high": 50, "cloud_mid": 10, "cloud_low": 5,
                        "rh_2m": 70, "aod": 0.3, "channel": [],
                        "hour": "2026-07-04T19:00"}}


def test_interpret_parses_json_and_records_request(tmp_path):
    png = tmp_path / "f.png"
    import numpy as np
    from PIL import Image
    Image.fromarray(np.zeros((8, 8), dtype=np.uint8), mode="L").save(png)

    fake = _FakeClient(json.dumps({"llm_score": 6.5, "analysis": "通道有低云",
                                   "risks": "西侧低云可能封口"}))
    result = interpret(_today(), similar=[{"date": "2026-05-12", "actual_score": 9.0,
                                           "distance": 0.1, "payload": {}}],
                       frame_paths=[png], client=fake)
    assert isinstance(result, LlmResult)
    assert result.llm_score == 6.5 and "低云" in result.analysis
    kwargs = fake.messages.last_kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    types = [b["type"] for b in kwargs["messages"][0]["content"]]
    assert "image" in types and "text" in types


def test_interpret_returns_none_on_failure():
    class _Boom:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("no credentials")

    assert interpret(_today(), similar=[], frame_paths=[], client=_Boom()) is None


def test_interpret_returns_none_on_unparseable():
    fake = _FakeClient("今天大概能烧,大概七分吧")  # 非 JSON
    assert interpret(_today(), similar=[], frame_paths=[], client=fake) is None


def test_build_content_caps_images(tmp_path):
    import numpy as np
    from PIL import Image
    paths = []
    for i in range(5):
        p = tmp_path / f"{i}.png"
        Image.fromarray(np.zeros((8, 8), dtype=np.uint8), mode="L").save(p)
        paths.append(p)
    content = build_content(_today(), [], paths)
    assert sum(1 for b in content if b["type"] == "image") == 3  # 最多 3 帧控成本


def test_explain_returns_text():
    fake = _FakeClient("通道:通畅…")
    assert explain("卡片", [], client=fake) == "通道:通畅…"


def test_explain_swallow_failure():
    class _Boom:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError

    assert explain("卡片", [], client=_Boom()) is None


def test_build_content_includes_similar_case_note():
    today = {"date": "2026-07-05", "event": "sunset_glow", "rule_score": 5,
             "confidence": "low", "payload": {}}
    similar = [{"date": "2026-05-06", "actual_score": 10, "distance": 0.1,
                "payload": {}, "note": "西侧通道裂开是关键"}]
    content = build_content(today, similar, [])
    text = content[0]["text"]
    assert "西侧通道裂开是关键" in text


_FACTORS = ('{"卫星实况": "34%可信", "画布": "高云幕连贯", "透光通道": "通",'
            ' "气溶胶": "AOD 0.3 通透", "降水": "无", "模式分歧": "一致",'
            ' "外推可信度": "临近可信"}')


def _full_json(prob=72, qual=64):
    return (f'{{"probability_pct": {prob}, "quality_pct": {qual},'
            f' "factors": {_FACTORS}, "scenario_alt": "",'
            f' "rules_applied": ["sat-warmtop-trap"],'
            f' "reasoning": "通道通+画布甜区", "risks": "低云带",'
            f' "confidence": "high"}}')


def test_predict_pct_parses_json():
    r = predict_pct({"rule_score": 5.0}, [], [], client=_FakeClient(_full_json()))
    assert r["probability_pct"] == 72.0 and r["quality_pct"] == 64.0
    assert r["factors"]["气溶胶"] == "AOD 0.3 通透"
    assert r["rules_applied"] == ["sat-warmtop-trap"]
    assert r["confidence"] == "high"


def test_predict_pct_rejects_out_of_range_and_failures():
    bad = ('{"probability_pct": 140, "quality_pct": 50, "factors": ' + _FACTORS
           + ', "reasoning": "", "risks": "", "confidence": "low"}')
    assert predict_pct({}, [], [], client=_FakeClient(bad)) is None

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError
    assert predict_pct({}, [], [], client=_Boom()) is None


def test_predict_pct_missing_factor_gets_one_retry():
    """七因子缺项 → 一次纠正重试(llm-factor-roll:必填否则重来)。"""
    from types import SimpleNamespace
    incomplete = ('{"probability_pct": 50, "quality_pct": 50,'
                  ' "factors": {"卫星实况": "ok"},'
                  ' "reasoning": "r", "risks": "k", "confidence": "low"}')
    calls = []

    class _TwoStep:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kw):
            calls.append(kw)
            text = incomplete if len(calls) == 1 else _full_json(55, 45)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=text)])

    r = predict_pct({}, [], [], client=_TwoStep())
    assert len(calls) == 2
    # 纠正消息里点名缺的因子
    assert "气溶胶" in str(calls[1]["messages"][-1]["content"])
    assert r["probability_pct"] == 55.0


def test_predict_pct_two_incomplete_returns_none():
    incomplete = ('{"probability_pct": 50, "quality_pct": 50,'
                  ' "reasoning": "r", "risks": "k", "confidence": "low"}')
    assert predict_pct({}, [], [], client=_FakeClient(incomplete)) is None


def test_model_tiers_exist():
    assert MODEL_FAST.startswith("claude-haiku")
    assert MODEL_DEEP.startswith("claude-sonnet")


def test_predict_pct_omits_thinking_for_haiku():
    """Haiku 4.5 不支持 adaptive thinking(实测 400),不发该参数。"""
    from types import SimpleNamespace
    captured = {}
    text = _full_json(50, 50)

    class _Cap:
        def __init__(self):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=text)])

    from skyfire.llm import MODEL_DEEP, MODEL_FAST
    assert predict_pct({}, [], [], model=MODEL_FAST, client=_Cap()) is not None
    assert "thinking" not in captured
    captured.clear()
    assert predict_pct({}, [], [], model=MODEL_DEEP, client=_Cap()) is not None
    assert captured.get("thinking") == {"type": "adaptive"}


def test_predict_system_mentions_per_model_raw():
    from skyfire.llm import _predict_system
    sys_text = _predict_system()
    assert "per_model_raw" in sys_text


def test_predict_system_injects_rulebook():
    """规则表注入(2026-07-10:四类知识强制过堂,不靠 RAG 碰运气)。"""
    from skyfire.llm import _predict_system
    sys_text = _predict_system()
    for rule_id in ("sat-warm-top-full-cover-detect",
                    "cloud-high-canvas-never-zero",
                    "cloud-overcast-zero-scale",
                    "aod-missing-not-neutral",
                    "consensus-2v2-dual-scenario"):
        assert rule_id in sys_text, rule_id
    # 来源行与雾/彩虹节被剔除(省 token,出处审计留在文件)
    assert "来源:" not in sys_text
    assert "fog-" not in sys_text and "rainbow-" not in sys_text
