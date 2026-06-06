// 四个阶段固定顺序
const STAGES = ["BR", "LRT", "AE", "导出"];

// 把表单原始值转成后端 /pipeline/start 需要的 payload
function buildStartPayload(values) {
  return {
    raw_folder: values.raw_folder,
    fps: parseInt(values.fps, 10),
    output_path: values.output_path,
    stabilize: {
      enabled: Boolean(values.stabilize_enabled),
      result: values.stabilize_result,
      smoothness: parseInt(values.stabilize_smoothness, 10),
      method: values.stabilize_method,
    },
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

// 手动阶段的操作引导（含圣光 Holy Grail）
const STAGE_GUIDE = {
  BR: "BR · 在 Adobe Bridge 中全选该文件夹的 RAW，按 ⌘R 进入 Camera Raw，调整透视矫正 / 镜头配置文件 / 消色差，完成后点「继续」。",
  LRT: "LRT · 在 LRTimelapse 中依次：① 关键帧向导设置关键帧 → ② 若是日转夜/夜转日素材，走「圣光 Holy Grail」向导处理曝光过渡 → ③ 视觉去闪（Deflicker）→ ④ 自动过渡 → ⑤ 保存（写入 XMP）。无需导出图像序列，AE 会直接读取 RAW。完成后点「继续」。",
};

// 当前若停在某手动阶段，返回该阶段的引导文字，否则空串
function guidanceText(status) {
  if (status.state !== "waiting_for_user") return "";
  return STAGE_GUIDE[status.current_stage] || "";
}

const WORKFLOW_ORDER = ["BR", "LRT", "AE", "导出"];

// 把阶段勾选状态转成固定顺序的阶段名数组
function collectWorkflowStages(checked) {
  return WORKFLOW_ORDER.filter((name) => checked[name]);
}

const SOCIAL_RATIO = { "16:9": [16, 9], "9:16": [9, 16], "3:4": [3, 4], "1:1": [1, 1], "3:2": [3, 2] };
const SOCIAL_SHORT = { "720p": 720, "1080p": 1080, "4K": 2160 };

function _even(n) { n = Math.round(n); return n % 2 === 0 ? n : n + 1; }

function socialPixels(aspect, resolution) {
  const [a, b] = SOCIAL_RATIO[aspect];
  const short = SOCIAL_SHORT[resolution];
  const long = short * Math.max(a, b) / Math.min(a, b);
  if (a > b) return [_even(long), _even(short)];
  if (a < b) return [_even(short), _even(long)];
  return [_even(short), _even(short)];
}

// 运镜方向选项随类型联动（与后端 export_formats.DIRECTIONS 同口径）
const MOTION_DIRECTIONS = {
  none: [],
  kenburns: [["in", "放大（推近）"], ["out", "缩小（拉远）"]],
  pan: [["left", "镜头左移"], ["right", "镜头右移"], ["up", "镜头上移"], ["down", "镜头下移"]],
  sweep: [["lr", "左 → 右"], ["rl", "右 → 左"]],
};

function motionDirections(type) {
  return MOTION_DIRECTIONS[type] || [];
}

// 竖屏横扫只对竖屏画幅有意义；横/方画幅运镜只给 Ken Burns / Pan
const PORTRAIT_ASPECTS = new Set(["9:16", "3:4"]);

function motionTypesFor(aspect) {
  const types = [["none", "无"], ["kenburns", "Ken Burns 推拉"], ["pan", "平移 Pan"]];
  if (PORTRAIT_ASPECTS.has(aspect)) types.push(["sweep", "竖屏横扫"]);
  return types;
}

function boxToNormalized(rect, dispW, dispH) {
  const clamp = (v) => Math.max(0, Math.min(1, v));
  return [clamp(rect.x / dispW), clamp(rect.y / dispH), clamp(rect.w / dispW), clamp(rect.h / dispH)];
}

function buildMotionConfig(values) {
  const m = { type: values.motion_type, direction: values.motion_direction, intensity: values.motion_intensity };
  if (values.motion_box) m.box = values.motion_box;
  return m;
}

function buildSocialConfig(values) {
  return {
    format: values.social_format,
    aspect: values.social_aspect,
    resolution: values.social_resolution,
    motion: buildMotionConfig(values),
    subject: Boolean(values.motion_subject),
  };
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
    fps: id("fps").value,
    output_path: id("output_path").value,
    stabilize_enabled: id("stabilize_enabled").checked,
    stabilize_result: id("stabilize_result").value,
    stabilize_smoothness: id("stabilize_smoothness").value,
    stabilize_method: id("stabilize_method").value,
    social_format: id("social_format").value,
    social_aspect: id("social_aspect").value,
    social_resolution: id("social_resolution").value,
    motion_type: id("motion_type").value,
    motion_direction: id("motion_direction").value,
    motion_intensity: id("motion_intensity").value,
    motion_subject: id("motion_subject").checked,
  };
}

// 把元数据格式化成展示行（相机/镜头 + 分辨率/ISO/光圈/快门/焦距）
function formatMeta(m) {
  if (!m || (!m.camera && !m.width)) return null;
  const exp = m.exposure ? (m.exposure >= 1 ? m.exposure + "s" : "1/" + Math.round(1 / m.exposure) + "s") : null;
  const cam = [m.make, m.camera].filter(Boolean).join(" ") + (m.lens ? " · " + m.lens : "");
  const shot = [];
  if (m.width && m.height) shot.push(m.width + "×" + m.height);
  if (m.iso) shot.push("ISO " + m.iso);
  if (m.fnumber) shot.push("f/" + m.fnumber);
  if (exp) shot.push(exp);
  if (m.focal) shot.push(m.focal + "mm");
  return { cam: cam, shot: shot.join(" · ") };
}

async function initPipeline(httpBase) {
  const id = (x) => document.getElementById(x);
  const errEl = id("pipeline-error");

  // 加载工作流模板（内置 + 自定义）
  let workflowMap = {};
  async function loadWorkflows(selectName) {
    const data = await fetch(httpBase + "/workflows").then((r) => r.json());
    workflowMap = data.workflows;
    const sel = id("workflow_select");
    sel.innerHTML = "";
    for (const name of Object.keys(workflowMap)) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name + "（" + workflowMap[name].join("-") + "）";
      sel.appendChild(opt);
    }
    if (selectName && workflowMap[selectName]) sel.value = selectName;
  }
  try {
    await loadWorkflows("全流程");
  } catch (_) {
    errEl.textContent = "无法加载工作流模板";
    return;
  }

  id("wf_save").addEventListener("click", async () => {
    const checked = {};
    document.querySelectorAll(".wf-stage").forEach((c) => { checked[c.value] = c.checked; });
    const stages = collectWorkflowStages(checked);
    const wfErr = id("wf-error");
    wfErr.textContent = "";
    const name = id("wf_name").value.trim();
    if (!name) { wfErr.textContent = "请填模板名"; return; }
    const res = await fetch(httpBase + "/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, stages: stages }),
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      wfErr.textContent = "保存失败：" + (e.detail || res.status);
      return;
    }
    await loadWorkflows(name);
  });

  // 社媒导出预览
  function syncSocialPreview() {
    const [w, h] = socialPixels(id("social_aspect").value, id("social_resolution").value);
    const tag = id("social_format").value === "H.265" ? "h265" : "h264";
    id("social-preview").textContent = `${w}×${h} · ${id("social_format").value} · timelapse_social_${w}x${h}_${tag}.mp4`;
  }
  ["social_format", "social_aspect", "social_resolution"].forEach((x) =>
    id(x).addEventListener("change", syncSocialPreview));
  syncSocialPreview();

  // 运镜：方向随类型联动，无运镜时方向/强度禁用
  function syncMotion() {
    const type = id("motion_type").value;
    const dirSel = id("motion_direction");
    dirSel.innerHTML = "";
    for (const [val, label] of motionDirections(type)) {
      const opt = document.createElement("option");
      opt.value = val; opt.textContent = label;
      dirSel.appendChild(opt);
    }
    const off = type === "none";
    dirSel.disabled = off;
    id("motion_intensity").disabled = off || type === "sweep";  // 横扫无强度
  }
  id("motion_type").addEventListener("change", syncMotion);

  // 画幅变 → 重填可用运镜类型（横/方画幅去掉竖屏横扫），保留仍可用的当前选择
  function syncMotionTypes() {
    const cur = id("motion_type").value;
    const types = motionTypesFor(id("social_aspect").value);
    const sel = id("motion_type");
    sel.innerHTML = "";
    for (const [val, label] of types) {
      const opt = document.createElement("option");
      opt.value = val; opt.textContent = label;
      sel.appendChild(opt);
    }
    sel.value = types.some((t) => t[0] === cur) ? cur : "none";
    syncMotion();
  }
  id("social_aspect").addEventListener("change", syncMotionTypes);
  syncMotionTypes();

  // AE 去闪 / 增稳 开关的细项显隐联动
  function syncToggle(cbId, fieldsId) {
    id(fieldsId).classList.toggle("hidden", !id(cbId).checked);
  }
  id("stabilize_enabled").addEventListener("change", () => syncToggle("stabilize_enabled", "stabilize-fields"));
  syncToggle("stabilize_enabled", "stabilize-fields");

  // 选中的 RAW 素材首帧 → 模糊背景（透过玻璃卡片看到片子）
  async function setBlurBackground(folder) {
    const bg = id("bg-blur");
    if (!folder) { bg.classList.remove("active"); return; }
    const apply = (name) => {
      bg.style.backgroundImage = `url("${window.preview.thumbUrl(httpBase, folder, name)}")`;
      bg.classList.add("active");
    };
    // ① 首帧先垫上（快）
    try {
      const data = await fetch(httpBase + "/preview/frames?folder=" + encodeURIComponent(folder)).then((r) => r.json());
      if (data.count > 0) apply(data.strip[0]);
      else { bg.classList.remove("active"); return; }
    } catch (_) { bg.classList.remove("active"); return; }
    // ② 后台挑饱和度最高的一帧，算完平滑替换
    try {
      const best = await fetch(httpBase + "/preview/best_frame?folder=" + encodeURIComponent(folder)).then((r) => r.json());
      if (best && best.name) apply(best.name);
    } catch (_) { /* 保留首帧 */ }
  }

  // 读首帧元数据 → 素材信息展示（相机/拍摄/分辨率，自动识别）
  async function setMaterialInfo(folder) {
    const box = id("material-info");
    if (!folder) { box.classList.add("hidden"); return; }
    try {
      const m = await fetch(httpBase + "/preview/meta?folder=" + encodeURIComponent(folder)).then((r) => r.json());
      const f = formatMeta(m);
      if (!f) { box.classList.add("hidden"); return; }
      id("material-rows").innerHTML = `<div>${f.cam}</div><div class="material-shot">${f.shot}</div>`;
      box.classList.remove("hidden");
    } catch (_) { box.classList.add("hidden"); }
  }

  // 选中 RAW 文件夹后：同时更新模糊背景 + 素材信息
  function onRawFolder(folder) { setBlurBackground(folder); setMaterialInfo(folder); }

  // 文件夹选择按钮 → 调原生对话框，填回对应输入框
  document.querySelectorAll(".btn-browse[data-target]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.api || !window.api.chooseDirectory) return;
      const dir = await window.api.chooseDirectory();
      if (dir) {
        id(btn.dataset.target).value = dir;
        if (btn.dataset.target === "raw_folder") onRawFolder(dir);
      }
    });
  });
  // 手动改 RAW 路径也更新
  id("raw_folder").addEventListener("change", (e) => onRawFolder(e.target.value.trim()));
  if (id("raw_folder").value.trim()) onRawFolder(id("raw_folder").value.trim());

  // 预览：缩略图条 + 播放轮播
  let animFrames = [];
  let animFolder = "";
  let animTimer = null;
  let animIdx = 0;

  function stopAnim() {
    if (animTimer) { clearInterval(animTimer); animTimer = null; }
    id("preview-play").textContent = "▶ 播放";
    id("preview-stage").classList.add("hidden");
    id("preview-strip").classList.remove("hidden");
  }

  async function loadPreview(folder) {
    stopAnim();
    const data = await fetch(httpBase + "/preview/frames?folder=" + encodeURIComponent(folder)).then((r) => r.json());
    id("preview-panel").classList.remove("hidden");
    id("preview-info").textContent = "共 " + data.count + " 帧";
    const strip = id("preview-strip");
    strip.innerHTML = "";
    if (data.count === 0) { strip.textContent = "该文件夹没有可预览的图片"; return; }
    for (const name of data.strip) {
      const img = document.createElement("img");
      img.src = window.preview.thumbUrl(httpBase, folder, name);
      img.className = "thumb";
      strip.appendChild(img);
    }
    animFrames = data.anim;
    animFolder = folder;
  }

  document.querySelectorAll(".btn-preview").forEach((btn) => {
    btn.addEventListener("click", () => {
      const folder = id(btn.dataset.folder).value;
      if (folder) loadPreview(folder);
    });
  });

  id("preview-play").addEventListener("click", () => {
    if (animTimer) { stopAnim(); return; }
    if (!animFrames.length) return;
    const stage = id("preview-stage");
    id("preview-strip").classList.add("hidden");
    stage.classList.remove("hidden");
    id("preview-play").textContent = "⏸ 停止";
    animIdx = 0;
    animTimer = setInterval(() => {
      stage.src = window.preview.thumbUrl(httpBase, animFolder, animFrames[animIdx]);
      animIdx = window.preview.nextFrameIndex(animIdx, animFrames.length);
    }, 90);
  });

  function buildStartBody() {
    const payload = buildStartPayload(readForm());
    payload.social = buildSocialConfig(readForm());
    payload.workflow = workflowMap[id("workflow_select").value] || null;
    return payload;
  }

  async function refreshStatus() {
    const status = await fetch(httpBase + "/pipeline/status").then((r) => r.json());
    renderBoard(status);
    const contBtn = id("btn-continue");
    contBtn.classList.toggle("hidden", !canContinue(status));
    contBtn.textContent = continueLabel(status);
    const guide = guidanceText(status);
    const guideEl = id("stage-guide");
    guideEl.textContent = guide;
    guideEl.classList.toggle("hidden", !guide);
    const noticeEl = id("pipeline-notice");
    noticeEl.textContent = status.notice || "";
    noticeEl.classList.toggle("hidden", !status.notice);
    if (status.state === "failed") errEl.textContent = "失败：" + (status.error || "");
    return status;
  }

  id("btn-start").addEventListener("click", async () => {
    errEl.textContent = "";
    const res = await fetch(httpBase + "/pipeline/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildStartBody()),
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
  module.exports = { buildStartPayload, stageBoardModel, canContinue, continueLabel, guidanceText, buildSocialConfig, buildMotionConfig, motionDirections, motionTypesFor, socialPixels, collectWorkflowStages, formatMeta, boxToNormalized, STAGES };
}
