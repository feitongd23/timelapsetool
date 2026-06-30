// Copyright (c) 2026 杜非同. All rights reserved.
// Part of Timelapse Tool — proprietary software.
// Unauthorized copying, modification, or distribution is prohibited.

const { contextBridge, ipcRenderer } = require("electron");

// 把后端地址暴露给渲染进程，避免渲染进程硬编码
contextBridge.exposeInMainWorld("backend", {
  httpBase: "http://127.0.0.1:8756",
  wsUrl: "ws://127.0.0.1:8756/ws",
});

// 暴露原生文件夹选择对话框
contextBridge.exposeInMainWorld("api", {
  chooseDirectory: () => ipcRenderer.invoke("choose-directory"),
  chooseFile: () => ipcRenderer.invoke("choose-file"),
});
