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

// 浏览器环境下绑定交互；测试环境（无 window.backend）跳过
if (typeof window !== "undefined" && window.backend) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  const statusEl = document.getElementById("conn-status");
  fetch(window.backend.httpBase + "/health")
    .then((r) => r.json())
    .then((d) => {
      const ok = d.status === "ok";
      statusEl.textContent = statusLabel(ok);
      statusEl.className = "status " + (ok ? "ok" : "err");
    })
    .catch(() => {
      statusEl.textContent = statusLabel(false);
      statusEl.className = "status err";
    });

  const ws = new WebSocket(window.backend.wsUrl);
  ws.onopen = () => ws.send(JSON.stringify({ type: "ping" }));
}

if (typeof module !== "undefined") {
  module.exports = { switchTab, statusLabel };
}
