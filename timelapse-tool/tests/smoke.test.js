/**
 * @jest-environment jsdom
 */
// Copyright (c) 2026 杜非同. All rights reserved.
// Part of Timelapse Tool — proprietary software.
// Unauthorized copying, modification, or distribution is prohibited.

const { switchTab, statusLabel, pollHealth } = require("../electron/renderer/app.js");

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

test("pollHealth 在后端就绪前重试，最终连上", async () => {
  let calls = 0;
  const fetchFn = jest.fn(() => {
    calls++;
    if (calls < 3) return Promise.reject(new Error("ECONNREFUSED"));
    return Promise.resolve({ json: () => Promise.resolve({ status: "ok" }) });
  });
  const ok = await pollHealth("http://x/health", {
    maxAttempts: 5,
    fetchFn,
    delayFn: () => Promise.resolve(),
  });
  expect(ok).toBe(true);
  expect(calls).toBe(3);
});

test("pollHealth 重试耗尽后返回失败", async () => {
  const fetchFn = jest.fn(() => Promise.reject(new Error("ECONNREFUSED")));
  const ok = await pollHealth("http://x/health", {
    maxAttempts: 4,
    fetchFn,
    delayFn: () => Promise.resolve(),
  });
  expect(ok).toBe(false);
  expect(fetchFn).toHaveBeenCalledTimes(4);
});
