import json
import errno
import socket
import ssl
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import grafana_balance_monitor as m
from mysql_test_support import make_store


def frame(values, times=None, name="A"):
    times = [990000] * len(values) if times is None else times
    return {"schema": {"fields": [
        {"name": "Time", "type": "time"},
        {"name": "Value", "type": "number", "labels": {"account_name": name}}]},
        "data": {"values": [times, values]}}


def response(*frames):
    return {"results": {"A": {"status": 200, "frames": list(frames)}}}


class ParsingTests(unittest.TestCase):
    def test_zero_and_last_non_null_unsorted(self):
        samples, errors = m.parse_frames(response(frame([25, None, 0], [980000, 995000, 990000])), 1000, 21600)
        self.assertEqual(samples["A"], (m.Decimal(0), 990))
        self.assertEqual(errors, [])

    def test_four_hour_sample_is_valid(self):
        samples, errors = m.parse_frames(response(frame([100], [1000 * (20000 - 14400)])), 20000, 21600)
        self.assertIn("A", samples)
        self.assertFalse(errors)

    def test_stale_and_future(self):
        for stamp in [1000, 50000000]:
            samples, errors = m.parse_frames(response(frame([1], [stamp])), 30000, 21600)
            self.assertFalse(samples)
            self.assertTrue(errors)

    def test_nan_does_not_fall_back_to_old_balance(self):
        samples, errors = m.parse_frames(response(frame([1, "NaN"], [980000, 990000])), 1000, 21600)
        self.assertFalse(samples)
        self.assertTrue(errors)

    def test_conflicting_same_account_timestamp(self):
        samples, errors = m.parse_frames(response(frame([1]), frame([2])), 1000, 21600)
        self.assertFalse(samples)
        self.assertTrue(errors)

    def test_table(self):
        table = {"schema": {"fields": [{"name": "account_name", "type": "string"},
                 {"name": "Time", "type": "time"}, {"name": "balance", "type": "number"}]},
                 "data": {"values": [["A", "B"], [990000, 995000], [12, 0]]}}
        samples, errors = m.parse_frames(response(table), 1000, 21600)
        self.assertEqual(samples["B"][0], 0)
        self.assertFalse(errors)

    def test_partial_error_is_reported(self):
        data = response(frame([10]))
        data["results"]["B"] = {"error": "unavailable", "status": 500}
        samples, errors = m.parse_frames(data, 1000, 21600)
        self.assertIn("A", samples)
        self.assertTrue(errors)

    def test_duration_and_money(self):
        self.assertEqual(m.duration("1d"), 86400)
        self.assertEqual(m.duration("1.5h"), 5400)
        self.assertEqual(m.number("0.1"), m.Decimal("0.1"))
        for value in [None, True, "NaN", "Infinity"]:
            with self.assertRaises(m.MonitorError):
                m.number(value)


class NetworkTests(unittest.TestCase):
    def test_classified_errors_and_no_secret_in_log(self):
        for reason, expected in [
            (socket.gaierror(-2, "secret-host"), "DNS 解析失败"),
            (ssl.SSLCertVerificationError(1, "secret-cert"), "TLS 证书验证失败"),
            (TimeoutError("secret-url"), "连接或响应超时"),
            (ConnectionRefusedError("secret-url"), "连接被拒绝"),
            (OSError(errno.ENETUNREACH, "secret-url"), "不可达"),
        ]:
            http = m.HTTP("Grafana", "https://example.com", 30)
            http.opener = Mock()
            http.opener.open.side_effect = m.URLError(reason)
            with self.assertRaises(m.MonitorError) as caught:
                http.request("POST", "/login", {"password": "secret-password"})
            self.assertIn(expected, str(caught.exception))
            self.assertIn("登录失败", str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))


class DeliveryTests(unittest.TestCase):
    def test_restart_cooldown_and_independent_retry(self):
        store = make_store(self)
        path = store.scope
        if True:
            now = time.time()
            self.assertTrue(store.enqueue("balance:1", "low", {"code": "1"}, 600, now))
            center, lark = Mock(), Mock()
            center.record.side_effect = m.MonitorError("中心故障")
            self.assertFalse(store.flush(center, lark))
            lark.send.assert_called_once()
            store.db.close()
            store = m.Store(path)
            self.addCleanup(lambda: store.close() if store.db.open else None)
            # 待补发记录不会因为冷却结束而再次产生一条 Lark 通知。
            self.assertFalse(store.enqueue("balance:1", "low", {"code": "1"}, 600, now + 900))
            center.record.side_effect = None
            self.assertTrue(store.flush(center, lark))
            lark.send.assert_called_once()
            self.assertFalse(store.enqueue("balance:1", "low", {"code": "1"}, 600, now + 300))
            self.assertTrue(store.enqueue("balance:1", "low", {"code": "1"}, 600, now + 600))
            store.db.close()

    def test_lark_failure_still_creates_record(self):
        store = make_store(self)
        store.enqueue("one", "test", {"code": "1"}, 300)
        center, lark = Mock(), Mock()
        lark.send.side_effect = m.MonitorError("Lark故障")
        self.assertFalse(store.flush(center, lark))
        center.record.assert_called_once()
        lark.send.side_effect = None
        self.assertTrue(store.flush(center, lark))
        center.record.assert_called_once()
        store.db.close()

    def test_record_response_lost_deduplicates(self):
        center = object.__new__(m.Center)
        center.request = Mock(return_value=[{"detail": "low\n[event:abc]"}])
        center.record({"code": "123", "detail": "low"}, "abc")
        self.assertEqual(center.request.call_count, 1)

    def test_lark_requires_business_success(self):
        lark = object.__new__(m.Lark)
        lark.http, lark.secret = Mock(), "test-secret"
        lark.http.request.return_value = {"code": 19024}
        with self.assertRaises(m.MonitorError):
            lark.send("test")
        lark.http.request.return_value = {"code": 0}
        lark.send("test")
        payload = lark.http.request.call_args.kwargs["body"]
        self.assertIn("sign", payload)
        self.assertEqual(payload["msg_type"], "text")


