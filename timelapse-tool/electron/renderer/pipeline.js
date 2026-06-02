// 四个阶段固定顺序
const STAGES = ["BR", "LRT", "AE", "PR"];

// 把表单原始值转成后端 /pipeline/start 需要的 payload
function buildStartPayload(values) {
  const [w, h] = String(values.resolution).split("x").map((n) => parseInt(n, 10));
  return {
    raw_folder: values.raw_folder,
    camera_name: values.camera_name,
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

// 「继续」按钮文案随当前手动阶段变化
function continueLabel(status) {
  if (status.current_stage === "BR") return "我已在 Camera Raw 完成，继续";
  if (status.current_stage === "LRT") return "我已在 LRT 完成，继续";
  return "继续";
}

// 应用阶段看板模型到 DOM
function renderBoard(status) {
  const model = stageBoardModel(status);
  for (const name of STAGES) {
    const el = document.querySelector(`.stage[data-stage="${name}"]`);
    if (el) el.className = "stage" + (model[name] ? " " + model[name] : "");
  }
}

function readForm() {
  const id = (x) => document.getElementById(x);
  return {
    raw_folder: id("raw_folder").value,
    camera_name: id("camera_name").value,
    lrt_export_folder: id("lrt_export_folder").value,
    stabilize: id("stabilize").checked,
    resolution: id("resolution").value,
    fps: id("fps").value,
    codec: id("codec").value,
    output_path: id("output_path").value,
  };
}

async function initPipeline(httpBase) {
  const id = (x) => document.getElementById(x);
  const errEl = id("pipeline-error");
  const cameraSel = id("camera_name");
  const resSel = id("resolution");

  try {
    const cams = await fetch(httpBase + "/cameras").then((r) => r.json());
    cameraSel.innerHTML = "";
    for (const cam of cams.cameras) {
      const opt = document.createElement("option");
      opt.value = cam.name;
      opt.textContent = cam.name;
      cameraSel.appendChild(opt);
    }
  } catch (_) {
    errEl.textContent = "无法加载相机列表";
    return;
  }

  async function loadResolutions() {
    const name = cameraSel.value;
    const data = await fetch(httpBase + "/cameras/" + encodeURIComponent(name) + "/resolutions").then((r) => r.json());
    resSel.innerHTML = "";
    for (const o of data.options) {
      const opt = document.createElement("option");
      opt.value = o.size[0] + "x" + o.size[1];
      opt.textContent = o.label + " (" + o.size[0] + "×" + o.size[1] + ")";
      resSel.appendChild(opt);
    }
  }
  cameraSel.addEventListener("change", loadResolutions);
  await loadResolutions();

  async function refreshStatus() {
    const status = await fetch(httpBase + "/pipeline/status").then((r) => r.json());
    renderBoard(status);
    const contBtn = id("btn-continue");
    contBtn.classList.toggle("hidden", !canContinue(status));
    contBtn.textContent = continueLabel(status);
    if (status.state === "failed") errEl.textContent = "失败：" + (status.error || "");
    return status;
  }

  id("btn-start").addEventListener("click", async () => {
    errEl.textContent = "";
    const res = await fetch(httpBase + "/pipeline/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildStartPayload(readForm())),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      errEl.textContent = "启动失败：" + (e.detail || res.status);
      return;
    }
    await refreshStatus();
  });

  id("btn-continue").addEventListener("click", async () => {
    errEl.textContent = "";
    const res = await fetch(httpBase + "/pipeline/continue", { method: "POST" });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      errEl.textContent = "继续失败：" + (e.detail || res.status);
      return;
    }
    await refreshStatus();
  });

  await refreshStatus();
}

if (typeof window !== "undefined") {
  window.initPipeline = initPipeline;
}

if (typeof module !== "undefined") {
  module.exports = { buildStartPayload, stageBoardModel, canContinue, continueLabel, STAGES };
}
