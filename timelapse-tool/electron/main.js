const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

// 渲染进程请求选择文件夹 → 打开系统目录选择框，返回选中路径（取消返回 null）
ipcMain.handle("choose-directory", async () => {
  const result = await dialog.showOpenDialog({ properties: ["openDirectory", "createDirectory"] });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

let pyProc = null;

function startBackend() {
  const pythonBin = path.join(__dirname, "..", "python", ".venv", "bin", "python");
  const serverScript = path.join(__dirname, "..", "python", "server.py");
  pyProc = spawn(pythonBin, [serverScript], { stdio: "inherit" });
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
