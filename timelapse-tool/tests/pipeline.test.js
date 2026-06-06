const { buildStartPayload, stageBoardModel, canContinue, continueLabel, guidanceText, buildSocialConfig, buildMotionConfig, motionDirections, socialPixels, collectWorkflowStages } = require("../electron/renderer/pipeline.js");

test("guidanceText 停在 LRT 时含圣光提示", () => {
  const g = guidanceText({ state: "waiting_for_user", current_stage: "LRT" });
  expect(g).toContain("圣光");
  expect(g).toContain("关键帧");
});

test("guidanceText 非等待态返回空", () => {
  expect(guidanceText({ state: "running", current_stage: "LRT" })).toBe("");
  expect(guidanceText({ state: "done", current_stage: "PR" })).toBe("");
});

test("collectWorkflowStages 按勾选返回固定顺序子集", () => {
  const checked = { BR: false, LRT: true, AE: true, PR: true };
  expect(collectWorkflowStages(checked)).toEqual(["LRT", "AE", "PR"]);
});

test("collectWorkflowStages 全不选返回空", () => {
  expect(collectWorkflowStages({ BR: false, LRT: false, AE: false, PR: false })).toEqual([]);
});

test("buildStartPayload 转换类型", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw",
    camera_name: "Sony A7R IV",
    resolution: "3840x2160",
    fps: "24",
    output_path: "/out",
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

test("buildStartPayload 带 stabilize", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw", camera_name: "Cam",
    resolution: "3840x2160", fps: "24", output_path: "/out",
    stabilize_enabled: true, stabilize_result: "smooth",
    stabilize_smoothness: "70", stabilize_method: "subspace",
  });
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

test("buildSocialConfig 含格式/画幅/分辨率/运镜/主体", () => {
  expect(buildSocialConfig({
    social_format: "H.265", social_aspect: "9:16", social_resolution: "1080p",
    motion_type: "kenburns", motion_direction: "in", motion_intensity: "medium", motion_subject: true,
  })).toEqual({
    format: "H.265", aspect: "9:16", resolution: "1080p",
    motion: { type: "kenburns", direction: "in", intensity: "medium" },
    subject: true,
  });
});

test("motionDirections 按类型联动", () => {
  expect(motionDirections("kenburns").map((d) => d[0])).toEqual(["in", "out"]);
  expect(motionDirections("pan").map((d) => d[0])).toEqual(["left", "right", "up", "down"]);
  expect(motionDirections("sweep").map((d) => d[0])).toEqual(["lr", "rl"]);
  expect(motionDirections("none")).toEqual([]);
});

test("socialPixels 与后端同口径", () => {
  expect(socialPixels("9:16", "1080p")).toEqual([1080, 1920]);
  expect(socialPixels("3:4", "720p")).toEqual([720, 960]);
  expect(socialPixels("3:2", "1080p")).toEqual([1620, 1080]);
});
