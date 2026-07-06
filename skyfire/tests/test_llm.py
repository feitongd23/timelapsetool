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


def test_predict_pct_parses_json():
    text = ('{"probability_pct": 72, "quality_pct": 64,'
            ' "reasoning": "通道通+画布甜区", "risks": "低云带",'
            ' "confidence": "high"}')
    r = predict_pct({"rule_score": 5.0}, [], [], client=_FakeClient(text))
    assert r == {"probability_pct": 72.0, "quality_pct": 64.0,
                 "reasoning": "通道通+画布甜区", "risks": "低云带",
                 "confidence": "high"}


def test_predict_pct_rejects_out_of_range_and_failures():
    bad = '{"probability_pct": 140, "quality_pct": 50, "reasoning": "", "risks": "", "confidence": "low"}'
    assert predict_pct({}, [], [], client=_FakeClient(bad)) is None

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError
    assert predict_pct({}, [], [], client=_Boom()) is None


def test_model_tiers_exist():
    assert MODEL_FAST.startswith("claude-haiku")
    assert MODEL_DEEP.startswith("claude-sonnet")


def test_predict_pct_omits_thinking_for_haiku():
    """Haiku 4.5 不支持 adaptive thinking(实测 400),不发该参数。"""
    from types import SimpleNamespace
    captured = {}
    text = ('{"probability_pct": 50, "quality_pct": 50,'
            ' "reasoning": "r", "risks": "k", "confidence": "low"}')

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
    from skyfire.llm import _PREDICT_SYSTEM
    assert "per_model_raw" in _PREDICT_SYSTEM
