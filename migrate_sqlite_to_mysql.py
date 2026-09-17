#!/usr/bin/env python3
"""离线 SQLite -> 原有 MySQL 表迁移。默认只读预览；--apply 才写入。"""
import argparse
import hashlib
import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

from grafana_balance_monitor import load_env, mysql_connect, Store, duration, safe_error


def read_sqlite(path, tables):
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        return {name: [dict(row) for row in source.execute('SELECT * FROM "'+name+'"')]
                for name in tables}
    finally:
        source.close()


def source_rows(source):
    businesses = {b["id"]: b for b in source["businesses"]}
    for b in businesses.values():
        yield "business", "business_code", dict(business_code=b["code"], business_name=b["name"],
            notify_enabled=b["enabled"], tag=b["tag"], description=b["description"], tone=b["tone"])
    for r in source["rules"]:
        seconds = Decimal(str(duration(r["debounce"])))
        if seconds != seconds.to_integral_value():
            raise ValueError("SQLite 规则防抖时间不是整数秒: " + r["code"])
        b = businesses[r["business_id"]]
        yield "business_detail", "detail_code", dict(detail_code=r["code"], business_code=b["code"],
            business_name=b["name"], fluctuation_percent=r["fluctuation"],
            balance_threshold=r["threshold"], vendor=r["provider"], account=r["account"],
            notify_enabled=r["enabled"], tag=r["tag"], alert_silence_seconds=int(seconds),
            business_purpose=r["purpose"])
    for u in source["users"]:
        yield "user_account", "account", dict(account=u["username"], password_hash=u["password_hash"], display_name=u["display_name"])


def equivalent(a, b):
    if a is None and b == "" or b is None and a == "":
        return True
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        return Decimal(str(a)) == Decimal(str(b))
    return a == b


def sql_insert(cur, table, row):
    fields = list(row)
    cur.execute("INSERT INTO `"+table+"` ("+",".join('`'+f+'`' for f in fields)+") VALUES ("+
                ",".join(["%s"]*len(fields))+")", tuple(row[f] for f in fields))
    return cur.lastrowid


