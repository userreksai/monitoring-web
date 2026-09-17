"""只供测试：创建独立随机数据库，绝不清空 MYSQL_DATABASE 指定的库。"""
import os
import uuid
import hashlib
from unittest.mock import patch


def prepare_mysql_test(test):
    if os.getenv("MYSQL_TEST_RUN") != "1":
        test.skipTest("MYSQL_TEST_RUN=1 未配置，跳过真实 MySQL 集成测试")
    import pymysql
    admin = pymysql.connect(host=os.getenv("MYSQL_TEST_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_TEST_PORT", "3306")), user=os.getenv("MYSQL_TEST_USER", "root"),
        password=os.getenv("MYSQL_TEST_PASSWORD", ""), autocommit=True)
    name = "monitoring_test_" + uuid.uuid4().hex
    with admin.cursor() as cur:
        cur.execute("CREATE DATABASE `"+name+"` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    def cleanup():
        with admin.cursor() as cur:
            cur.execute("DROP DATABASE `"+name+"`")
        admin.close()
    test.addCleanup(cleanup)
    env = patch.dict(os.environ, {
        "MYSQL_HOST": os.getenv("MYSQL_TEST_HOST", "127.0.0.1"),
        "MYSQL_PORT": os.getenv("MYSQL_TEST_PORT", "3306"),
        "MYSQL_USER": os.getenv("MYSQL_TEST_USER", "root"),
        "MYSQL_PASSWORD": os.getenv("MYSQL_TEST_PASSWORD", ""),
        "MYSQL_DATABASE": name, "MYSQL_SSL_CA": ""})
    env.start()
    test.addCleanup(env.stop)
    return name


def make_store(test):
    from grafana_balance_monitor import Store
    name = prepare_mysql_test(test)
    store = Store(hashlib.sha256(name.encode()).hexdigest()[:32])
    test.addCleanup(lambda: store.close() if store.db.open else None)
    return store
