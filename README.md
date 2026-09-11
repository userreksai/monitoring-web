# 短信计费监控前端

这是短信计费监控管理平台的 Vue 3 + Vite 前端，包含登录、告警业务、告警设置和告警记录页面。前端通过 `/api` 调用独立的 Go 后端服务：

- 前端仓库：<https://github.com/userreksai/monitoring-web>
- 后端仓库：<https://github.com/userreksai/monitoring-service>

## 本地开发

环境要求：Node.js 20.19+、pnpm 11.19.0。

```bash
pnpm install --frozen-lockfile
pnpm run dev
```

访问 <http://localhost:8900>。Vite 开发服务器会将 `/api` 请求代理到默认后端地址 <http://127.0.0.1:8901>，因此需要同时启动 `monitoring-service`。

## 生产运行

先构建 Vue，再由 `server.mjs` 托管 `dist` 静态文件，并把 `/api` 反向代理到后端：

```bash
pnpm install --frozen-lockfile
pnpm run build
PORT=8900 API_BASE_URL=http://127.0.0.1:8901 node server.mjs
```

可配置环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8900` | 前端 HTTP 服务端口 |
| `API_BASE_URL` | `http://127.0.0.1:8901` | 独立后端服务地址 |

## Ubuntu 24.04 LTS 部署

先部署并启动 `monitoring-service`，确保后端端口可以从前端服务器访问。随后首次安装或更新前端均可执行：

```bash
curl -fsSL https://raw.githubusercontent.com/userreksai/monitoring-web/main/deploy/install.sh -o /tmp/monitoring-web-install.sh
sudo bash /tmp/monitoring-web-install.sh
```

脚本会：

- 拉取或快进更新 GitHub `main` 分支到 `/opt/monitoring-web`；
- 安装 Node.js 与固定版本的 pnpm，执行依赖安装和 Vue 构建；
- 首次创建 `/opt/monitoring-web/.env`；
- 初始化、启用并重启 `monitoring-web.service`；
- 通过 `server.mjs` 在 `8900` 端口提供页面，并代理 `/api`。

首次部署到其他后端地址时，可直接传入配置：

```bash
sudo API_BASE_URL=http://127.0.0.1:8901 \
  PORT=8900 bash /tmp/monitoring-web-install.sh
```

脚本更新代码时会保留已有 `.env`。如需后续修改代理目标：

```bash
sudoedit /opt/monitoring-web/.env
sudo systemctl restart monitoring-web
```

常用维护命令：

```bash
sudo systemctl status monitoring-web
sudo systemctl restart monitoring-web
sudo journalctl -u monitoring-web -f
```

也可以覆盖仓库、分支和安装目录：

```bash
sudo REPO_URL=https://github.com/userreksai/monitoring-web.git \
  BRANCH=main APP_DIR=/opt/monitoring-web \
  bash /tmp/monitoring-web-install.sh
```
