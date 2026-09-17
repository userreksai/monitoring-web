# 将现有告警系统切换到 MySQL

本次交付同时修改 Go 后端与 Python 监控。库名沿用 `sms_billing_monitor`，业务数据沿用 `business`、`business_detail`、`notification_log`、`user_account`。前端 API 字段和地址不变，无需重新部署前端。

从 Git 获取代码时，Python 监控及迁移工具位于 `monitoring-web`，Go 后端位于 `monitoring-service`。完整升级包将后端源码放在子目录中；独立克隆两个仓库时，可以使用 `BACKEND_SOURCE_DIR=/实际/monitoring-service bash deploy/install-mysql-backend.sh /opt/monitoring-service`，也可以直接在后端仓库执行 `bash deploy/install.sh /opt/monitoring-service`。本文的 Python 真实数据库迁移测试读取 `monitoring-service/schema.sql`，运行该测试前需将后端放在此前端仓库的同名子目录。

线上切换必须同时更新后端和脚本。只替换 Python 文件，不能改变告警中心的数据库。本地已通过 MySQL 8.4 实例上的测试；未连接或修改生产数据库。

## 1. 上传、停止写入并备份

将交付包解压到 `/opt/monitoring-alert`。压缩包不包含真实 `monitor.env`、后端 `.env` 或数据库，不会覆盖它们。后端安装目录以下按原部署默认 `/opt/monitoring-service`，原 SQLite 数据按 `/var/lib/monitoring-service/monitoring.db`；**先检查实际 `DB_PATH`，如不同替换下面对应路径**。

```bash
cd /opt/monitoring-alert
grep '^DB_PATH=' /opt/monitoring-service/.env
systemctl stop grafana-balance-monitor
systemctl stop monitoring-service

apt-get update
apt-get install -y python3-venv sqlite3 golang-go

# 创建一次性备份目录，保留配置、程序与 service。
BACKUP_DIR="/opt/monitoring-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$BACKUP_DIR"
cp -p monitor.env "$BACKUP_DIR/monitor.env"
cp -p /opt/monitoring-service/.env "$BACKUP_DIR/backend.env"
cp -p /opt/monitoring-service/bin/monitoring-service "$BACKUP_DIR/backend-binary"
cp -p /etc/systemd/system/monitoring-service.service "$BACKUP_DIR/backend.service"
cp -p /etc/systemd/system/grafana-balance-monitor.service "$BACKUP_DIR/monitor.service"

# 使用 SQLite backup，包含可能仍位于 WAL 中的已提交数据。
test -f /var/lib/monitoring-service/monitoring.db && \
  sqlite3 /var/lib/monitoring-service/monitoring.db ".backup '$BACKUP_DIR/monitoring.db'"
test -f monitor-state.sqlite3 && \
  sqlite3 monitor-state.sqlite3 ".backup '$BACKUP_DIR/monitor-state.sqlite3'"

# 保留 MySQL 原数据备份；输入现有 MySQL 管理员密码。
mysqldump -uroot -p --single-transaction --routines --triggers \
  sms_billing_monitor > "$BACKUP_DIR/sms_billing_monitor.sql"
```

如果后端尚无 SQLite 数据，仅使用已有 MySQL，则跳过旧后端 SQLite 备份/导入。但你列出的脚本状态库 `monitor-state.sqlite3` 仍需迁移。升级前另外保存旧 Python 文件用于回滚（上传新包前保存，或从原交付版本取回）。

## 2. 配置同一个 MySQL 数据库

可使用已有数据库应用账号。若尚无程序账号，在 `mysql -uroot -p` 中执行下列示例，**将密码占位符替换成实际密码**。程序使用 TCP 访问本机 `127.0.0.1:3306`；若数据库在另一台主机，请按实际连接来源创建用户。

