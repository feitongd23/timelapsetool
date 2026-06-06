const { buildStartPayload, stageBoardModel, canContinue, continueLabel, guidanceText, buildSocialConfig, buildMotionConfig, motionDirections, motionTypesFor, socialPixels, collectWorkflowStages, formatMeta, boxToNormalized, progressPercent } = require("../electron/renderer/pipeline.js");

test("guidanceText 停在 LRT 时含圣光提示", () => {
  const g = guidanceText({ state: "waiting_for_user", current_stage: "LRT" });
  expect(g).toContain("圣光");
  expect(g).toContain("关键帧");
});

test("guidanceText 非等待态返回空", () => {
  expect(guidanceText({ state: "running", current_stage: "LRT" })).toBe("");
  expect(guidanceText({ state: "done", current_stage: "导出" })).toBe("");
});

test("collectWorkflowStages 按勾选返回固定顺序子集", () => {
  const checked = { BR: false, LRT: true, AE: true, "导出": true };
  expect(collectWorkflowStages(checked)).toEqual(["LRT", "AE", "导出"]);
});

test("collectWorkflowStages 全不选返回空", () => {
  expect(collectWorkflowStages({ BR: false, LRT: false, AE: false, "导出": false })).toEqual([]);
});

test("buildStartPayload 转换类型（无相机/分辨率，母版自动原始分辨率）", () => {
  const payload = buildStartPayload({
    raw_folder: "/raw",
    fps: "24",
    output_path: "/out",
    stabilize_enabled: false,
    stabilize_result: "smooth",
    stabilize_smoothness: "50",
    stabilize_method: "subspace",
  });
  expect(payload.fps).toBe(24);
  expect(payload.raw_folder).toBe("/raw");
  expect(payload.stabilize.enabled).toBe(false);
  expect(payload).not.toHaveProperty("resolution");
  expect(payload).not.toHaveProperty("camera_name");
});

test("formatMeta 拼相机与拍摄信息", () => {
  const f = formatMeta({ make: "SONY", camera: "ILCE-7RM4A", lens: "FE 24-70mm F2.8 GM",
                         width: 9504, height: 6336, iso: 100, fnumber: 9, exposure: 0.2, focal: 28 });
  expect(f.cam).toContain("ILCE-7RM4A");
  expect(f.cam).toContain("24-70");
  expect(f.shot).toContain("9504×6336");
  expect(f.shot).toContain("ISO 100");
  expect(f.shot).toContain("f/9");
  expect(f.shot).toContain("1/5s");
  expect(f.shot).toContain("28mm");
});

test("formatMeta 空数据返回 null", () => {
  expect(formatMeta({})).toBeNull();
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
  const model = stageBoardModel({ state: "done", current_stage: "导出", completed: ["BR", "AE", "导出"], error: null });
  expect(model.BR).toBe("done");
  expect(model["导出"]).toBe("done");
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

test("motionTypesFor 横/方画幅无竖屏横扫，竖版有", () => {
  expect(motionTypesFor("9:16").map((t) => t[0])).toContain("sweep");
  expect(motionTypesFor("3:4").map((t) => t[0])).toContain("sweep");
  expect(motionTypesFor("16:9").map((t) => t[0])).toEqual(["none", "kenburns", "pan"]);
  expect(motionTypesFor("3:2").map((t) => t[0])).not.toContain("sweep");
  expect(motionTypesFor("1:1").map((t) => t[0])).not.toContain("sweep");
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

test("boxToNormalized 像素框转归一化并夹紧", () => {
  expect(boxToNormalized({ x: 100, y: 50, w: 200, h: 400 }, 1000, 1000))
    .toEqual([0.1, 0.05, 0.2, 0.4]);
  const n = boxToNormalized({ x: -10, y: 0, w: 2000, h: 100 }, 1000, 1000);
  expect(n[0]).toBe(0);
  expect(n[2]).toBe(1);
});

test("buildSocialConfig 带 box（有框时写入 motion.box）", () => {
  const s = buildSocialConfig({
    social_format: "H.265", social_aspect: "9:16", social_resolution: "1080p",
    motion_type: "kenburns", motion_direction: "in", motion_intensity: "medium",
    motion_subject: false, motion_box: [0.3, 0.3, 0.2, 0.2],
  });
  expect(s.motion.box).toEqual([0.3, 0.3, 0.2, 0.2]);
});

test("buildSocialConfig 无 box 时 motion 不含 box", () => {
  const s = buildSocialConfig({
    social_format: "H.265", social_aspect: "9:16", social_resolution: "1080p",
    motion_type: "kenburns", motion_direction: "in", motion_intensity: "medium",
    motion_subject: false, motion_box: null,
  });
  expect(s.motion).not.toHaveProperty("box");
});

test("progressPercent: done=100 / running 用 fraction / 无 fraction 保持", () => {
  expect(progressPercent({ state: "done" }, 50)).toBe(100);
  expect(progressPercent({ state: "running", progress: { fraction: 0.43 } }, 0)).toBe(43);
  expect(progressPercent({ state: "running", progress: { fraction: null } }, 60)).toBe(60);
  expect(progressPercent({ state: "failed" }, 30)).toBe(30);
  expect(progressPercent({ state: "idle" }, 0)).toBe(0);
});
