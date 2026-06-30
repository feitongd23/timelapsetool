// Copyright (c) 2026 杜非同. All rights reserved.
// Part of Timelapse Tool — proprietary software.
// Unauthorized copying, modification, or distribution is prohibited.

const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

// 渲染进程请求选择文件夹 → 打开系统目录选择框，返回选中路径（取消返回 null）
ipcMain.handle("choose-directory", async () => {
  const result = await dialog.showOpenDialog({ properties: ["openDirectory", "createDirectory"] });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

// 渲染进程请求选择单个视频文件（成片转社媒）
ipcMain.handle("choose-file", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openFile"],
    filters: [{ name: "视频", extensions: ["mov", "mp4", "m4v"] }],
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

let pyProc = null;

function startBackend() {
  if (app.isPackaged) {
    // 打包态：spawn 随包的 PyInstaller 可执行；TLT_RESOURCES 让后端找到预编译 Swift 二进制
    const res = process.resourcesPath; // .app/Contents/Resources
    // onedir 打包：可执行在 Resources/server/server（同目录有 _internal/），不再每次解压，冷启动快
    pyProc = spawn(path.join(res, "server", "server"), [], {
      stdio: "inherit",
      env: { ...process.env, TLT_RESOURCES: res },
    });
  } else {
    const pythonBin = path.join(__dirname, "..", "python", ".venv", "bin", "python");
    const serverScript = path.join(__dirname, "..", "python", "server.py");
    pyProc = spawn(pythonBin, [serverScript], { stdio: "inherit" });
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (pyProc) pyProc.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("quit", () => {
  if (pyProc) pyProc.kill();
});
