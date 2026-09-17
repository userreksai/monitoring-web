#!/usr/bin/env bash
# 注册当前目录中的监控程序，MySQL 版使用独立 venv。
# sudo bash deploy/install-monitor-service.sh
# sudo bash deploy/install-monitor-service.sh /实际脚本目录 [运行用户]
set -euo pipefail

if [[ "$(id -u)" != 0 ]]; then
  echo '请用 sudo 或 root 执行。' >&2
  exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd -- "${1:-$script_dir/..}" && pwd)"
run_user="${2:-${SUDO_USER:-root}}"
python_bin="$(command -v python3)"

# 这些字符在 systemd 中有替换或转义语义，拒绝以免生成错误的服务命令。
for value in "$app_dir" "$python_bin"; do
  if [[ "$value" == *['%$"\']* || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo '安装路径不能包含 %、$、双引号、反斜线或换行。' >&2
    exit 1
  fi
done
if [[ ! "$run_user" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*\$?$ ]]; then
  echo '运行用户名无效。' >&2
  exit 1
fi
id "$run_user" >/dev/null
"$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "需要 Python 3.10 或以上")'
test -f "$app_dir/grafana_balance_monitor.py"
test -f "$app_dir/requirements-monitor.txt"
if [[ ! -f "$app_dir/monitor.env" ]]; then
  echo "请先创建并填写 $app_dir/monitor.env，再安装服务。" >&2
  exit 1
fi

# 只验证配置语法及必填项，不访问生产或发送测试通知。
cd -- "$app_dir"
"$python_bin" -m venv "$app_dir/.venv"
python_bin="$app_dir/.venv/bin/python"
"$python_bin" -m pip install -r "$app_dir/requirements-monitor.txt"
runuser -u "$run_user" -- env PYTHONDONTWRITEBYTECODE=1 "$python_bin" -c \
  'from pathlib import Path; from grafana_balance_monitor import load_env, Config; load_env(Path("monitor.env")); Config()'

cat > /etc/systemd/system/grafana-balance-monitor.service <<EOF
[Unit]
Description=Grafana SMS balance monitor
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$run_user
WorkingDirectory="$app_dir"
ExecStart="$python_bin" -u "$app_dir/grafana_balance_monitor.py" --env-file "$app_dir/monitor.env"
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Restart=on-failure
RestartSec=15s
TimeoutStopSec=120s
UMask=0077
NoNewPrivileges=true
StandardOutput=journal
StandardError=journal
SyslogIdentifier=grafana-balance-monitor

[Install]
WantedBy=multi-user.target
EOF

systemd-analyze verify /etc/systemd/system/grafana-balance-monitor.service
systemctl daemon-reload
systemctl enable grafana-balance-monitor.service
systemctl restart grafana-balance-monitor.service
systemctl --no-pager --full status grafana-balance-monitor.service
echo '实时日志：sudo journalctl -u grafana-balance-monitor -f -o cat'
