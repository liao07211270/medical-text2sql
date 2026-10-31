import re

def main(sql_input: str) -> dict:

    # 若 LLM 回傳空值或非字串，直接攔截
    if not sql_input or not isinstance(sql_input, str):
        return {
            "status": "danger",
            "safe_sql": "",
            "message": "⚠️ 無法產生對應的查詢語句，請換個方式描述您的問題。"
        }

    sql_stripped = sql_input.strip()
    sql_upper = sql_stripped.upper()

    # 若回傳內容不像 SQL（不含 SELECT、FROM），視為無關問題
    if 'SELECT' not in sql_upper or 'FROM' not in sql_upper:
        return {
            "status": "danger",
            "safe_sql": "",
            "message": "⚠️ 您的問題似乎與醫療資料庫無關，請輸入與病患、看診紀錄或處方相關的查詢。"
        }

    # 定義黑名單，使用正規表達式確保是獨立關鍵字（避免誤擋欄位名或資料表名）
    forbidden_words = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE', 'EXEC', 'EXECUTE', 'GRANT', 'REVOKE']

    for word in forbidden_words:
        pattern = r'\b' + word + r'\b'
        if re.search(pattern, sql_upper):
            return {
                "status": "danger",
                "safe_sql": "",
                "message": f"⚠️ 資安系統攔截：偵測到禁用指令 '{word}'，本系統僅允許查詢操作。"
            }

    # 嚴格白名單：必須以 SELECT 開頭
    if not sql_upper.startswith('SELECT'):
        return {
            "status": "danger",
            "safe_sql": "",
            "message": "⚠️ 資安系統攔截：本系統僅允許執行 SELECT 查詢指令。"
        }

    # 檢測通過
    return {
        "status": "safe",
        "safe_sql": sql_stripped,
        "message": "✅ 資安檢測通過，允許執行查詢。"
    }
