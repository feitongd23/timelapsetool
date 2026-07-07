import httpx

from skyfire.push import push


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_push_bark_posts_title_body_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["json"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"code": 200, "message": "success"})

    ok = push("晚霞 7.5 分", "北京今晚值得出动", {"provider": "bark", "key": "ABC123"},
              client=_client(handler))
    assert ok is True
    # POST 到 /{key},正文放 body 参数(无 URL 长度限制)
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.day.app/ABC123"
    assert seen["json"]["title"] == "晚霞 7.5 分"
    assert seen["json"]["body"] == "北京今晚值得出动"


def test_push_bark_long_body_not_truncated():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        seen["json"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"code": 200})

    long_body = "明日展望两段四模式明细。" * 80    # ~960 字,GET-URL 编码后会超 4KB
    ok = push("明日展望", long_body, {"provider": "bark", "key": "K"},
              client=_client(handler))
    assert ok is True
    assert seen["json"]["body"] == long_body      # 完整送达,不因长度被截/拒


def test_push_serverchan_posts_title_desp():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"code": 0, "message": "success"})

    ok = push("朝霞 3 分", "东边通道堵", {"provider": "serverchan", "key": "SCT999"},
              client=_client(handler))
    assert ok is True
    assert seen["url"] == "https://sctapi.ftqq.com/SCT999.send"
    assert "title=" in seen["body"] and "desp=" in seen["body"]


def test_push_returns_false_on_http_error_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert push("t", "b", {"provider": "bark", "key": "K"}, client=_client(handler)) is False


def test_push_returns_false_on_provider_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 400, "message": "bad key"})

    assert push("t", "b", {"provider": "bark", "key": "K"}, client=_client(handler)) is False


def test_push_unknown_provider_returns_false():
    assert push("t", "b", {"provider": "carrier_pigeon", "key": "K"}, client=None) is False
