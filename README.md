# 醫療 Text-to-SQL 智能查詢系統（複現版）

使用者用自然語言提問，Dify 工作流中的 LLM（Gemini）轉成 SQL，經兩層安全檢查後由 Flask API 在 MySQL 執行並回傳結果。
資料庫內容**全部為虛構測試資料**。

## 架構

```
使用者提問 (user_query)
   │
   ▼
┌──────────────────── Dify 工作流 ────────────────────┐
│ 開始 → LLM(Gemini, temp 0) → 資安攔截(Python) → HTTP 請求 → 輸出 │
│                 產生 SQL       黑名單/SELECT 白名單    POST /execute_sql  message / safe_sql / db_result │
└───────────────────────────────────┬─────────────────┘
                                    │ Docker network（docker_default）
                                    ▼
                          flask-api:5000（第二道防線）
                          單一語句 / 禁註解 / 禁危險函式 / 自動 LIMIT / 逾時
                                    │ 唯讀帳號（僅 SELECT）
                                    ▼
                               mysql:3306  meddb
                    Patients · ClinicalRecords · Medications · Prescriptions
```

## 檔案

| 路徑 | 說明 |
|---|---|
| `dify_llm_system_prompt.txt` | Dify LLM 節點系統提示詞（原文） |
| `dify_security_code.py` | Dify 資安攔截程式碼節點（原文） |
| `db/init/01_schema.sql` | 4 張資料表（依提示詞 Schema） |
| `db/init/02_seed.sql` | 虛構資料：20 病患、38 看診、10 種藥、52 處方（由 `scripts/gen_seed.py` 產生） |
| `db/init/03_readonly_user.sh` | 建立只有 SELECT 權限的唯讀帳號 |
| `api/db_api.py` | Flask API：`POST /execute_sql`、`GET /health` |
| `docker-compose.yml` | `mysql` + `flask-api` |
| `docker-compose.dify.yml` | 疊加檔：讓 `flask-api` 加入自架 Dify 的 network |
| `tests/` | pytest：資安節點 + API 端到端測試（SQLite 取代 MySQL，免 Docker） |
| `scripts/eval_report.py` | 離線評估，輸出 `docs/eval_results.md` |
| `scripts/smoke_docker.py` | 對 Docker 版 API（真實 MySQL）跑全部案例＋查詢逾時測試 |
| `scripts/eval_dify.py` | 線上評估（實際呼叫 Dify 工作流 + LLM），輸出 `docs/eval_dify_results.md` |

## API 規格

`POST /execute_sql`，body：`{"sql": "SELECT ..."}`

成功（HTTP 200）：
```json
{"status": "success", "sql": "SELECT ... LIMIT 200", "columns": ["PatientID", "Gender"],
 "rows": [["A123456789", "男"]], "row_count": 1, "truncated": false}
```
其他結果（同樣是 HTTP 200，看 `status`）：
```json
{"status": "skipped",  "message": "未執行查詢：沒有收到 SQL（上游資安節點已攔截或判定問題無關）"}
{"status": "rejected", "message": "SQL 被拒絕：不允許一次執行多條 SQL 語句"}
{"status": "error",    "message": "查詢執行失敗：OperationalError: ..."}
```
- `skipped`：`sql` 為空字串，代表 Dify 資安節點已攔截（工作流沒有條件分支，攔截時仍會呼叫 API）
- `rejected`：第二道防線拒絕（多語句、註解、非 SELECT、`LOAD_FILE`/`OUTFILE`/`SLEEP`/`SHOW` 等）
- `error`：資料庫執行失敗（語法錯、逾時、連線失敗）
- 只有請求格式錯誤（不是 JSON、沒有 `sql` 字串）才回 HTTP 400

> 為什麼不用 4xx/5xx：實測 Dify 的 HTTP 節點收到 4xx/5xx 會把整個工作流判定 failed，
> 資安節點的攔截訊息就到不了輸出節點。改成 200 + `status` 後，攔截案例工作流為 succeeded 並正確顯示訊息。
- 沒有 `LIMIT` 會自動補 `LIMIT 200`（`MAX_ROWS`），且最多回傳 200 筆；超過時 `truncated: true`
- MySQL 端 `MAX_EXECUTION_TIME=5000` 毫秒（`QUERY_TIMEOUT_MS`）

## 本機測試（不需要 Docker）

```bash
python -m venv .venv
```
```bash
.venv\Scripts\pip install -r api/requirements.txt pytest
```
```bash
.venv\Scripts\python -m pytest -q
```
```bash
.venv\Scripts\python scripts/eval_report.py
```

## 用 Docker 啟動

1. 複製 `.env.example` 為 `.env`，自行填入 `MYSQL_ROOT_PASSWORD`、`MYSQL_READONLY_PASSWORD`（不要提交 `.env`）。
2. 只啟動資料庫與 API：
   ```bash
   docker compose up -d --build
   ```
3. 驗證：
   ```bash
   curl http://localhost:5000/health
   ```
   ```bash
   curl -X POST http://localhost:5000/execute_sql -H "Content-Type: application/json" -d "{\"sql\": \"SELECT * FROM Medications\"}"
   ```
   全部案例（含真實 MySQL 逾時中止）：`python scripts/smoke_docker.py`
