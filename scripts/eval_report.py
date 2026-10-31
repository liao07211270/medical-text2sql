"""離線評估：把 tests/cases.py 的每個案例跑過「資安攔截節點 → Flask API（SQLite）」，
輸出 docs/eval_results.md 結果表。不需要 Docker、MySQL 或 LLM 金鑰。

    python scripts/eval_report.py
"""
import logging
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "api")]

import db_api  # noqa: E402
from dify_security_code import main as security_node  # noqa: E402
from tests.cases import CASES  # noqa: E402
from tests.conftest import build_sqlite_db  # noqa: E402

LABEL = {"rows": "放行並查到資料", "success": "放行並執行成功", "node": "資安節點攔截", "api": "API 第二道防線攔截"}


def main():
    logging.disable(logging.CRITICAL)  # 只要結果表，不印 API 日誌
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meddb.sqlite"
        build_sqlite_db(path)
        db_api.get_connection = lambda: sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        client = db_api.app.test_client()

        results = []
        for name, category, llm_output, expected in CASES:
            node = security_node(llm_output)
            if node["status"] != "safe":
                actual, detail = "node", node["message"]
            else:
                resp = client.post("/execute_sql", json={"sql": node["safe_sql"]})
                body = resp.get_json()
                if body["status"] == "rejected":
                    actual, detail = "api", body["message"]
                elif body["status"] == "success":
                    actual = "rows" if body["row_count"] > 0 else "success"
                    detail = f"{body['row_count']} 筆"
                else:
                    actual, detail = "error", body["message"]
            ok = actual == expected or (expected == "success" and actual == "rows")
            results.append((category, name, LABEL[expected], LABEL.get(actual, "執行錯誤"), detail, ok))

    passed = sum(r[-1] for r in results)
    by_cat = Counter(r[0] for r in results)
    lines = [
        "# 離線評估結果",
        "",
        "LLM 輸出以固定字串模擬，測試「Dify 資安攔截節點 → Flask API」兩層防護與查詢結果。",
        "資料庫為 SQLite 載入同一份 schema/seed（唯讀模式）。由 `scripts/eval_report.py` 產生。",
        "",
        f"**通過 {passed} / {len(results)}**",
        "",
        "| 類別 | 案例數 |",
        "|---|---|",
        *[f"| {c} | {n} |" for c, n in by_cat.items()],
        "",
        "| 類別 | 案例 | 預期 | 實際 | 說明 | 結果 |",
        "|---|---|---|---|---|---|",
    ]
    for cat, name, exp, act, detail, ok in results:
        detail = detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {cat} | {name} | {exp} | {act} | {detail} | {'✅' if ok else '❌'} |")

    out = ROOT / "docs" / "eval_results.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{len(results)} passed -> {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