```sql
CREATE USER IF NOT EXISTS 'monitoring'@'127.0.0.1'
  IDENTIFIED BY '替换为你设置的数据库密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON sms_billing_monitor.* TO 'monitoring'@'127.0.0.1';
```

在现有 `/opt/monitoring-alert/monitor.env` 和 `/opt/monitoring-service/.env` **分别添加**：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=sms_billing_monitor
MYSQL_USER=monitoring
MYSQL_PASSWORD=你的数据库密码
MYSQL_TIME_ZONE=+08:00
```

不要用模板覆盖已有配置。保留 Grafana、Lark、CENTER_*、后端 JWT_SECRET 及端口。`CENTER_USERNAME/PASSWORD` 仍是告警中心登录账号，不是 MySQL 账号。`MYSQL_TIME_ZONE` 决定新告警时间和“今日统计”的日期边界，按原业务时区设置；示例为北京时间。

旧 `DB_PATH`、`STATE_DB` 不再用作活动数据库。`STATE_DB` 若存在，仅用于识别旧文件，防止未迁移就丢失防抖状态。现有 SQLite 文件保留作备份，不删除。

## 3. 安装 Python 依赖、升级 MySQL 表结构

```bash
cd /opt/monitoring-alert
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-monitor.txt

# 构建/安装新后端并执行 --migrate-only；不会自动启动服务。
bash deploy/install-mysql-backend.sh /opt/monitoring-service
```

安装脚本读取后端 `.env`，不从 GitHub 拉取旧版本。它保留旧二进制备份；连接 MySQL 失败则不切换二进制。若本地不存在后端 `.env`，脚本创建模板并退出，填写后重试。

表结构升级仅创建缺失表、增加页面需要的列、扩展密码/告警内容字段及事件唯一索引，不清空表，不覆盖业务/阈值/账号，不插入示例业务。已有 SHA-256 登录密码仍有效，成功登录时升级为 PBKDF2。原 `alert_silence_seconds` 保持秒单位，页面继续使用 `10m`、`1h`、`1d`；原值 0 表示不抑制告警。

## 4. 先预览，再迁移旧数据

以下命令可以直接读取停止服务后的原文件；若使用备份文件，将路径改为第 1 步的备份路径。

```bash
cd /opt/monitoring-alert
.venv/bin/python migrate_sqlite_to_mysql.py --env-file monitor.env \
  --source-db /var/lib/monitoring-service/monitoring.db \
  --state-db /opt/monitoring-alert/monitor-state.sqlite3
```

默认只读预览，显示新增数量和冲突字段。对于同编码数据不同（例如原 MySQL 初始化示例账号和页面中后来修改的账号），默认不写入任何业务数据。根据实际数据选择一种策略，并先运行预览：

```bash
# 以 MySQL 已有配置为准；仅补充不存在的业务、规则、用户。
.venv/bin/python migrate_sqlite_to_mysql.py --env-file monitor.env \
  --source-db /var/lib/monitoring-service/monitoring.db \
  --state-db /opt/monitoring-alert/monitor-state.sqlite3 --prefer mysql

# 或：以旧告警中心 SQLite 的现有页面配置为准（也覆盖同名用户密码摘要）。
.venv/bin/python migrate_sqlite_to_mysql.py --env-file monitor.env \
  --source-db /var/lib/monitoring-service/monitoring.db \
  --state-db /opt/monitoring-alert/monitor-state.sqlite3 --prefer sqlite
```

确认预览后，给所选命令追加 `--apply` 才真正迁移。若没有冲突，原默认命令直接追加 `--apply` 即可。如果你当前 29 条规则保存在 SQLite，而 MySQL 仍是早期初始化数据，应核对冲突后选择 SQLite 配置；工具不会替你猜。

若后端没有要迁移的 SQLite，只迁移脚本状态：

```bash
.venv/bin/python migrate_sqlite_to_mysql.py --env-file monitor.env \
  --state-db /opt/monitoring-alert/monitor-state.sqlite3 --apply
