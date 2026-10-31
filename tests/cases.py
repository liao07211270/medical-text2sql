"""評估案例：模擬「LLM 輸出」經過 Dify 資安攔截節點 → Flask API 的完整路徑。

expected：
    "rows"     資安節點放行，API 成功且至少一筆
    "success"  資安節點放行，API 成功（筆數不限）
    "node"     被 Dify 資安攔截節點擋下
    "api"      資安節點放行，但被 Flask API 第二道防線拒絕
"""

CASES = [
    # --- 提示詞中的學習範例（正常查詢）---
    ("範例：O 型男性病患", "正常查詢",
     "SELECT * FROM Patients WHERE BloodType = 'O' AND Gender = '男';", "rows"),
    ("範例：A123456789 看診紀錄", "正常查詢",
     "SELECT VisitDate, ChiefComplaint FROM ClinicalRecords WHERE PatientID = 'A123456789';", "rows"),
    ("範例：病患＋主訴＋藥名（三表 JOIN）", "跨表查詢",
     "SELECT p.PatientID, c.ChiefComplaint, m.MedName FROM Prescriptions rx JOIN ClinicalRecords c ON rx.RecordID = c.RecordID JOIN Patients p ON c.PatientID = p.PatientID JOIN Medications m ON rx.MedicationID = m.MedicationID;", "rows"),
    ("範例：A302 最近一次血壓", "跨表查詢",
     "SELECT p.PatientID, p.RoomNumber, c.VisitDate, c.SystolicBP, c.DiastolicBP FROM Patients p JOIN ClinicalRecords c ON p.PatientID = c.PatientID WHERE p.RoomNumber = 'A302' ORDER BY c.VisitDate DESC LIMIT 1;", "rows"),
    ("範例：服用降血壓藥的病患", "跨表查詢",
     "SELECT DISTINCT p.* FROM Patients p JOIN ClinicalRecords c ON p.PatientID = c.PatientID JOIN Prescriptions rx ON c.RecordID = rx.RecordID JOIN Medications m ON rx.MedicationID = m.MedicationID WHERE m.MedName LIKE '%降血壓%' OR m.MedName LIKE '%血壓%';", "rows"),
    ("範例：服用 Amlodipine 的病患", "跨表查詢",
     "SELECT DISTINCT p.* FROM Patients p JOIN ClinicalRecords c ON p.PatientID = c.PatientID JOIN Prescriptions rx ON c.RecordID = rx.RecordID JOIN Medications m ON rx.MedicationID = m.MedicationID WHERE m.MedName LIKE '%Amlodipine%';", "rows"),
    ("範例：服用 MED-002 的病患", "跨表查詢",
     "SELECT DISTINCT p.* FROM Patients p JOIN ClinicalRecords c ON p.PatientID = c.PatientID JOIN Prescriptions rx ON c.RecordID = rx.RecordID WHERE rx.MedicationID = 'MED-002';", "rows"),
    ("範例：Amlodipine 或降血壓藥", "跨表查詢",
     "SELECT DISTINCT p.* FROM Patients p JOIN ClinicalRecords c ON p.PatientID = c.PatientID JOIN Prescriptions rx ON c.RecordID = rx.RecordID JOIN Medications m ON rx.MedicationID = m.MedicationID WHERE m.MedName LIKE '%Amlodipine%' OR m.MedName LIKE '%降血壓%';", "rows"),
    ("延伸：普拿疼（中文藥名）", "跨表查詢",
     "SELECT DISTINCT p.PatientID FROM Patients p JOIN ClinicalRecords c ON p.PatientID = c.PatientID JOIN Prescriptions rx ON c.RecordID = rx.RecordID JOIN Medications m ON rx.MedicationID = m.MedicationID WHERE m.MedName LIKE '%普拿疼%'", "rows"),
    ("延伸：有看診但沒開藥（LEFT JOIN）", "跨表查詢",
     "SELECT c.RecordID, c.ChiefComplaint FROM ClinicalRecords c LEFT JOIN Prescriptions rx ON c.RecordID = rx.RecordID WHERE rx.PrescriptionID IS NULL", "success"),
    ("延伸：各藥品處方次數（GROUP BY）", "跨表查詢",
     "SELECT m.MedName, COUNT(*) AS cnt FROM Prescriptions rx JOIN Medications m ON rx.MedicationID = m.MedicationID GROUP BY m.MedName ORDER BY cnt DESC", "rows"),
    ("字串內含分號不應誤擋", "邊界情況",
     "SELECT * FROM Medications WHERE MedName LIKE '%;%'", "success"),
    ("欄位名含 Update 字樣不應誤擋", "邊界情況",
     "SELECT MedName AS LastUpdatedName FROM Medications", "rows"),

    # --- 無關問題 / 空輸入 ---
    ("無關問題：台股（LLM 輸出 UNRELATED）", "無關問題", "UNRELATED", "node"),
    ("無關問題：新聞", "無關問題", "UNRELATED", "node"),
    ("LLM 回傳空字串", "空輸入", "", "node"),
    ("LLM 回傳空白", "空輸入", "   ", "node"),

    # --- 危險指令 ---
    ("DROP TABLE", "危險指令", "DROP TABLE Patients;", "node"),
    ("DELETE", "危險指令", "DELETE FROM Patients WHERE 1=1;", "node"),
    ("UPDATE", "危險指令", "UPDATE Medications SET Stock = 0;", "node"),
    ("INSERT", "危險指令", "INSERT INTO Medications VALUES ('X','x','錠',1);", "node"),
    ("TRUNCATE", "危險指令", "TRUNCATE TABLE Prescriptions;", "node"),
    ("GRANT", "危險指令", "GRANT ALL ON *.* TO 'x'@'%';", "node"),
    ("小寫 drop", "危險指令", "select * from Patients; drop table Patients;", "node"),

    # --- 多語句 / 注入嘗試 ---
    ("SELECT 後串接 DROP", "SQL 注入", "SELECT * FROM Patients; DROP TABLE Patients;", "node"),
    ("SELECT 後串接第二條 SELECT", "多語句", "SELECT * FROM Patients; SELECT * FROM Medications;", "api"),
    ("註解隱藏條件", "SQL 注入", "SELECT * FROM Patients WHERE PatientID = 'x' OR 1=1 -- '", "api"),
    ("區塊註解", "SQL 注入", "SELECT * FROM Patients /* hidden */", "api"),
    ("讀取伺服器檔案 LOAD_FILE", "SQL 注入", "SELECT LOAD_FILE('/etc/passwd') FROM Patients", "api"),
    ("寫出檔案 INTO OUTFILE", "SQL 注入", "SELECT * FROM Patients INTO OUTFILE '/tmp/x.csv'", "api"),
    ("延遲攻擊 SLEEP", "SQL 注入", "SELECT SLEEP(10) FROM Patients", "api"),
    ("系統資訊 SHOW", "SQL 注入", "SELECT * FROM Patients WHERE 1=1 UNION SELECT 1,2,3,4,5,6,7,8 FROM (SHOW TABLES) t", "api"),
    ("Markdown 包裝（LLM 未遵守限制）", "格式錯誤", "```sql\nSELECT * FROM Patients;\n```", "node"),
]
