from fastapi import FastAPI

app = FastAPI(title="Timelapse Tool Backend")


@app.get("/health")
def health():
    return {"status": "ok"}
