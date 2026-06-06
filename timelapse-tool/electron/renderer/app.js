function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("active", p.id === name);
  });
}

function statusLabel(healthy) {
  return healthy ? "后端已连接" : "后端连接失败";
}

// 轮询健康检查直到后端就绪：后端由 Electron 启动，可能比窗口加载慢，
// 单次请求会输在竞速上。重试 maxAttempts 次、每次间隔 intervalMs。
// 依赖（fetchFn / delayFn）可注入以便测试。
async function pollHealth(url, { maxAttempts = 20, intervalMs = 500, fetchFn = fetch, delayFn } = {}) {
  const wait = delayFn || ((ms) => new Promise((r) => setTimeout(r, ms)));
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const res = await fetchFn(url);
      const data = await res.json();
      if (data.status === "ok") return true;
    } catch (_) {
      // 后端还没起来，继续重试
    }
    if (attempt < maxAttempts - 1) await wait(intervalMs);
  }
  return false;
}

// 浏览器环境下绑定交互；测试环境（无 window.backend）跳过
if (typeof window !== "undefined" && window.backend) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  const statusEl = document.getElementById("conn-status");
  pollHealth(window.backend.httpBase + "/health").then((ok) => {
    statusEl.textContent = statusLabel(ok);
    statusEl.className = "status " + (ok ? "ok" : "err");
    if (ok) {
      const ws = new WebSocket(window.backend.wsUrl);
      ws.onopen = () => ws.send(JSON.stringify({ type: "ping" }));
      // 确认后端就绪后再加载相机列表，避免与后端启动竞速
      if (typeof window.initPipeline === "function") {
        window.initPipeline(window.backend.httpBase);
      }
      if (typeof window.initSocialTab === "function") {
        window.initSocialTab(window.backend.httpBase);
      }
    }
  });
}

if (typeof module !== "undefined") {
  module.exports = { switchTab, statusLabel, pollHealth };
}
