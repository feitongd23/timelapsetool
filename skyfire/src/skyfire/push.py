"""手机推送适配器(spec 7 推送渠道:自用阶段手机推送服务)。

支持 Bark 与 Server酱³,配置选一。任何失败(未知 provider/网络/服务端错误码)
→ 返回 False,绝不抛异常(spec 8:推送失败不阻塞预测)。
"""
from urllib.parse import quote

import httpx

BARK_BASE = "https://api.day.app"
SERVERCHAN_BASE = "https://sctapi.ftqq.com"


def push(title: str, body: str, config: dict, client: httpx.Client | None = None) -> bool:
    provider = config.get("provider")
    key = config.get("key", "")
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=15)
    try:
        if provider == "bark":
            # safe='' 连 '/' 也编码:报告正文含 "7.5/10" 等,否则 Bark 会把 '/' 当路径段
            resp = client.get(
                f"{BARK_BASE}/{key}/{quote(title, safe='')}/{quote(body, safe='')}")
            resp.raise_for_status()
            return resp.json().get("code") == 200
        if provider == "serverchan":
            resp = client.post(f"{SERVERCHAN_BASE}/{key}.send",
                               data={"title": title, "desp": body})
            resp.raise_for_status()
            return resp.json().get("code") == 0
        return False
    except Exception:
        return False
    finally:
        if owns_client:
            client.close()
