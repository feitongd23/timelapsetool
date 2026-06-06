from fastapi import FastAPI

app = FastAPI(title="Timelapse Tool Backend")


@app.get("/health")
def health():
    return {"status": "ok"}


from fastapi import WebSocket, WebSocketDisconnect


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        return


import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.models import PipelineConfig, PipelineState
from pipeline.runner import PipelineRunner
from pipeline.stages import default_stages
from pipeline import workflows
from pipeline import preview

_THUMB_CACHE = str(Path(tempfile.gettempdir()) / "timelapse_thumbs")

_WORKFLOWS_PATH = Path(__file__).parent / "workflows.json"
_workflow_store = workflows.WorkflowStore(_WORKFLOWS_PATH)

_progress_log = []
_runner = PipelineRunner(stages=default_stages(), emit=_progress_log.append)
_worker = None  # 后台渲染线程；非 None 且 alive 表示正在运行

# 返回前给后台线程的短暂等待：尽量让状态先推进到稳定态（手动暂停/done）。
# 真实长渲染会在此后继续后台跑，HTTP 已返回 running。
_STARTUP_WAIT = 0.3


def _busy():
    return _worker is not None and _worker.is_alive()


class StartBody(BaseModel):
    raw_folder: str
    stabilize: dict
    fps: int
    social: dict
    workflow: Optional[list] = None
    output_path: str


class SocialFromBody(BaseModel):
    src: str
    social: dict


@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    global _runner, _worker
    if _busy():
        raise HTTPException(status_code=409, detail="正在运行，请稍候")
    data = body.dict()
    workflow_names = data.pop("workflow", None)
    config = PipelineConfig(**data)
    try:
        config.validate()  # 同步校验，配置错误立即 400
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    stages = workflows.build_stages(workflow_names) if workflow_names else default_stages()
    _runner = PipelineRunner(stages=stages, emit=_progress_log.append)
    _runner._notice = None
    # 后台线程跑流水线（遇手动阶段暂停 / 渲染长任务），HTTP 立即返回
    _worker = threading.Thread(target=_runner.start, args=(config,), daemon=True)
    _worker.start()
    _worker.join(_STARTUP_WAIT)
    return _runner.status()


def _run_continue():
    try:
        _runner.continue_()
    except (ValueError, RuntimeError) as exc:
        _runner._state = PipelineState.FAILED
        _runner._error = str(exc)


@app.post("/pipeline/continue")
def pipeline_continue():
    global _worker
    if _busy():
        raise HTTPException(status_code=409, detail="正在运行，请稍候")
    if _runner.status()["state"] != PipelineState.WAITING_FOR_USER:
        raise HTTPException(status_code=409, detail="当前不处于等待用户状态")
    _worker = threading.Thread(target=_run_continue, daemon=True)
    _worker.start()
    _worker.join(_STARTUP_WAIT)
    return _runner.status()


@app.get("/pipeline/status")
def pipeline_status():
    return _runner.status()


@app.get("/workflows")
def get_workflows():
    return {"workflows": _workflow_store.all()}


class SaveWorkflowBody(BaseModel):
    name: str
    stages: list


@app.post("/workflows", status_code=201)
def save_workflow(body: SaveWorkflowBody):
    try:
        _workflow_store.save(body.name, body.stages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@app.get("/preview/frames")
def preview_frames(folder: str):
    frames = preview.list_frames(folder)
    return {
        "count": len(frames),
        "strip": preview.strip_names(frames),
        "anim": preview.anim_names(frames),
    }


@app.get("/preview/thumb")
def preview_thumb(folder: str, name: str):
    src = Path(folder) / name
    if not src.is_file():
        raise HTTPException(status_code=404, detail="帧不存在")
    thumb = preview.generate_thumbnail(str(src), 320, _THUMB_CACHE)
    if not Path(thumb).exists():
        raise HTTPException(status_code=500, detail="缩略图生成失败")
    return FileResponse(thumb, media_type="image/png")


@app.get("/preview/best_frame")
def preview_best_frame(folder: str):
    """挑文件夹里平均饱和度最高的一帧（用作 UI 模糊背景）。"""
    from pipeline import export
    binary = export.ensure_export_binary()
    name = preview.best_frame(folder, binary)
    if not name:
        raise HTTPException(status_code=404, detail="无可分析的帧")
    return {"name": name}


@app.get("/preview/meta")
def preview_meta(folder: str):
    """读首帧的相机/拍摄/分辨率元数据（只读展示，母版按此原始分辨率自动建）。"""
    from pipeline import export
    binary = export.ensure_export_binary()
    return preview.read_metadata(folder, binary)


@app.get("/preview/file_thumb")
def preview_file_thumb(src: str):
    """任意单个图片/视频文件的缩略图（选区窗口底图）。"""
    if not Path(src).is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    thumb = preview.generate_thumbnail(src, 640, _THUMB_CACHE)
    if not Path(thumb).exists():
        raise HTTPException(status_code=500, detail="缩略图生成失败")
    return FileResponse(thumb, media_type="image/png")


@app.post("/export/social_from")
def export_social_from(body: SocialFromBody):
    """把已有成片（mov）直接转社媒版，输出到源同目录。"""
    from pipeline import export
    src = Path(body.src)
    if not src.is_file():
        raise HTTPException(status_code=404, detail="成片不存在")
    binary = export.ensure_export_binary()
    try:
        out = export.transcode_social(str(src), str(src.parent), body.social,
                                      emit=_progress_log.append, binary=binary, prefix=src.stem)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"output": str(out)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8756)
