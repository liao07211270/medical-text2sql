"""資安攔截節點 + Flask API 的端到端測試（LLM 輸出以固定字串模擬）。"""
import pytest

import db_api
from dify_security_code import main as security_node
from tests.cases import CASES


def run_pipeline(client, llm_output):
    node = security_node(llm_output)
    if node["status"] != "safe":
        return "node", node, None
    resp = client.post("/execute_sql", json={"sql": node["safe_sql"]})
    return ("api" if resp.get_json()["status"] == "rejected" else "executed"), node, resp


@pytest.mark.parametrize("name,category,llm_output,expected", CASES, ids=[c[0] for c in CASES])
def test_case(client, name, category, llm_output, expected):
    stage, node, resp = run_pipeline(client, llm_output)
    if expected == "node":
        assert stage == "node", f"應被資安節點攔截：{node}"
        assert node["safe_sql"] == ""
        return
    assert stage != "node", f"不應被資安節點攔截：{node['message']}"
    body = resp.get_json()
    if expected == "api":
        assert stage == "api", body
        assert resp.status_code == 200 and body["status"] == "rejected"
        return
    assert resp.status_code == 200, body
    assert body["status"] == "success"
    if expected == "rows":
        assert body["row_count"] > 0, f"範例查不到資料：{body['sql']}"


def test_limit_appended(client):
    body = client.post("/execute_sql", json={"sql": "SELECT * FROM Prescriptions"}).get_json()
    assert body["sql"].endswith(f"LIMIT {db_api.MAX_ROWS}")


def test_existing_limit_kept(client):
    body = client.post("/execute_sql", json={"sql": "SELECT * FROM Patients LIMIT 3;"}).get_json()
    assert body["sql"] == "SELECT * FROM Patients LIMIT 3"
    assert body["row_count"] == 3


def test_max_rows_cap(client, monkeypatch):
    monkeypatch.setattr(db_api, "MAX_ROWS", 5)
    body = client.post("/execute_sql", json={"sql": "SELECT * FROM Prescriptions LIMIT 100"}).get_json()
    assert body["row_count"] == 5 and body["truncated"] is True


def test_response_shape(client):
    body = client.post("/execute_sql", json={"sql": "SELECT PatientID, Height FROM Patients WHERE PatientID = 'A123456789'"}).get_json()
    assert body["columns"] == ["PatientID", "Height"]
    assert body["rows"] == [["A123456789", 172.5]]


@pytest.mark.parametrize("payload", [None, {}, {"query": "SELECT 1"}, {"sql": 123}])
def test_bad_payload(client, payload):
    resp = client.post("/execute_sql", json=payload) if payload is not None else client.post("/execute_sql", data="not json")
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


@pytest.mark.parametrize("sql", ["", "   "])
def test_empty_sql_skipped(client, sql):
    """資安節點攔截時 safe_sql 為空：要回 200，否則 Dify 會把整個工作流判定失敗。"""
    resp = client.post("/execute_sql", json={"sql": sql})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "skipped"


def test_rejected_returns_200(client):
    resp = client.post("/execute_sql", json={"sql": "SELECT 1; SELECT 2"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "rejected"


def test_db_error_returns_200_with_error_status(client):
    resp = client.post("/execute_sql", json={"sql": "SELECT * FROM NoSuchTable"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "error"


def test_readonly_connection_blocks_writes(sqlite_path):
    """即使繞過檢查直接執行，唯讀連線也寫不進去（對應 MySQL 唯讀帳號）。"""
    import sqlite3
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM Prescriptions")
