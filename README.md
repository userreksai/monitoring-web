# 云告警管理中心前端

按照 Stitch 原型实现的云告警管理中心，包含登录页、告警业务、告警设置和告警记录三张主要数据页面。

## 运行

```bash
npm run dev
```

默认访问地址：<http://localhost:8900>

可通过 `PORT` 环境变量覆盖端口。当前登录页为界面演示，输入任意非空账号和密码即可进入工作台。页面使用与 Stitch 原型一致的演示数据，后续可接入数据库/API。

## Ubuntu 24.04 部署

首次安装或后续更新均执行同一个脚本：

```bash
curl -fsSL https://raw.githubusercontent.com/userreksai/monitoring-web/main/deploy/install.sh -o /tmp/monitoring-web-install.sh
sudo bash /tmp/monitoring-web-install.sh
```

脚本会将代码部署到 `/opt/monitoring-web`，创建 `monitoring-web` 系统用户，初始化并启用 `monitoring-web.service`，监听 `8900` 端口。再次执行会拉取 `main` 分支最新代码并重启服务。

常用维护命令：

```bash
sudo systemctl status monitoring-web
sudo systemctl restart monitoring-web
sudo journalctl -u monitoring-web -f
```

可以使用环境变量覆盖部署参数，例如：

```bash
sudo PORT=8900 BRANCH=main APP_DIR=/opt/monitoring-web bash /tmp/monitoring-web-install.sh
```
