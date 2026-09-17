# Grafana 短信余额监控（MySQL 版）

Python 3.10+，依赖见 `requirements-monitor.txt`。服务目录：`/opt/monitoring-alert`。

**从旧 SQLite 版本升级，请先阅读 `MYSQL_UPGRADE.md`，同时升级后端并迁移旧数据。不能只替换脚本。**

## 启动

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-monitor.txt
# 首次运行才复制模板，不要覆盖已填写的 monitor.env
cp -n monitor.env.example monitor.env
# 填好 Grafana、告警中心、Lark、MYSQL_* 后，只读验证
.venv/bin/python grafana_balance_monitor.py --dry-run
# 运行一轮，实际通知和写入
.venv/bin/python grafana_balance_monitor.py --once
# 常驻，五分钟一次
.venv/bin/python grafana_balance_monitor.py
```

生产服务：`bash deploy/install-monitor-service.sh /opt/monitoring-alert root`。日志：`journalctl -u grafana-balance-monitor -f -o cat`。修改配置后 `systemctl restart grafana-balance-monitor`。

## 行为

- 每五分钟查询 dashboard `ad6mjfp` 中标题为“全部”的面板，查询最近六小时，各账号取最新有效非空样本；零余额有效。
- 余额四小时不变不算失败。超过 `MAX_SAMPLE_AGE_SECONDS` 的样本、缺失账号、无时间戳、NaN、查询或网络失败向 Lark 通知。
- 按 `account_name` 与告警中心 `account` 精确匹配，默认业务编码 `534784`。每轮刷新业务和规则，读取最新阈值及通知开关。内置原清单 28 个账号做完整性检查，中心新增启用规则也检查缺失数据。
- 余额严格小于阈值才触发，同时尊重业务和规则通知开关。未启用浮动百分比告警。
- 首次低余额立即通知并排队创建“待处理”告警记录；同规则在防抖跨度内不重复产生事件。到期仍低余额时再次告警。异常通知有独立五分钟间隔。
- MySQL `monitor_cooldown` 和 `monitor_outbox` 保存防抖及补发状态，重启不丢失。Lark、中心记录分别标记成功，只补发失败的一端。已排队事件即使后来余额恢复仍补发历史事件。
- MySQL 命名锁限制同库同业务单实例；连接断开后退出，由 systemd 重启。没有活动 SQLite 数据库。发现未导入的旧状态文件时会阻止启动，避免突然重复告警。
- 中心记录通过唯一 `event_id` 保证重复提交不新增记录。Lark 不提供幂等接口，响应丢失后的补发可能重复，可按消息事件 ID 识别。
- 采集/规则读取失败只发 Lark，不伪造规则编码写入中心；低余额事件同时投递 Lark 与中心。

数据样本时间不一定等于供应商业务更新时间。如果 exporter 不断重新打抓取时间戳，需要额外上游更新时间指标才能判断四小时任务是否停更。

## 特殊 Grafana 面板

默认支持 account_name label 的 Grafana DataFrame 时间序列、以及 account_name + Time + 单一数字余额列的表格。若面板有模板变量、计算转换、独立时间范围或特殊插件，默认拒绝猜测查询，明确报告配置错误。

可在 Grafana 面板 Inspect → Query 中取得实际 `/api/ds/query` 请求 body，展开变量、确认余额计算与图表一致后保存到 JSON 文件，设置 `GRAFANA_QUERY_FILE` 为绝对路径。文件至少包含 `{"queries":[...]}`；程序每轮把 `from/to` 更新为最近六小时。前端图表转换不会由查询接口自动执行，需要把等价计算写入查询。前端专用数据源需要按实际 API 适配。

Grafana 地址只填根地址 `https://zy_grafana.v668live.com`，不要填 `/d/...`。部署服务器需要能连接这个内网域名解析出的 IP 和 443 端口。

API 参考：[Grafana 数据源查询](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/data_source/)、[Lark 自定义机器人](https://open.larksuite.com/document/client-docs/bot-v3/add-custom-bot)。

## 测试

```bash
.venv/bin/python -m unittest -v test_grafana_balance_monitor.py test_mysql_migration.py
```

数据库集成测试需设置 `MYSQL_TEST_RUN=1` 及 `MYSQL_TEST_HOST/PORT/USER/PASSWORD`，测试账号需要创建/删除测试库权限。测试只创建删除随机 `monitoring_test_*` 数据库，不会使用生产库。未配置时明确跳过数据库相关测试。
