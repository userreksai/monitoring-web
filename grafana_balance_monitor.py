#!/usr/bin/env python3
"""Grafana 余额 -> monitoring-service -> Lark，Python 3.10+，MySQL 持久化。"""
from __future__ import annotations

import argparse
import base64
import copy
import errno
import hashlib
import hmac
import http.cookiejar
import json
import logging
import math
import os
import re
import signal
import socket
import ssl
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

LOG = logging.getLogger("balance-monitor")
EXPECTED_ACCOUNTS = """cxSMS_vty_NgwMXO
云通讯_aty_vnghGN
云通讯_bty_azLQ9x
云通讯_bty_uzv9zy
云通讯_pay_JYefDD
云通讯_pay_ZvGwdL
云通讯_vty_3hNhVd
云通讯_vty_QN7QKA
云通讯_vty_wJfeyA
挖数据_bty_19033517632_手机运营商二要素
挖数据_bty_19033517632_用户系统接口
挖数据_bty_19033517632_银行卡二三四要素验证
挖数据_bty_19033517632_银行卡归属地
挖数据_pay_13644454058_手机运营商三要素
挖数据_pay_13644454058_手机运营商二要素
挖数据_pay_13644454058_用户系统接口
挖数据_pay_13644454058_银行卡二三四要素验证
挖数据_vty_15251195642_备案号查询
挖数据_vty_15251195642_手机运营商三要素
挖数据_vty_15251195642_手机运营商二要素
挖数据_vty_15251195642_用户系统接口
挖数据_vty_15251195642_身份证二要素实名认证
挖数据_vty_15251195642_银行卡二三四要素验证
赛邮云_bty_jordan85637@outlook.com
赛邮云_vty_vtyuat2014@outlook.com
飞鸽_bty_13714842254
飞鸽_vty_GJYN
麦讯通_bty_MXT801615_5348753754""".splitlines()


class MonitorError(Exception):
    pass


class APIError(MonitorError):
    def __init__(self, service, status):
        self.status = status
        super().__init__(f"{service} 请求失败（HTTP {status}）")


def number(value):
    if value is None or isinstance(value, bool):
        raise MonitorError("余额或阈值为空/非数字")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise MonitorError("余额或阈值不是有效数字") from exc
    if not result.is_finite():
        raise MonitorError("余额或阈值为 NaN/Infinity")
    return result


