"""手机推送适配器(spec 7 推送渠道:自用阶段手机推送服务)。

支持 Bark 与 Server酱³,配置选一。任何失败(未知 provider/网络/服务端错误码)
→ 返回 False,绝不抛异常(spec 8:推送失败不阻塞预测)。
"""
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
            # POST 而非 GET:正文放 body 参数,避开 GET-URL 长度上限。
            # 明日展望是最长推送(两段+四模式明细),URL 编码后 >4KB 会被
            # Bark 服务器拒掉→静默漏推(2026-07-08 排查到的漏报根因)。
            resp = client.post(f"{BARK_BASE}/{key}",
                               json={"title": title, "body": body})
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
