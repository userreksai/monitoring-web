import json
import time
import unittest
from pathlib import Path

import grafana_balance_monitor as m
from migrate_sqlite_to_mysql import migrate
from mysql_test_support import prepare_mysql_test


class MySQLMigrationTests(unittest.TestCase):
    def setUp(self):
        prepare_mysql_test(self)
        self.db = m.mysql_connect()
        self.addCleanup(self.db.close)
        for sql in Path("monitoring-service/schema.sql").read_text(encoding="utf-8").split(";"):
            if sql.strip():
                with self.db.cursor() as cur:
                    cur.execute(sql)
        self.source = dict(businesses=[dict(id=1, code="534784", name="短信商", enabled=1, tag="", description="", tone="green")],
            rules=[dict(code="123", business_id=1, provider="云通讯", account="A", threshold=1000.25,
                        fluctuation=10, debounce="1d", purpose="vty", tag="", enabled=1)],
            users=[dict(username="admin", password_hash="a"*64, display_name="管理")],
            alert_records=[dict(id=1, rule_code="123", business="短信商", provider="云通讯", account="A",
                alert_type="余额不足", value="0", detail="测试", status="待处理", level="warning", occurred_at="2026-09-17 14:00:00")])

    def count(self, table):
        with self.db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM "+table)
            return cur.fetchone()[0]

    def test_preview_apply_rerun_and_state(self):
        now = time.time()
        state = {"cooldown": [{"key": "balance:123", "at": now}], "outbox": [dict(
            id="a"*32, key="balance:123", body="test", record=json.dumps({"code":"123"}),
            lark_done=1, record_done=0, created=now)]}
        preview = migrate(self.db, self.source, state, scope="0"*32)
        self.assertEqual(preview["insert"], 3)
        self.assertEqual(self.count("business"), 0)
        result = migrate(self.db, self.source, state, scope="0"*32, apply=True)
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(self.count("notification_log"), 1)
        migrate(self.db, self.source, state, scope="0"*32, apply=True)
        self.assertEqual(self.count("notification_log"), 1)
        with self.db.cursor() as cur:
            cur.execute("SELECT balance_threshold,alert_silence_seconds FROM business_detail")
            balance, seconds = cur.fetchone()
            self.assertEqual(str(balance), "1000.2500")
            self.assertEqual(seconds, 86400)
            cur.execute("SELECT lark_done,record_done FROM monitor_outbox")
            self.assertEqual(cur.fetchone(), (1,0))
        store = m.Store("0"*32)
        self.addCleanup(store.close)
        self.assertFalse(store.enqueue("balance:123", "new", {"code":"123"}, 86400))
        with self.assertRaises(m.MonitorError):
            m.Store("0"*32)

    def test_conflict_does_not_overwrite(self):
        with self.db.cursor() as cur:
            cur.execute("INSERT INTO business(business_code,business_name) VALUES('534784','MySQL原值')")
        report = migrate(self.db, self.source, apply=True)
        self.assertTrue(report["conflicts"])
        self.assertEqual(self.count("business_detail"), 0)
        with self.db.cursor() as cur:
            cur.execute("SELECT business_name FROM business")
            self.assertEqual(cur.fetchone()[0], "MySQL原值")

    def test_failed_record_rolls_back_rules_and_business(self):
        self.source["alert_records"][0]["rule_code"] = "missing"
        with self.assertRaises(Exception):
            migrate(self.db, self.source, apply=True)
        self.assertEqual(self.count("business"), 0)
        self.assertEqual(self.count("business_detail"), 0)


if __name__ == "__main__":
    unittest.main()
