import json
from types import SimpleNamespace

from skyfire.llm import LlmResult, build_content, interpret


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
