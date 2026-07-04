# tests/test_gridmap.py
import httpx
from PIL import Image

from skyfire.gridmap import fetch_cloud_grid, grid_points, render_grid_png

BBOX = (110.0, 36.0, 122.0, 44.0)   # lon0, lat0, lon1, lat1


def test_grid_points_row_major_north_first():
    pts = grid_points(BBOX, step=2.0)
    lats = sorted({lat for lat, _ in pts}, reverse=True)
    assert lats[0] == 44.0 and lats[-1] == 36.0
    assert len(pts) == 5 * 7           # lat 44..36 step2 ×5, lon 110..122 step2 ×7


def test_fetch_cloud_grid_shapes_and_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        n = len(dict(request.url.params)["latitude"].split(","))
        loc = {"hourly": {"time": ["2026-05-06T19:00"],
                          "cloud_cover_high": [80], "cloud_cover_mid": [40],
                          "cloud_cover_low": [5]}}
        return httpx.Response(200, json=[loc] * n)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pts = grid_points(BBOX, step=2.0)
    grid = fetch_cloud_grid(client, pts, 5, 7, "Asia/Shanghai",
                            "2026-05-06T19:00", date="2026-05-06")
    assert seen["host"] == "historical-forecast-api.open-meteo.com"
    assert set(grid) == {"high", "mid", "low"}
    assert len(grid["high"]) == 5 and len(grid["high"][0]) == 7
    assert grid["high"][0][0] == 80 and grid["low"][0][0] == 5


def test_render_grid_png_triple_panel(tmp_path):
    grid = {k: [[v] * 7 for _ in range(5)]
            for k, v in (("high", 80), ("mid", 40), ("low", 5))}
    out = render_grid_png(grid, tmp_path / "clouds.png", label="2026-05-06 19:00")
    img = Image.open(out)
    assert img.width > img.height * 2      # 三联横排