def duration(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([mhd])", value.strip().lower())
    if not match or float(match[1]) < 0:
        raise MonitorError("规则防抖时间无效")
    return float(match[1]) * {"m": 60, "h": 3600, "d": 86400}[match[2]]


def load_env(path):
    """简单 KEY=value 文件，不执行 shell、不展开变量。已有环境变量优先。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise MonitorError("配置文件格式错误，应为 KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


class Config:
    def __init__(self):
        self.grafana = os.getenv("GRAFANA_URL", "").rstrip("/")
        self.center = os.getenv("CENTER_URL", "").rstrip("/")
        self.webhook = os.getenv("LARK_WEBHOOK", "")
        self.secret = os.getenv("LARK_SECRET", "")
        self.guser = os.getenv("GRAFANA_USERNAME", "dev-api")
        self.gpassword = os.getenv("GRAFANA_PASSWORD", "")
        self.gtoken = os.getenv("GRAFANA_TOKEN", "")
        self.cuser = os.getenv("CENTER_USERNAME", "")
        self.cpassword = os.getenv("CENTER_PASSWORD", "")
        self.uid = os.getenv("DASHBOARD_UID", "ad6mjfp")
        self.panel = os.getenv("PANEL_TITLE", "全部")
        self.org = os.getenv("GRAFANA_ORG_ID", "1")
        self.business = os.getenv("BUSINESS_CODE", "534784")
        self.interval = int(os.getenv("POLL_SECONDS", "300"))
        self.max_age = int(os.getenv("MAX_SAMPLE_AGE_SECONDS", "21600"))
        self.timeout = int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
        self.query_file = os.getenv("GRAFANA_QUERY_FILE", "")
        self.scope = hashlib.sha256((os.getenv("MYSQL_DATABASE", "sms_billing_monitor") + ":" + self.business).encode()).hexdigest()[:32]
        for name, value in [("GRAFANA_URL", self.grafana), ("CENTER_URL", self.center)]:
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
                raise MonitorError(f"请配置 {name} 的完整服务地址（不含 /d/... 或 /api）")
        hook = urlsplit(self.webhook)
        if hook.scheme != "https" or hook.hostname != "open.larksuite.com" or not re.fullmatch(r"/open-apis/bot/v2/hook/[A-Za-z0-9-]+", hook.path):
            raise MonitorError("请配置完整 LARK_WEBHOOK，包含 /hook/ 后的机器人 ID")
        if not self.gtoken and not (self.guser and self.gpassword):
            raise MonitorError("请配置 GRAFANA_PASSWORD 或 GRAFANA_TOKEN")
        if not self.cuser or not self.cpassword:
            raise MonitorError("请配置 CENTER_USERNAME 和 CENTER_PASSWORD")
        if not os.getenv("MYSQL_USER") or not os.getenv("MYSQL_PASSWORD"):
            raise MonitorError("请配置 MYSQL_USER 和 MYSQL_PASSWORD；不再使用 SQLite 状态库")
        if min(self.interval, self.max_age, self.timeout) <= 0:
            raise MonitorError("轮询、超时和样本有效期必须大于零")


class HTTP:
    def __init__(self, name, base, timeout):
        self.name, self.base, self.timeout = name, base, timeout
        self.headers = {"Accept": "application/json"}
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method, path="", body=None):
        headers = dict(self.headers)
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                # 登录重定向不应被当作成功；也不输出可能包含凭据的 URL/响应正文。
                if response.geturl() != req.full_url:
                    raise MonitorError(f"{self.name} 返回重定向，请检查地址/登录状态")
                return json.load(response)
        except HTTPError as exc:
            raise APIError(self.name, exc.code) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if isinstance(reason, socket.gaierror):
                detail = "DNS 解析失败，请检查服务器内网 DNS/域名解析"
            elif isinstance(reason, ssl.SSLCertVerificationError):
                detail = "TLS 证书验证失败，请检查证书信任链、域名匹配及系统时间"
            elif isinstance(reason, ssl.SSLError):
                detail = "TLS 握手失败，请检查 HTTPS 协议、代理及服务端 TLS 配置"
            elif isinstance(reason, TimeoutError):
                detail = f"连接或响应超时（超时设置 {self.timeout} 秒），请检查路由、防火墙或服务响应"
            elif isinstance(reason, ConnectionRefusedError):
                detail = "连接被拒绝，请检查目标端口是否监听"
            elif isinstance(reason, OSError) and reason.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
                detail = "目标网络/主机不可达，请检查内网路由或 VPN"
            elif isinstance(reason, ConnectionResetError):
                detail = "连接被重置，请检查服务端或中间代理"
            else:
                detail = "网络连接失败（" + type(reason).__name__ + "）"
            # 仅显示受控的阶段名称，不输出带 webhook、凭据的 URL/底层异常正文。
            stage = ("登录" if path == "/login" else "读取面板" if path.startswith("/api/dashboards/")
                     else "查询余额" if path == "/api/ds/query" else "请求")
            raise MonitorError(f"{self.name} {stage}失败：{detail}") from None
        except (ValueError, UnicodeError):
            raise MonitorError(f"{self.name} 未返回有效 JSON") from None


class Center:
    def __init__(self, config):
        self.config = config
        self.http = HTTP("告警中心", config.center, config.timeout)

    def login(self):
        result = self.http.request("POST", "/api/auth/login", {
            "username": self.config.cuser, "password": self.config.cpassword})
        self.http.headers["Authorization"] = "Bearer " + result["token"]

    def request(self, method, path, body=None):
        if "Authorization" not in self.http.headers:
            self.login()
        try:
            return self.http.request(method, path, body)
        except APIError as exc:
            if exc.status != 401:
                raise
            self.login()
            return self.http.request(method, path, body)

    def rules(self):
        businesses = self.request("GET", "/api/businesses")
        business = next((b for b in businesses if b["code"] == self.config.business), None)
        if business is None:
            raise MonitorError("告警中心不存在指定 BUSINESS_CODE")
        rules = self.request("GET", "/api/rules")
        return [dict(r, enabled=bool(r["enabled"] and business["enabled"]))
                for r in rules if r["parent"] == self.config.business]

    def record(self, payload, event_id):
        # 写入响应丢失后用事件标识查重。后端没有幂等键接口，只支持单实例。
        records = self.request("GET", "/api/records?" + urlencode({"q": payload["code"]}))
        marker = f"[event:{event_id}]"
        if any(marker in r.get("detail", "") for r in records):
            return
        self.request("POST", "/api/records", dict(payload, eventId=event_id, detail=payload["detail"] + "\n" + marker))


def panels(items):
    for item in items:
        yield item
        yield from panels(item.get("panels", []))


def parse_frames(response, now, max_age):
    """支持带 account_name label 的时间序列和 account_name/Time/Value 表格。"""
    results = response.get("results")
    if not isinstance(results, dict) or not results:
        raise MonitorError("Grafana 查询无 results")
    samples = {}
    problems = []
    invalid_accounts = set()
    for result in results.values():
        if result.get("error") or int(result.get("status", 200)) >= 400:
            problems.append("Grafana 子查询失败")
            continue
        for frame in result.get("frames", []):
            fields = frame.get("schema", {}).get("fields", [])
            values = frame.get("data", {}).get("values", [])
            if len(fields) != len(values) or len({len(v) for v in values}) > 1:
                problems.append("Grafana frame 列长度不一致")
                continue
            time_col = next((i for i, f in enumerate(fields) if f.get("type") == "time"), None)
            account_col = next((i for i, f in enumerate(fields) if f.get("name") == "account_name"), None)
            numeric = [i for i, f in enumerate(fields) if f.get("type") == "number"]
            if account_col is not None and len(numeric) != 1:
                problems.append("表格余额列不唯一，请在查询中只返回一个余额列")
                continue
            for i in numeric:
                label = fields[i].get("labels", {}).get("account_name")
                if not label and account_col is None:
                    problems.append("余额字段缺少 account_name 标签")
                    continue
                for row, raw in enumerate(values[i]):
                    if raw is None:  # lastNotNull：零是有效余额。
                        continue
                    name = str(values[account_col][row] if account_col is not None else label)
                    try:
                        value = number(raw)
                        if time_col is None:
                            raise MonitorError("缺少样本时间，无法判断数据是否过期")
                        stamp = float(values[time_col][row]) / 1000
                        if not math.isfinite(stamp) or stamp > now + 300:
                            raise MonitorError("样本时间无效或位于未来")
                    except (MonitorError, TypeError, ValueError) as exc:
                        invalid_accounts.add(name)
                        problems.append(f"{name}: {str(exc) if isinstance(exc, MonitorError) else '样本时间无效'}")
                        continue
                    previous = samples.get(name)
                    if previous and stamp == previous[1] and value != previous[0]:
                        invalid_accounts.add(name)
                        problems.append(f"{name}: 同时间存在多个不同余额")
                    if previous is None or stamp > previous[1]:
                        samples[name] = (value, stamp)
    for name, (_, stamp) in list(samples.items()):
        if name in invalid_accounts:
            del samples[name]
        elif now - stamp > max_age:
            del samples[name]
            problems.append(f"{name}: 最后样本超过有效期")
    return samples, sorted(set(problems))


class Grafana:
    def __init__(self, config):
        self.config = config
        self.http = HTTP("Grafana", config.grafana, config.timeout)
        self.http.headers["X-Grafana-Org-Id"] = config.org
        if config.gtoken:
            self.http.headers["Authorization"] = "Bearer " + config.gtoken
        self.logged_in = bool(config.gtoken)

    def request(self, method, path, body=None):
        if not self.logged_in:
            self.http.request("POST", "/login", {"user": self.config.guser, "password": self.config.gpassword})
            self.logged_in = True
        try:
            return self.http.request(method, path, body)
        except APIError as exc:
            if exc.status != 401 or self.config.gtoken:
                raise
            self.logged_in = False
            self.http.request("POST", "/login", {"user": self.config.guser, "password": self.config.gpassword})
            self.logged_in = True
            return self.http.request(method, path, body)

    def collect(self):
        dashboard = self.request("GET", "/api/dashboards/uid/" + quote(self.config.uid, safe=""))["dashboard"]
        matches = [p for p in panels(dashboard.get("panels", [])) if p.get("title") == self.config.panel]
        if len(matches) != 1:
            raise MonitorError("无法唯一定位标题为“全部”的面板，请检查 PANEL_TITLE")
        panel = matches[0]
        if self.config.query_file:
            body = json.loads(Path(self.config.query_file).read_text(encoding="utf-8-sig"))
        else:
            # 这些转换只调整展示结构；计算/过滤类转换必须人工核对查询。
            if any(t.get("id") not in {"organize", "labelsToFields", "merge", "sortBy"}
                   for t in panel.get("transformations", []) if not t.get("disabled")):
                raise MonitorError("面板包含转换，请提供已核对的 GRAFANA_QUERY_FILE 查询")
            if panel.get("timeShift") or panel.get("timeFrom"):
                raise MonitorError("面板存在独立时间范围，请提供 GRAFANA_QUERY_FILE")
            targets = [copy.deepcopy(t) for t in panel.get("targets", []) if not t.get("hide")]
            for target in targets:
                ds = target.get("datasource") or panel.get("datasource")
                if isinstance(ds, str) and "$" not in ds:
                    ds = self.request("GET", "/api/datasources/name/" + quote(ds, safe=""))
                    ds = {"uid": ds["uid"], "type": ds["type"]}
                if not isinstance(ds, dict) or not ds.get("uid") or ds["uid"] == "-- Mixed --":
                    raise MonitorError("数据源未明确指定，请提供 GRAFANA_QUERY_FILE")
                target["datasource"] = ds
                target.setdefault("intervalMs", 60000)
                target.setdefault("maxDataPoints", 1000)
                if re.search(r"\$(?:[A-Za-z_]|\{)", json.dumps(target)):
                    raise MonitorError("查询包含模板变量，请从 Query inspector 导出已展开的 GRAFANA_QUERY_FILE")
            body = {"queries": targets}
        if not body.get("queries"):
            raise MonitorError("全部面板无可执行查询")
        # 每次更新查询窗口；原始业务余额四小时更新不影响五分钟采集。
        now = time.time()
        body["from"], body["to"] = str(int((now - 21600) * 1000)), str(int(now * 1000))
        response = self.request("POST", "/api/ds/query", body)
        return parse_frames(response, now, self.config.max_age)


class Lark:
    def __init__(self, config):
        self.http = HTTP("Lark", config.webhook, config.timeout)
        self.secret = config.secret

    def send(self, text):
        payload = {"msg_type": "text", "content": {"text": text}}
        if self.secret:
            stamp = str(int(time.time()))
            key = (stamp + "\n" + self.secret).encode()
            payload.update(timestamp=stamp, sign=base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode())
        result = self.http.request("POST", body=payload)
        code = result.get("code", result.get("StatusCode"))
        if code != 0:
            raise MonitorError(f"Lark 拒绝通知（业务状态码 {code}）")


def mysql_connect():
    try:
        import pymysql
    except ImportError:
        raise MonitorError("缺少 MySQL 驱动，请执行 python3 -m pip install -r requirements-monitor.txt") from None
    options = dict(host=os.getenv("MYSQL_HOST", "127.0.0.1"),
                   port=int(os.getenv("MYSQL_PORT", "3306")), user=os.getenv("MYSQL_USER", ""),
                   password=os.getenv("MYSQL_PASSWORD", ""),
                   database=os.getenv("MYSQL_DATABASE", "sms_billing_monitor"),
                   charset="utf8mb4", autocommit=True, connect_timeout=10,
                   read_timeout=30, write_timeout=30)
    ca = os.getenv("MYSQL_SSL_CA", "")
    if ca:
        options.update(ssl_ca=ca, ssl_verify_cert=True, ssl_verify_identity=True)
    connection = pymysql.connect(**options)
    try:
        with connection.cursor() as cur:
            cur.execute("SET time_zone=%s", (os.getenv("MYSQL_TIME_ZONE", "+08:00"),))
    except Exception:
        connection.close()
        raise
    return connection


class Store:
    """MySQL 防抖/补发队列，使用连接级命名锁防止多实例重复通知。"""
    def __init__(self, scope):
        self.scope = scope
        self.db = mysql_connect()
        self.lock_name = "balance-monitor:" + scope
        try:
            if self.query("SELECT GET_LOCK(%s,0)", (self.lock_name,))[0][0] != 1:
                raise MonitorError("已有监控实例使用这个 MySQL 库和业务")
            self.prepare(self.db)
            legacy = Path(os.getenv("STATE_DB", str(Path(__file__).with_name("monitor-state.sqlite3"))))
            if legacy.exists() and not self.query("SELECT 1 FROM monitor_state_imports WHERE scope=%s", (scope,)):
                raise MonitorError("发现旧 SQLite 状态库但尚未迁移，请先运行 migrate_sqlite_to_mysql.py --state-db ... --apply")
        except Exception:
            self.db.close()
            raise

    @staticmethod
    def prepare(db):
        with db.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS monitor_state_imports (
                scope CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
                imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB""")
            cur.execute("""CREATE TABLE IF NOT EXISTS monitor_cooldown (
                scope CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                last_event_at DOUBLE NOT NULL, PRIMARY KEY(scope,key_hash)
            ) ENGINE=InnoDB""")
            cur.execute("""CREATE TABLE IF NOT EXISTS monitor_outbox (
                id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
                scope CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                event_key TEXT NOT NULL, body MEDIUMTEXT NOT NULL, record_json MEDIUMTEXT,
                lark_done BOOLEAN NOT NULL DEFAULT FALSE,
                record_done BOOLEAN NOT NULL DEFAULT FALSE, created DOUBLE NOT NULL,
                KEY idx_outbox_pending(scope,key_hash,lark_done,record_done)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin""")

    def query(self, sql, params=()):
        with self.db.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def check_lock(self):
        # 不自动重连：重连会失去命名锁，继续投递可能与另一实例竞争。
        self.db.ping(reconnect=False)
        if self.query("SELECT IS_USED_LOCK(%s)=CONNECTION_ID()", (self.lock_name,))[0][0] != 1:
            raise MonitorError("MySQL 实例锁丢失，停止投递以避免重复告警")

    def enqueue(self, key, text, record, seconds, now=None):
        self.check_lock()
        now = time.time() if now is None else now
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        args = (self.scope, key_hash)
        self.db.begin()
        try:
            old = self.query("SELECT last_event_at FROM monitor_cooldown WHERE scope=%s AND key_hash=%s FOR UPDATE", args)
            pending = self.query("SELECT 1 FROM monitor_outbox WHERE scope=%s AND key_hash=%s AND (lark_done=0 OR record_done=0) LIMIT 1", args)
            if pending or (old and now-old[0][0] < seconds):
                self.db.rollback()
                return False
            event_id = uuid.uuid4().hex
            self.query("""INSERT INTO monitor_outbox
                (id,scope,key_hash,event_key,body,record_json,lark_done,record_done,created)
                VALUES(%s,%s,%s,%s,%s,%s,0,%s,%s)""", (
                    event_id, self.scope, key_hash, key, text+f"\n事件: {event_id}",
                    json.dumps(record, ensure_ascii=False) if record else None, int(record is None), now))
            self.query("""INSERT INTO monitor_cooldown(scope,key_hash,last_event_at) VALUES(%s,%s,%s)
                ON DUPLICATE KEY UPDATE last_event_at=VALUES(last_event_at)""", (*args, now))
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    def flush(self, center, lark):
        self.check_lock()
        ok = True
        rows = self.query("""SELECT id,body,record_json,lark_done,record_done FROM monitor_outbox
            WHERE scope=%s AND (lark_done=0 OR record_done=0) ORDER BY created""", (self.scope,))
        for event_id, body, record, lark_done, record_done in rows:
            for channel, done in (("lark", lark_done), ("record", record_done)):
                if done:
                    continue
                self.check_lock()
                try:
                    if channel == "lark":
                        lark.send(body)
                    else:
                        center.record(json.loads(record), event_id)
                    self.query(f"UPDATE monitor_outbox SET {channel}_done=1 WHERE id=%s AND scope=%s", (event_id, self.scope))
                except Exception as exc:
                    ok = False
                    LOG.error("事件 %s 的 %s 投递失败: %s", event_id, channel, safe_error(exc))
        self.query("DELETE FROM monitor_outbox WHERE scope=%s AND lark_done=1 AND record_done=1 AND created<%s", (self.scope, time.time()-30*86400))
        return ok

    def close(self):
        self.db.close()