def migrate(db, source=None, state=None, source_id="monitoring-service-sqlite", scope=None,
            apply=False, prefer="fail"):
    """单事务迁移数据；预览只执行 SELECT。业务编码为关联键，不强行覆盖数字主键。"""
    report = {"insert": 0, "update": 0, "skip": 0, "records": 0, "state": 0, "conflicts": []}
    operations = []
    with db.cursor() as cur:
        if source:
            for table, key, row in source_rows(source):
                fields = list(row)
                cur.execute("SELECT "+",".join('`'+f+'`' for f in fields)+" FROM `"+table+"` WHERE `"+key+"`=%s", (row[key],))
                existing = cur.fetchone()
                if existing is None:
                    operations.append(("insert", table, key, row))
                    report["insert"] += 1
                    continue
                changed = [f for f, value in zip(fields, existing) if not equivalent(value, row[f])]
                if not changed:
                    report["skip"] += 1
                elif prefer == "mysql":
                    report["skip"] += 1
                elif prefer == "sqlite":
                    operations.append(("update", table, key, row))
                    report["update"] += 1
                else:
                    report["conflicts"].append({"table": table, "key": row[key], "fields": changed})
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='sqlite_import_log'")
            has_ledger = bool(cur.fetchone()[0])
            for r in source["alert_records"]:
                if has_ledger:
                    cur.execute("SELECT target_id FROM sqlite_import_log WHERE source_id=%s AND source_key=%s", (source_id, str(r["id"])))
                    if cur.fetchone():
                        report["skip"] += 1
                        continue
                event = re.search(r"\[event:([a-f0-9]{32})\]", r["detail"])
                row = dict(alert_time=r["occurred_at"], detail_code=r["rule_code"],
                    business_name=r["business"], vendor=r["provider"], account=r["account"],
                    alert_content=r["detail"], alert_type=r["alert_type"], alert_value=r["value"],
                    status=r["status"], level=r["level"], event_id=event[1] if event else None)
                operations.append(("record", "notification_log", str(r["id"]), row))
                report["records"] += 1
        if state:
            report["state"] = len(state["cooldown"]) + len(state["outbox"])
    if not apply or report["conflicts"]:
        return report
    # DDL 独立于数据事务；失败时最多留下空辅助表，不覆盖业务数据。
    with db.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS sqlite_import_log (
            source_id VARCHAR(100) NOT NULL, source_key VARCHAR(64) NOT NULL,
            target_id BIGINT UNSIGNED NOT NULL, PRIMARY KEY(source_id,source_key)
        ) ENGINE=InnoDB""")
    if state:
        Store.prepare(db)
    db.begin()
    try:
        with db.cursor() as cur:
            for action, table, key, row in operations:
                if table == "business_detail":
                    cur.execute("SELECT business_name FROM business WHERE business_code=%s", (row["business_code"],))
                    parent = cur.fetchone()
                    if parent is None:
                        raise ValueError("目标父业务不存在: " + row["business_code"])
                    row = dict(row, business_name=parent[0])
                if action == "insert":
                    sql_insert(cur, table, row)
                elif action == "update":
                    fields = [f for f in row if f != key]
                    cur.execute("UPDATE `"+table+"` SET "+",".join('`'+f+'`=%s' for f in fields)+" WHERE `"+key+"`=%s", tuple(row[f] for f in fields)+(row[key],))
                else:
                    target = None
                    if row["event_id"]:
                        cur.execute("SELECT id FROM notification_log WHERE event_id=%s", (row["event_id"],))
                        found = cur.fetchone()
                        target = found[0] if found else None
                    target = target or sql_insert(cur, table, row)
                    sql_insert(cur, "sqlite_import_log", dict(source_id=source_id, source_key=key, target_id=target))
            if state:
                for r in state["cooldown"]:
                    cur.execute("""INSERT INTO monitor_cooldown(scope,key_hash,last_event_at) VALUES(%s,%s,%s)
                        ON DUPLICATE KEY UPDATE last_event_at=GREATEST(last_event_at,VALUES(last_event_at))""",
                        (scope, hashlib.sha256(r["key"].encode()).hexdigest(), r["at"]))
                for r in state["outbox"]:
                    row = dict(id=r["id"], scope=scope, key_hash=hashlib.sha256(r["key"].encode()).hexdigest(),
                        event_key=r["key"], body=r["body"], record_json=r["record"], lark_done=r["lark_done"],
                        record_done=r["record_done"], created=r["created"])
                    cur.execute("SELECT id FROM monitor_outbox WHERE id=%s", (r["id"],))
                    if not cur.fetchone():
                        sql_insert(cur, "monitor_outbox", row)
                cur.execute("INSERT INTO monitor_state_imports(scope) VALUES(%s) ON DUPLICATE KEY UPDATE scope=scope", (scope,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return report


def main():
    import os
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=Path("monitor.env"))
    p.add_argument("--source-db", type=Path, help="旧告警中心 monitoring.db")
    p.add_argument("--state-db", type=Path, help="旧脚本 monitor-state.sqlite3")
    p.add_argument("--source-id", default="monitoring-service-sqlite", help="同一数据来源重试时保持不变")
    p.add_argument("--prefer", choices=["fail", "mysql", "sqlite"], default="fail", help="同编码冲突策略，默认停止")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if not args.source_db and not args.state_db:
        p.error("至少指定 --source-db 或 --state-db")
    load_env(args.env_file)
    scope = hashlib.sha256((os.getenv("MYSQL_DATABASE", "sms_billing_monitor")+":"+os.getenv("BUSINESS_CODE", "534784")).encode()).hexdigest()[:32]
    db = None
    try:
        source = read_sqlite(args.source_db, ["businesses", "rules", "users", "alert_records"]) if args.source_db else None
        state = read_sqlite(args.state_db, ["cooldown", "outbox"]) if args.state_db else None
        db = mysql_connect()
        with db.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s,0)", ("balance-monitor:"+scope,))
            if cur.fetchone()[0] != 1:
                raise ValueError("监控仍在运行，请先停止监控服务")
            cur.execute("SELECT GET_LOCK(%s,0)", ("sqlite-import:"+scope,))
            if cur.fetchone()[0] != 1:
                raise ValueError("已有迁移任务正在执行")
        report = migrate(db, source, state, args.source_id, scope, args.apply, args.prefer)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["conflicts"]:
            print("存在冲突，未迁移数据。核对后明确选择 --prefer mysql 或 --prefer sqlite。")
            return 2
        print("迁移已提交，SQLite 原文件未修改。" if args.apply else "只读预览，未写入；确认后追加 --apply。")
        return 0
    except Exception as exc:
        print("迁移失败：" + (str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else safe_error(exc)))
        return 1
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
