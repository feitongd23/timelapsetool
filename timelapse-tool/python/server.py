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


from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from pipeline.cameras import CameraStore
from pipeline.models import PipelineConfig
from pipeline.runner import PipelineRunner
from pipeline.stages import default_stages

_CAMERAS_PATH = Path(__file__).parent / "cameras.json"
_camera_store = CameraStore(_CAMERAS_PATH)

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
    acr_preset_path: str
    lrt_export_folder: str
    stabilize: bool
    resolution: list
    fps: int
    codec: str
    output_path: str


@app.post("/pipeline/start")
def pipeline_start(body: StartBody):
    config = PipelineConfig(**body.dict())
    try:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8756)
