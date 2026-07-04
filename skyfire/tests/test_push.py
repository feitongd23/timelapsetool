import httpx

from skyfire.push import push


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_push_bark_hits_key_url_and_encodes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 200, "message": "success"})

    ok = push("晚霞 7.5 分", "北京今晚值得出动", {"provider": "bark", "key": "ABC123"},
              client=_client(handler))
    assert ok is True
    assert seen["url"].startswith("https://api.day.app/ABC123/")
    # 中文经 URL 编码(不出现原始汉字)
    assert "晚霞" not in seen["url"]
    assert "%" in seen["url"]


def test_push_bark_encodes_slash_in_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 200})

    ok = push("晚霞 7.5/10", "指数 7.5/10 系数 0.82", {"provider": "bark", "key": "K"},
              client=_client(handler))
    assert ok is True
    # body/title 里的 '/' 必须被编码(否则 Bark 当额外路径段):key 后只应剩两段
    assert seen["url"].split("/K/", 1)[1].count("/") == 1


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
