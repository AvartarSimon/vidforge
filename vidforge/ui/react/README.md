# vidforge 界面（React + MUI）

这是 vidforge 唯一的界面。Python 后端（`vidforge/ui/__init__.py`）只提供 `/api/*` 接口，并把这里
`npm run build` 出来的 `dist/` 送给浏览器。`./install-mac.sh` 和第一次启动都会自动构建一次。

## 改界面时（开发模式，两个进程）

1. 启动 Python 后端，打开要编辑的项目：
   ```
   vidforge ui <project目录> --port 8765 --no-browser
   ```
   如果 8765 被占用，vidforge 会换一个端口，这时把 `vite.config.ts` 里 `server.proxy` 的端口改成实际的。

2. 启动开发服务器：
   ```
   cd vidforge/ui/react
   npm install   # 第一次
   npm run dev
   ```
   打开 http://127.0.0.1:5175/ ，改代码页面会自动刷新。`/api/*`、`/files/*` 由 Vite 转发给后端，没有跨域问题。

3. 改完运行 `npx tsc -b`（类型检查）和 `npm run build`（更新 `dist/`，后端直接用它）。
