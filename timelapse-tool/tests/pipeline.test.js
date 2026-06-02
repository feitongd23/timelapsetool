const { buildStartPayload, stageBoardModel, canContinue, continueLabel, buildExportConfig } = require("../electron/renderer/pipeline.js");

test("buildStartPayload 转换类型", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw",
    camera_name: "Sony A7R IV",
    lrt_export_folder: "/seq",
    resolution: "3840x2160",
    fps: "24",
    output_path: "/out",
    deflicker_enabled: false,
    deflicker_strength: "50",
    deflicker_time_radius: "2",
    stabilize_enabled: false,
    stabilize_result: "smooth",
    stabilize_smoothness: "50",
    stabilize_method: "subspace",
  });
  expect(payload.fps).toBe(24);
  expect(payload.resolution).toEqual([3840, 2160]);
  expect(payload.raw_folder).toBe("/raw");
  expect(payload).not.toHaveProperty("acr_preset_path");
});

test("buildStartPayload 带 deflicker/stabilize", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw", camera_name: "Cam", lrt_export_folder: "/seq",
    resolution: "3840x2160", fps: "24", output_path: "/out",
    deflicker_enabled: true, deflicker_strength: "60", deflicker_time_radius: "3",
    stabilize_enabled: true, stabilize_result: "smooth",
    stabilize_smoothness: "70", stabilize_method: "subspace",
  });
  expect(payload.deflicker).toEqual({ enabled: true, strength: 60, time_radius: 3 });
  expect(payload.stabilize).toEqual({ enabled: true, result: "smooth", smoothness: 70, method: "subspace" });
});

test("continueLabel 随手动阶段变化", () => {
  expect(continueLabel({ current_stage: "BR" })).toBe("我已在 Camera Raw 完成，继续");
  expect(continueLabel({ current_stage: "LRT" })).toBe("我已在 LRT 完成，继续");
});

test("stageBoardModel 标记已完成/进行中阶段", () => {
  const model = stageBoardModel({ state: "waiting_for_user", current_stage: "LRT", completed: ["BR"], error: null });
  expect(model.BR).toBe("done");
  expect(model.LRT).toBe("active");
  expect(model.AE).toBe("");
});

test("stageBoardModel 失败态标记失败阶段", () => {
  const model = stageBoardModel({ state: "failed", current_stage: "AE", completed: ["BR"], error: "炸了" });
  expect(model.BR).toBe("done");
  expect(model.AE).toBe("failed");
});

test("stageBoardModel 完成态全部 done", () => {
  const model = stageBoardModel({ state: "done", current_stage: "PR", completed: ["BR", "AE", "PR"], error: null });
  expect(model.BR).toBe("done");
  expect(model.PR).toBe("done");
});

test("canContinue 仅在等待态为真", () => {
  expect(canContinue({ state: "waiting_for_user" })).toBe(true);
  expect(canContinue({ state: "running" })).toBe(false);
  expect(canContinue({ state: "done" })).toBe(false);
});

const PRESET_TABLE = {
  "母版 · ProRes 422 HQ": { codec: "ProRes", container: "MOV", prores_profile: "422 HQ" },
};

test("buildExportConfig 预设模式展开预设", () => {
  const exp = buildExportConfig({ mode: "preset", preset: "母版 · ProRes 422 HQ" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "ProRes", container: "MOV", prores_profile: "422 HQ" });
});

test("buildExportConfig 手动 ProRes", () => {
  const exp = buildExportConfig({ mode: "manual", codec: "ProRes", prores_profile: "4444" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "ProRes", container: "MOV", prores_profile: "4444" });
});

test("buildExportConfig 手动 H.264 转换码率为整数", () => {
  const exp = buildExportConfig({ mode: "manual", codec: "H.264", bitrate_mbps: "80", quality: "high" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "H.264", container: "MP4", bitrate_mbps: 80, quality: "high" });
});

test("buildExportConfig 手动 H.265 带位深", () => {
  const exp = buildExportConfig({ mode: "manual", codec: "H.265", bitrate_mbps: "60", bit_depth: "10" }, PRESET_TABLE);
  expect(exp).toEqual({ codec: "H.265", container: "MP4", bitrate_mbps: 60, bit_depth: 10 });
});
