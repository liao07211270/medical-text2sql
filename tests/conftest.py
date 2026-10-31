"""測試共用設定：用 SQLite 載入同一份 schema / seed，取代 MySQL，讓沒有 Docker 也能測 API 邏輯。"""
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT))

import db_api  # noqa: E402


def mysql_to_sqlite(sql: str) -> str:
    """把 MySQL 專屬語法拿掉，讓 SQLite 能執行。"""
    sql = re.sub(r"COMMENT\s+'[^']*'", "", sql)
    sql = re.sub(r"\)\s*ENGINE=[^;]*;", ");", sql)
    sql = re.sub(r"^(SET NAMES|USE|CREATE DATABASE)[^;]*;", "", sql, flags=re.M)
    return sql.replace("AUTO_INCREMENT", "")


def build_sqlite_db(path):
    conn = sqlite3.connect(path)
    for name in ("01_schema.sql", "02_seed.sql"):
        conn.executescript(mysql_to_sqlite((ROOT / "db" / "init" / name).read_text(encoding="utf-8")))
    conn.commit()
    conn.close()


@pytest.fixture(scope="session")
def sqlite_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "meddb.sqlite"
    build_sqlite_db(path)
    return path


@pytest.fixture
def client(sqlite_path, monkeypatch):
    # 以唯讀模式開啟，模擬 MySQL 唯讀帳號
    monkeypatch.setattr(db_api, "get_connection",
                        lambda: sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True))
    db_api.app.config["TESTING"] = True
    return db_api.app.test_client()
