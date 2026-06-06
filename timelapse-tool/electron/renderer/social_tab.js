async function initSocialTab(httpBase) {
  const id = (x) => document.getElementById(x);
  let pickedBox = null;

  function syncDirections() {
    const sel = id("b_motion_direction"); sel.innerHTML = "";
    for (const [v, l] of motionDirections(id("b_motion_type").value)) {
      const o = document.createElement("option"); o.value = v; o.textContent = l; sel.appendChild(o);
    }
  }
  function syncTypes() {
    const cur = id("b_motion_type").value;
    const types = motionTypesFor(id("b_social_aspect").value);
    const sel = id("b_motion_type"); sel.innerHTML = "";
    for (const [v, l] of types) { const o = document.createElement("option"); o.value = v; o.textContent = l; sel.appendChild(o); }
    sel.value = types.some((t) => t[0] === cur) ? cur : "none";
    syncDirections();
    id("b_motion-box-row").classList.toggle("hidden", sel.value !== "kenburns");
  }
  function syncPreview() {
    const [w, h] = socialPixels(id("b_social_aspect").value, id("b_social_resolution").value);
    id("b_social-preview").textContent = `${w}×${h} · ${id("b_social_format").value}`;
  }
  function refreshHint() { id("b_motion-box-hint").textContent = pickedBox ? "已框选放大区域" : "未选（自动）"; }

  id("b_social_aspect").addEventListener("change", () => { syncTypes(); syncPreview(); });
  ["b_social_format", "b_social_resolution"].forEach((x) => id(x).addEventListener("change", syncPreview));
  id("b_motion_type").addEventListener("change", () => { syncDirections(); id("b_motion-box-row").classList.toggle("hidden", id("b_motion_type").value !== "kenburns"); });
  syncTypes(); syncPreview(); refreshHint();

  id("b_choose").addEventListener("click", async () => {
    if (!window.api || !window.api.chooseFile) return;
    const f = await window.api.chooseFile();
    if (f) { id("b_src").value = f; pickedBox = null; refreshHint(); }
  });

  id("b_btn-pick-box").addEventListener("click", () => {
    const src = id("b_src").value.trim();
    if (!src) { id("b_motion-box-hint").textContent = "请先选成片"; return; }
    window.cropModal.open(httpBase + "/preview/file_thumb?src=" + encodeURIComponent(src), (box) => { pickedBox = box; refreshHint(); });
  });

  id("b_convert").addEventListener("click", async () => {
    id("b_error").textContent = ""; id("b_result").textContent = "转换中…";
    const social = buildSocialConfig({
      social_format: id("b_social_format").value, social_aspect: id("b_social_aspect").value,
      social_resolution: id("b_social_resolution").value, motion_type: id("b_motion_type").value,
      motion_direction: id("b_motion_direction").value, motion_intensity: id("b_motion_intensity").value,
      motion_subject: id("b_motion_subject").checked, motion_box: pickedBox,
    });
    const res = await fetch(httpBase + "/export/social_from", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src: id("b_src").value, social: social }),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); id("b_result").textContent = ""; id("b_error").textContent = "失败：" + (e.detail || res.status); return; }
    const data = await res.json();
    id("b_result").textContent = "完成：" + data.output;
  });
}
if (typeof window !== "undefined") window.initSocialTab = initSocialTab;