```

数据写入为单个 MySQL 事务，任何插入失败整批回滚；用于记录迁移的辅助表 DDL 独立执行，失败最多留下空辅助表。旧 SQLite 文件只读打开。再次执行保持相同 `--source-id`，历史记录通过迁移台账去重；队列事件 ID 和单端投递状态保留，防抖时间取较新值。数字主键遇到已有 MySQL 数据时不会硬覆盖，业务关联使用原业务编码/规则编码。

迁移期间保持两个服务停止，不要在网页或数据库中修改业务数据。`--prefer` 是本次全局冲突策略，如果不同记录要不同处理，应先人工核对并调整数据后再运行默认策略。

## 5. 切换服务并核对

```bash
systemctl restart monitoring-service
curl -fsS http://127.0.0.1:8901/api/health
# 应返回 "database":"mysql"

cd /opt/monitoring-alert
.venv/bin/python grafana_balance_monitor.py --dry-run

# 注册新的 venv Python 路径、开启开机启动并运行监控。
bash deploy/install-monitor-service.sh /opt/monitoring-alert root

systemctl status monitoring-service grafana-balance-monitor --no-pager -l
journalctl -u monitoring-service -n 50 --no-pager -o cat
journalctl -u grafana-balance-monitor -f -o cat
```

`--dry-run` 不发送通知，也不写告警记录或状态，但需要 API、Grafana 真实可访问。此前 `172.21.0.238:443` 超时属于内网连通性问题，切换 MySQL 不会解决该网络问题；需要单独打通。

登录页面核对业务、账号、阈值、通知开关、防抖跨度以及历史记录。也可在 MySQL 中查看：

```sql
USE sms_billing_monitor;
SELECT COUNT(*) FROM business_detail;
SELECT detail_code,account,balance_threshold,alert_silence_seconds,notify_enabled
FROM business_detail WHERE business_code='534784';
SELECT id,detail_code,alert_type,alert_value,status,alert_time
FROM notification_log ORDER BY id DESC LIMIT 10;
SELECT scope,COUNT(*) FROM monitor_cooldown GROUP BY scope;
SELECT id,lark_done,record_done FROM monitor_outbox ORDER BY created DESC LIMIT 10;
```

## 当前存储结构与投递语义

| 表 | 用途 |
|---|---|
| `business` | 原业务表 |
| `business_detail` | 原规则、账号、阈值、防抖秒数 |
| `notification_log` | 原告警记录表，补充类型、值、状态、事件 ID |
| `user_account` | 原登录表，兼容旧密码 |
| `monitor_cooldown` | 按业务/规则持久化防抖时间 |
| `monitor_outbox` | Lark 与中心记录的独立投递队列 |
| `monitor_state_imports` | 旧脚本状态已迁移标记 |
| `sqlite_import_log` | 旧中心历史记录导入台账 |

监控通过中心 API 获取业务规则和创建记录，通过 MySQL 直接保存状态。中心记录增加唯一 `event_id`，重复提交同一事件只产生一条记录；Lark Webhook 本身不支持幂等，若发出后响应丢失，补发仍可能在群里重复，事件 ID 可识别。单实例锁改用 MySQL GET_LOCK，同一数据库同一业务跨机器也不会并行投递；数据库连接丢失会停止当前进程，由 systemd 拉起后重新取得锁。

保留原外键 `ON DELETE RESTRICT`：已有记录的规则、已有规则的业务不能直接删除，接口返回冲突，避免删除配置时连带丢失历史。

如需回滚，先停止两个新服务，恢复旧 Python、原二进制和两个 service/config 备份，重新加载 systemd 后启用旧服务。旧 SQLite 文件仍在；切换到 MySQL 后新产生的数据不会自动回写 SQLite，回滚前需要另行核对这些增量。不要直接恢复 MySQL 全库备份覆盖上线后数据。
