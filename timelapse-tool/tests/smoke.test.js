const { switchTab, statusLabel } = require("../electron/renderer/app.js");

test("switchTab 切换激活面板", () => {
  document.body.innerHTML = `
    <button class="tab active" data-tab="pipeline"></button>
    <button class="tab" data-tab="selector"></button>
    <section id="pipeline" class="panel active"></section>
    <section id="selector" class="panel"></section>`;
  switchTab("selector");
  expect(document.getElementById("selector").classList.contains("active")).toBe(true);
  expect(document.getElementById("pipeline").classList.contains("active")).toBe(false);
});

test("statusLabel 根据健康状态返回文案", () => {
  expect(statusLabel(true)).toBe("后端已连接");
  expect(statusLabel(false)).toBe("后端连接失败");
});
