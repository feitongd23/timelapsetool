// 四个阶段固定顺序
const STAGES = ["BR", "LRT", "AE", "PR"];

// 把表单原始值转成后端 /pipeline/start 需要的 payload
function buildStartPayload(values) {
  const [w, h] = String(values.resolution).split("x").map((n) => parseInt(n, 10));
  return {
    raw_folder: values.raw_folder,
    camera_name: values.camera_name,
    acr_preset_path: values.acr_preset_path,
    lrt_export_folder: values.lrt_export_folder,
    stabilize: Boolean(values.stabilize),
    resolution: [w, h],
    fps: parseInt(values.fps, 10),
    codec: values.codec,
    output_path: values.output_path,
  };
}

// 把 /pipeline/status 映射成每个阶段的 CSS class
function stageBoardModel(status) {
  const completed = new Set(status.completed || []);
  const model = {};
  for (const name of STAGES) {
    if (status.state === "failed" && status.current_stage === name) {
      model[name] = "failed";
    } else if (status.state === "done") {
      model[name] = "done";
    } else if (completed.has(name)) {
      model[name] = "done";
    } else if (status.current_stage === name && status.state !== "failed") {
      model[name] = "active";
    } else {
      model[name] = "";
    }
  }
  return model;
}

function canContinue(status) {
  return status.state === "waiting_for_user";
}

if (typeof module !== "undefined") {
  module.exports = { buildStartPayload, stageBoardModel, canContinue, STAGES };
}