def safe_error(exc):
    # 不记录任意底层异常正文，避免 URL 中的 webhook/密码进入日志和消息。
    if isinstance(exc, MonitorError):
        return str(exc)
    if type(exc).__module__.startswith("pymysql"):
        code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else "unknown"
        return f"MySQL 请求失败（{code}），请检查连接配置、表结构和权限"
    return type(exc).__name__


class Monitor:
    def __init__(self, config, dry_run=False):
        self.config, self.dry_run = config, dry_run
        self.center, self.grafana, self.lark = Center(config), Grafana(config), Lark(config)
        self.store = None if dry_run else Store(config.scope)

    def emit(self, key, text, record=None, seconds=300):
        if self.dry_run:
            LOG.info("[试运行] %s", text)
        else:
            # 不管通知是否被防抖抑制，都留下本轮失败原因，方便 journalctl 排查。
            if record is None:
                LOG.error("%s", text)
            self.store.enqueue(key, text, record, seconds)

    def cycle(self):
        good = True
        collection_failed = False
        rules, samples, problems = None, {}, []
        try:
            rules = self.center.rules()
        except Exception as exc:
            good = False
            self.emit("center-error", "【短信余额监控】告警中心规则读取失败\n" + safe_error(exc))
        try:
            samples, problems = self.grafana.collect()
        except Exception as exc:
            collection_failed = True
            problems.append(safe_error(exc))
        missing = sorted(set(EXPECTED_ACCOUNTS) - samples.keys())
        if missing and not collection_failed:
            problems.append("缺少有效余额: " + "、".join(missing))
        if problems:
            good = False
            self.emit("grafana-error", "【短信余额监控】Grafana 采集异常\n" + "\n".join(problems))
        if rules is not None:
            by_account = {}
            for rule in rules:
                by_account.setdefault(rule["account"], []).append(rule)
            unmatched = sorted((set(EXPECTED_ACCOUNTS) | set(samples)) - by_account.keys())
            if unmatched:
                good = False
                self.emit("mapping-error", "【短信余额监控】账号未配置告警规则\n" + "\n".join(unmatched))
            for account, matching in by_account.items():
                if len(matching) != 1:
                    good = False
                    self.emit("duplicate:" + account, "【短信余额监控】同一业务中账号匹配多条规则，请排除歧义\n" + account)
                    continue
                rule = matching[0]
                if not rule["enabled"]:
                    continue
                try:
                    cooldown = duration(rule["debounce"])
                    threshold = number(rule["threshold"])
                    if account not in samples:
                        if account not in missing and not collection_failed:
                            good = False
                            self.emit("missing:" + account, "【短信余额监控】账号缺少有效余额\n" + account)
                        continue
                    balance, stamp = samples[account]
                    LOG.info("账号=%s 余额=%s 阈值=%s", account, balance, threshold)
                    if balance >= threshold:
                        continue
                    sample_time = time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(stamp))
                    detail = (f"【短信余额不足】\n业务: {rule['business']}\n规则: {rule['code']}\n"
                              f"账号: {account}\n余额: {balance}\n阈值: < {threshold}\n"
                              f"防抖: {rule['debounce']}\n样本时间: {sample_time}\n"
                              f"来源: Grafana {self.config.uid} / {self.config.panel}")
                    record = {"code": rule["code"], "type": "余额不足", "value": str(balance),
                              "detail": detail, "status": "待处理"}
                    self.emit("balance:" + rule["code"], detail, record, cooldown)
                except Exception as exc:
                    good = False
                    self.emit("rule-error:" + rule["code"], "【短信余额监控】规则处理失败\n规则: " + rule["code"] + "\n" + safe_error(exc))
        if not self.dry_run:
            good = self.store.flush(self.center, self.lark) and good
        LOG.info("本轮完成，有效余额 %d 个，状态 %s", len(samples), "正常" if good else "异常")
        return good


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name("monitor.env"))
    parser.add_argument("--once", action="store_true", help="只运行一轮（异常返回 1）")
    parser.add_argument("--dry-run", action="store_true", help="只读采集和比较，不通知、不写记录/状态库")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    monitor = None
    try:
        load_env(args.env_file)
        config = Config()
        monitor = Monitor(config, args.dry_run)
        LOG.info("监控启动：轮询间隔 %s 秒，面板 %s / %s，模式 %s",
                 config.interval, config.uid, config.panel,
                 "试运行" if args.dry_run else "单次" if args.once else "常驻")
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.is_set():
            start = time.monotonic()
            good = monitor.cycle()
            if args.once or args.dry_run:
                return 0 if good else 1
            stop.wait(max(0, config.interval - (time.monotonic() - start)))
        return 0
    except Exception as exc:
        LOG.error("监控停止: %s", safe_error(exc))
        return 1
    finally:
        if monitor and monitor.store:
            monitor.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
