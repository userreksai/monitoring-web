#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/userreksai/monitoring-web.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/monitoring-web}"
SERVICE_NAME="${SERVICE_NAME:-monitoring-web}"
SERVICE_USER="${SERVICE_USER:-monitoring-web}"
PORT="${PORT:-8900}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log() {
  printf '[monitoring-web] %s\n' "$*"
}

fail() {
  printf '[monitoring-web] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "请使用 root 用户运行，或执行：sudo bash $0"
fi

if [[ ! -f /etc/os-release ]]; then
  fail "无法识别当前 Linux 系统"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  fail "当前系统不是 Ubuntu（检测到 ${ID:-unknown}）"
fi

log "安装运行依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git nodejs

NODE_MAJOR="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
if [[ -z "${NODE_MAJOR}" || "${NODE_MAJOR}" -lt 18 ]]; then
  fail "需要 Node.js 18 或更高版本，当前版本：$(node --version 2>/dev/null || echo 未安装)"
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  log "创建系统用户 ${SERVICE_USER}"
  useradd --system --user-group --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  log "更新 ${BRANCH} 分支代码"
  git -C "${APP_DIR}" remote set-url origin "${REPO_URL}"
  git -C "${APP_DIR}" fetch --prune origin "${BRANCH}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
elif [[ -e "${APP_DIR}" ]] && [[ -n "$(find "${APP_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  fail "安装目录已存在且不是空 Git 仓库：${APP_DIR}"
else
  log "克隆代码到 ${APP_DIR}"
  mkdir -p "$(dirname "${APP_DIR}")"
  git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${APP_DIR}"
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

log "写入 systemd 服务 ${SERVICE_NAME}"
cat >"${UNIT_FILE}" <<EOF
[Unit]
Description=Cloud Alert Management Web
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment=NODE_ENV=production
Environment=PORT=${PORT}
ExecStart=/usr/bin/node ${APP_DIR}/server.mjs
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "${UNIT_FILE}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

log "等待服务启动"
for _ in {1..15}; do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:${PORT}/" >/dev/null; then
    log "部署完成：http://服务器IP:${PORT}"
    systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,8p'
    exit 0
  fi
  sleep 1
done

systemctl --no-pager --full status "${SERVICE_NAME}" || true
journalctl -u "${SERVICE_NAME}" -n 30 --no-pager || true
fail "服务未能在端口 ${PORT} 正常响应"
