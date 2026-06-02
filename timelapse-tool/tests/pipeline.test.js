const { buildStartPayload, stageBoardModel, canContinue, continueLabel } = require("../electron/renderer/pipeline.js");

test("buildStartPayload 转换类型", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw",
    camera_name: "Sony A7R IV",
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
  expect(payload).not.toHaveProperty("acr_preset_path");
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
