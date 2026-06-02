const { buildStartPayload, stageBoardModel, canContinue } = require("../electron/renderer/pipeline.js");

test("buildStartPayload 转换类型", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw",
    camera_name: "Sony A7R IV",
    acr_preset_path: "/p.xmp",
    lrt_export_folder: "/seq",
    stabilize: true,
    resolution: "3840x2160",
    fps: "24",
    codec: "ProRes",
    output_path: "/out",
  });
  expect(payload.fps).toBe(24);
  expect(payload.resolution).toEqual([3840, 2160]);
  expect(payload.stabilize).toBe(true);
  expect(payload.raw_folder).toBe("/raw");
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
