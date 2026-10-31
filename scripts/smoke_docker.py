"""對已啟動的 Docker 版 flask-api（真實 MySQL）跑 tests/cases.py 全部案例。

    docker compose up -d --build
    python scripts/smoke_docker.py            # 預設 http://localhost:5000
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dify_security_code import main as security_node  # noqa: E402
from tests.cases import CASES  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"


def post(sql):
    req = urllib.request.Request(f"{BASE}/execute_sql", data=json.dumps({"sql": sql}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
        print("health:", r.read().decode())

    failed = 0
    for name, _, llm_output, expected in CASES:
        node = security_node(llm_output)
        if node["status"] != "safe":
            actual, detail = "node", node["message"]
        else:
            code, body = post(node["safe_sql"])
            if body["status"] == "rejected":
                actual, detail = "api", body["message"]
            elif body["status"] == "success":
                actual, detail = ("rows" if body["row_count"] else "success"), f"{body['row_count']} 筆"
            else:
                actual, detail = "error", body["message"]
        ok = actual == expected or (expected == "success" and actual == "rows")
        failed += not ok
        print(f"{'OK ' if ok else 'NG '} {name}: {actual} ({detail})")

    # 逾時：真實 MySQL 才測得到。用大量 CROSS JOIN 製造慢查詢，應在 QUERY_TIMEOUT_MS 內被中止
    code, body = post("SELECT COUNT(*) FROM Prescriptions a CROSS JOIN Prescriptions b "
                      "CROSS JOIN Prescriptions c CROSS JOIN Prescriptions d CROSS JOIN Prescriptions e "
                      "WHERE a.Days + b.Days + c.Days + d.Days + e.Days > 1000")
    timeout_ok = body.get("status") == "error" and "maximum statement execution time" in body.get("message", "").lower()
    failed += not timeout_ok
    print(f"{'OK ' if timeout_ok else 'NG '} 查詢逾時中止: {code} {body.get('message', body)}")

    print(f"\n{len(CASES) + 1 - failed}/{len(CASES) + 1} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