class WorkflowTests(unittest.TestCase):
    def build(self, balance=10, enabled=True):
        monitor = object.__new__(m.Monitor)
        monitor.config = SimpleNamespace(uid="ad6mjfp", panel="全部")
        monitor.dry_run = False
        monitor.store = make_store(self)
        monitor.center, monitor.grafana, monitor.lark = Mock(), Mock(), Mock()
        monitor.center.rules.return_value = [{"code": "123", "account": "A", "business": "余额",
            "threshold": 100, "debounce": "10m", "enabled": enabled}]
        monitor.grafana.collect.return_value = ({"A": (m.number(balance), time.time())}, [])
        return monitor

    @patch.object(m, "EXPECTED_ACCOUNTS", ["A"])
    def test_threshold_equality_disabled_and_zero(self):
        for balance, enabled, count in [(100, True, 0), (99, False, 0), (0, True, 1)]:
            monitor = self.build(balance, enabled)
            self.assertTrue(monitor.cycle())
            self.assertEqual(monitor.lark.send.call_count, count)
            self.assertEqual(monitor.center.record.call_count, count)
            if count:
                record = monitor.center.record.call_args.args[0]
                self.assertEqual(record["value"], "0")
                self.assertEqual(record["code"], "123")
                self.assertEqual(record["status"], "待处理")

    @patch.object(m, "EXPECTED_ACCOUNTS", ["A"])
    def test_two_cycles_only_one_event(self):
        monitor = self.build()
        monitor.cycle()
        monitor.cycle()
        monitor.lark.send.assert_called_once()
        monitor.center.record.assert_called_once()

    @patch.object(m, "EXPECTED_ACCOUNTS", ["A"])
    def test_failure_logged_even_when_notification_is_debounced(self):
        monitor = self.build()
        monitor.grafana.collect.side_effect = m.APIError("Grafana", 403)
        with self.assertLogs("balance-monitor", level="ERROR") as logs:
            monitor.cycle()
            monitor.cycle()
        self.assertEqual(sum("HTTP 403" in line for line in logs.output), 2)
        monitor.lark.send.assert_called_once()

    @patch.object(m, "EXPECTED_ACCOUNTS", ["A"])
    def test_grafana_failure_not_zero_balance(self):
        monitor = self.build()
        monitor.grafana.collect.side_effect = m.MonitorError("Grafana 失败")
        self.assertFalse(monitor.cycle())
        monitor.lark.send.assert_called_once()
        monitor.center.record.assert_not_called()
        self.assertIn("采集异常", monitor.lark.send.call_args.args[0])
        self.assertNotIn("缺少有效余额", monitor.lark.send.call_args.args[0])

    @patch.object(m, "EXPECTED_ACCOUNTS", ["A"])
    def test_center_failure_still_sends_notification(self):
        monitor = self.build()
        monitor.center.rules.side_effect = m.MonitorError("登录失败")
        self.assertFalse(monitor.cycle())
        monitor.lark.send.assert_called_once()
        self.assertIn("规则读取失败", monitor.lark.send.call_args.args[0])

    def test_grafana_dashboard_query_chain(self):
        grafana = object.__new__(m.Grafana)
        grafana.config = SimpleNamespace(uid="ad6mjfp", panel="全部", query_file="", max_age=21600)
        dashboard = {"dashboard": {"panels": [{"title": "其他"}, {"panels": [{"title": "全部",
            "datasource": {"uid": "prom", "type": "prometheus"},
            "targets": [{"refId": "A", "expr": "balance", "range": True}]}]}]}}
        grafana.request = Mock(side_effect=[dashboard, response(frame([5], [time.time() * 1000]))])
        samples, errors = grafana.collect()
        self.assertEqual(samples["A"][0], 5)
        self.assertFalse(errors)
        method, path, body = grafana.request.call_args.args
        self.assertEqual((method, path), ("POST", "/api/ds/query"))
        self.assertEqual(body["queries"][0]["datasource"]["uid"], "prom")
        self.assertEqual(int(body["to"]) - int(body["from"]), 21600000)


if __name__ == "__main__":
    unittest.main()