4. 驗證唯讀帳號真的不能寫入（應出現 `command denied`）：
   ```bash
   docker compose exec mysql sh -c "mysql -u\$MYSQL_READONLY_USER -p\$MYSQL_READONLY_PASSWORD meddb -e 'DELETE FROM Prescriptions'"
   ```

> 容器 MySQL 對主機開在 `127.0.0.1:3307`（`MYSQL_HOST_PORT`），避免與本機已裝的 MySQL 衝突；容器之間仍用 `mysql:3306`。

> 重新初始化資料庫（改了 schema/seed 後）：`docker compose down -v` 會**刪除資料庫 volume**，再 `up` 即重建。

## 接上自架 Dify

1. 依 Dify 官方文件取得 `docker` 資料夾（Dify GitHub repo 的 `docker/`），`cp .env.example .env` 後 `docker compose up -d`。
   預設 compose 專案名為 `docker`，network 為 `docker_default`；用 `docker network ls` 確認，不同時改 `.env` 的 `DIFY_NETWORK`。
   **必要**：Dify 的 HTTP 節點經 `ssrf_proxy` 轉送，預設拒絕所有內網位址。在 Dify 的 `docker/.env` 加上
   `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=flask-api`（只放行這個容器名稱），否則 HTTP 節點會被擋。
   （已驗證版本：Dify 1.18.0）
2. 啟動本專案並加入 Dify network：
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dify.yml up -d --build
   ```
3. 在 Dify 介面（預設 `http://localhost`）建立管理員帳號 → 設定 → 模型供應商 → 安裝 Gemini 並**自行輸入 API 金鑰**。
4. 匯入工作流：工作室 →「匯入 DSL 檔案」選擇 `dify/text2sql_workflow.dsl.yml`（從 Dify Cloud 匯出的原始工作流備份）。
   若沒有 DSL，依下列節點手動重建：
   - **開始**：變數 `user_query`（文字、必填、最長 256）
   - **LLM**：Gemini（`gemini-3-flash-preview` 或可用的 Flash 模型），temperature 0；SYSTEM 貼 `dify_llm_system_prompt.txt`，最後的 `{{user_query}}` 改成插入開始節點變數；USER 訊息填 `{{#開始.user_query#}}`
   - **資安攔截**（程式碼，Python3）：輸入 `sql_input` = LLM 的 `text`；貼上 `dify_security_code.py`；輸出 `status`、`safe_sql`、`message`（皆 String）
   - **HTTP 請求**：`POST http://flask-api:5000/execute_sql`，Header `Content-Type: application/json`，Body JSON `{"sql": "{{資安攔截.safe_sql}}"}`，重試 3 次、間隔 100ms
   - **結束**：`message`、`safe_sql`、`db_result`（HTTP 節點 `body`）
5. 測試：在工作流「執行」輸入「幫我找有服用Amlodipine的病患有哪些？」。

### 不自架 Dify（使用 Dify Cloud）

Dify Cloud 連不到 Docker 內部名稱 `flask-api`。需把 API 暴露到公網（例如 ngrok：`ngrok http 5000`），
再把 HTTP 節點 URL 改成 `https://<ngrok 網址>/execute_sql`。公開暴露時建議另加驗證（例如 API key header）。

### 網路排查

| 症狀 | 檢查 |
|---|---|
| HTTP 節點 `Name or service not known` | `docker network inspect docker_default` 是否有 `flask-api`；是否用了疊加檔啟動 |
| 連線被拒 / 403（自架 Dify） | Dify 的 HTTP 節點經 `ssrf_proxy`（squid）轉送；預設拒絕內網位址。確認 Dify `.env` 有 `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=flask-api`，改完要 `docker compose up -d ssrf_proxy` 重建；`docker compose logs ssrf_proxy` 可看是否 `TCP_DENIED` |
| 攔截類問題整個工作流 failed（`Request failed with status code 400`） | 舊版 API 對空 SQL 回 400 所致；已改為 200 + `status: skipped`，重新 `up -d --build flask-api` |
| LLM 節點 `429 RESOURCE_EXHAUSTED` | Gemini 免費版每分鐘 5 次；手動測試放慢，`eval_dify.py` 已內建 13 秒間隔與重試 |
| 中文亂碼 | MySQL 已設 `utf8mb4`；API 回傳 `ensure_ascii=False` |

## 評估

- 離線（無 LLM）：`scripts/eval_report.py` → [docs/eval_results.md](docs/eval_results.md)，33 個案例涵蓋正常/跨表查詢、無關問題、空輸入、危險指令、多語句、SQL 注入、格式錯誤。
- 線上（含 LLM）：Dify 應用 → 發布 →「存取點 → 後端服務 API → API 金鑰」建立金鑰，填入 `.env` 的 `DIFY_API_KEY` 後執行 `scripts/eval_dify.py` → [docs/eval_dify_results.md](docs/eval_dify_results.md)。
  - `python scripts/eval_dify.py --only-failed`：只重跑結果表中 ❌ 的題目，其餘保留並合併計分
  - Gemini 免費版限制：每分鐘 5 次、每個模型**每天 20 次**（太平洋時間午夜重置，約台灣時間 15:00–16:00）。腳本已內建 13 秒間隔、每分鐘額度重試；撞到每日額度會立即停止，不覆蓋未跑的題目
  - Dify 執行紀錄中的 `total_price` 只是依牌價估算的等值成本，免費金鑰不會扣款
