# vidforge — React + MUI 前端（试验版）

这是跟 `vidforge/ui/static/`（原生 JS 版本）并存的另一套前端，用同一个 Python 后端的 `/api/*`
接口，方便对比两种做法。旧版本不受这个目录影响，照常用。

第一期只做了：左侧导航栏外壳 + 项目切换 + 完整可用的「第1步·脚本」。第2-5步是"即将推出"占位。

## 本地跑起来（开发模式，两个进程）

1. 先启动 Python 后端（跟平时一样，打开你要编辑的项目）：
   ```
   vidforge ui <project目录> --port 8765 --no-browser
   ```
   确认它确实绑定在 8765——如果 8765 被占用，`vidforge` 会自动换一个端口，这种情况下要把
   `vite.config.ts` 里 `server.proxy` 的 target 端口改成实际用的那个。

2. 再启动这个 React 前端：
   ```
   cd vidforge/ui/react
   npm install   # 第一次跑之前
   npm run dev
   ```
   打开 http://127.0.0.1:5175/

开发服务器把 `/api/*` 和 `/files/*` 请求转发给 8765 端口的 Python 后端（`vite.config.ts` 里配的
proxy），所以浏览器全程只跟 5175 同源，不会遇到 CORS 问题，也不用改 Python 后端一行代码。
