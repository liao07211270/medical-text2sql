"""醫療 Text-to-SQL：SQL 執行 API

Dify 工作流的 HTTP 節點呼叫：
    POST http://flask-api:5000/execute_sql
    {"sql": "SELECT ..."}

這一層是 Dify「資安攔截」節點之後的第二道防線：
    1. 只接受單一條 SELECT（拒絕分號串接、註解、危險關鍵字）
    2. 沒有 LIMIT 時自動補上，並以 fetchmany 限制最多回傳 MAX_ROWS 筆
    3. MySQL 端用唯讀帳號 + MAX_EXECUTION_TIME 限制查詢時間

回傳格式（固定）：
    成功：{"status": "success", "sql": ..., "columns": [...], "rows": [[...]], "row_count": n, "truncated": bool}
    略過：{"status": "skipped", "message": ...}   # sql 為空，代表上游資安節點已攔截
    拒絕：{"status": "rejected", "message": ...}  # 第二道防線不放行
    失敗：{"status": "error", "message": ...}     # 資料庫執行失敗

除了請求格式錯誤（400）以外一律回 HTTP 200：Dify 的 HTTP 節點遇到 4xx/5xx 會把整個工作流
判定失敗，攔截訊息就到不了輸出節點；所以結果改由 body 的 status 表示。
"""
import datetime
import decimal
import logging
import os
import re

from flask import Flask, jsonify, request

MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
QUERY_TIMEOUT_MS = int(os.getenv("QUERY_TIMEOUT_MS", "5000"))
MAX_SQL_LENGTH = int(os.getenv("MAX_SQL_LENGTH", "4000"))

# 即使 Dify 節點已檢查過，這裡仍再擋一次；另外加上讀檔、延遲、鎖定等 SELECT 也能做到的危險用法
FORBIDDEN = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "EXEC", "EXECUTE",
    "GRANT", "REVOKE", "CREATE", "RENAME", "CALL", "HANDLER", "LOAD",
    "OUTFILE", "DUMPFILE", "LOAD_FILE", "SLEEP", "BENCHMARK", "LOCK", "SET", "SHOW",
]
FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b")
STRING_LITERAL_RE = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.|\"\")*\"")

app = Flask(__name__)
app.json.ensure_ascii = False  # 讓 Dify 的 db_result 直接看到中文
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("db_api")


class SQLRejected(ValueError):
    pass


def validate_sql(sql):
    """檢查並正規化 SQL，回傳實際要執行的語句；不合格時丟出 SQLRejected。"""
    if not isinstance(sql, str) or not sql.strip():
        raise SQLRejected("SQL 為空")
    if len(sql) > MAX_SQL_LENGTH:
        raise SQLRejected(f"SQL 長度超過 {MAX_SQL_LENGTH} 字元")

    sql = sql.strip().rstrip(";").strip()
    # 去掉字串常值後再檢查結構，避免 LIKE '%;%' 之類的內容誤判，也避免把關鍵字藏在字串外
    skeleton = STRING_LITERAL_RE.sub("''", sql)
    if "'" in skeleton.replace("''", "") or '"' in skeleton.replace('""', ""):
        raise SQLRejected("引號不成對")
    upper = skeleton.upper()

    if ";" in upper:
        raise SQLRejected("不允許一次執行多條 SQL 語句")
    if "--" in upper or "/*" in upper or "#" in upper:
        raise SQLRejected("不允許 SQL 註解")
    if not upper.lstrip("( \n\t").startswith("SELECT"):
        raise SQLRejected("僅允許 SELECT 查詢")
    m = FORBIDDEN_RE.search(upper)
    if m:
        raise SQLRejected(f"偵測到禁用關鍵字 '{m.group(1)}'")

    if not re.search(r"\bLIMIT\s+\d+(\s*,\s*\d+)?(\s+OFFSET\s+\d+)?\s*$", upper):
        sql = f"{sql} LIMIT {MAX_ROWS}"
    return sql


def to_json_value(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def get_connection():
    import pymysql

    return pymysql.connect(
        host=os.getenv("DB_HOST", "mysql"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "meddb"),
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=QUERY_TIMEOUT_MS // 1000 + 2,
        # MySQL 端的 SELECT 執行時間上限（毫秒）
        init_command=f"SET SESSION MAX_EXECUTION_TIME={QUERY_TIMEOUT_MS}",
    )


def run_query(sql):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        rows = [[to_json_value(v) for v in r] for r in rows[:MAX_ROWS]]
        return columns, rows, truncated
    finally:
        conn.close()


def result(status, message, code=200):
    return jsonify({"status": status, "message": message}), code


@app.post("/execute_sql")
def execute_sql():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or "sql" not in payload or not isinstance(payload["sql"], str):
        return result("error", '請求格式錯誤，需為 JSON：{"sql": "SELECT ..."}', 400)

    if not payload["sql"].strip():
        return result("skipped", "未執行查詢：沒有收到 SQL（上游資安節點已攔截或判定問題無關）")

    try:
        sql = validate_sql(payload["sql"])
    except SQLRejected as e:
        log.warning("rejected: %s | %r", e, payload.get("sql"))
        return result("rejected", f"SQL 被拒絕：{e}")

    try:
        columns, rows, truncated = run_query(sql)
    except Exception as e:  # 資料庫錯誤（語法錯、逾時、連線失敗）
        log.exception("query failed: %s", sql)
        return result("error", f"查詢執行失敗：{type(e).__name__}: {e}")

    log.info("ok rows=%d truncated=%s | %s", len(rows), truncated, sql)
    return jsonify({
        "status": "success",
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    })


@app.get("/health")
def health():
    try:
        run_query("SELECT 1")
        return jsonify({"status": "ok", "db": "ok"})
    except Exception as e:
        return jsonify({"status": "degraded", "db": f"{type(e).__name__}: {e}"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
