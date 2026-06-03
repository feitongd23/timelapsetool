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
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.cameras import CameraStore
from pipeline.models import PipelineConfig
from pipeline.runner import PipelineRunner
from pipeline.stages import default_stages
from pipeline.export_formats import PRESETS
from pipeline import workflows
from pipeline import preview

_THUMB_CACHE = str(Path(tempfile.gettempdir()) / "timelapse_thumbs")

_CAMERAS_PATH = Path(__file__).parent / "cameras.json"
_camera_store = CameraStore(_CAMERAS_PATH)

_WORKFLOWS_PATH = Path(__file__).parent / "workflows.json"
_workflow_store = workflows.WorkflowStore(_WORKFLOWS_PATH)

_progress_log = []
_runner = PipelineRunner(stages=default_stages(), emit=_progress_log.append)


@app.get("/cameras")
def get_cameras():
    return {"cameras": _camera_store.list()}


@app.get("/cameras/{name}/resolutions")
def get_resolutions(name: str):
    try:
        return {"options": _camera_store.resolution_options(name)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"未知相机: {name}")


class AddCameraBody(BaseModel):
    name: str
    native: list


@app.post("/cameras", status_code=201)
def add_camera(body: AddCameraBody):
    try:
        _camera_store.add(body.name, body.native)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


class StartBody(BaseModel):
    raw_folder: str
    camera_name: str
    lrt_export_folder: str
    stabilize: dict
    resolution: list
    fps: int
    export: Optional[dict] = None
    preset: Optional[str] = None
    workflow: Optional[list] = None
    output_path: str


@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    global _runner
    data = body.dict()
    workflow_names = data.pop("workflow", None)
    preset = data.pop("preset", None)
    if data.get("export") is None and preset:
        from pipeline.export_formats import expand_preset
        try:
            data["export"] = expand_preset(preset)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"未知导出预设: {preset}")
    config = PipelineConfig(**data)
    try:
        stages = workflows.build_stages(workflow_names) if workflow_names else default_stages()
        _runner = PipelineRunner(stages=stages, emit=_progress_log.append)
        _runner.start(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _runner.status()


@app.post("/pipeline/continue")
def pipeline_continue():
    try:
        _runner.continue_()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _runner.status()


@app.get("/pipeline/status")
def pipeline_status():
    return _runner.status()


@app.get("/export/presets")
def get_export_presets():
    return {"presets": list(PRESETS.keys())}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8756)
