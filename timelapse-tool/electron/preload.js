const { contextBridge } = require("electron");

// 把后端地址暴露给渲染进程，避免渲染进程硬编码
contextBridge.exposeInMainWorld("backend", {
  httpBase: "http://127.0.0.1:8756",
  wsUrl: "ws://127.0.0.1:8756/ws",
});
