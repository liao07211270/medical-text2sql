"""產生 db/init/02_seed.sql（全部為虛構測試資料，不含任何真實個資）。

固定亂數種子，重跑會得到相同結果：
    python scripts/gen_seed.py
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(20261030)

OUT = Path(__file__).resolve().parent.parent / "db" / "init" / "02_seed.sql"

# 藥品字典：MedName 內含功效關鍵字，讓提示詞中的 LIKE '%降血壓%' 等範例能查到
MEDICATIONS = [
    ("MED-001", "Amlodipine 5mg（降血壓）", "錠", 500),
    ("MED-002", "Acetaminophen 500mg 普拿疼（止痛退燒）", "錠", 1200),
    ("MED-003", "Losartan 50mg（降血壓）", "錠", 300),
    ("MED-004", "Metformin 500mg（降血糖）", "錠", 800),
    ("MED-005", "Ibuprofen 400mg（消炎止痛）", "錠", 600),
    ("MED-006", "Atorvastatin 20mg（降血脂）", "錠", 400),
    ("MED-007", "Omeprazole 20mg（制酸胃藥）", "膠囊", 350),
    ("MED-008", "Amoxicillin 500mg（抗生素）", "膠囊", 450),
    ("MED-009", "Cetirizine 10mg（抗過敏）", "錠", 700),
    ("MED-010", "Aspirin 100mg（抗血小板）", "錠", 900),
]

# 主訴 → 可能開立的藥品
COMPLAINTS = [
    ("頭暈、後頸僵硬，自述血壓偏高", ["MED-001", "MED-003"]),
    ("定期回診追蹤高血壓", ["MED-001", "MED-003", "MED-010"]),
    ("發燒 38.5 度、喉嚨痛", ["MED-002", "MED-008"]),
    ("頭痛兩天，無其他不適", ["MED-002"]),
    ("膝蓋關節疼痛、腫脹", ["MED-005"]),
    ("下背痛，久坐後加劇", ["MED-005", "MED-002"]),
    ("口渴、頻尿，血糖控制不佳", ["MED-004"]),
    ("健檢膽固醇偏高，回診諮詢", ["MED-006"]),
    ("胃悶、胃酸逆流", ["MED-007"]),
    ("咳嗽有痰一週", ["MED-008", "MED-002"]),
    ("打噴嚏、流鼻水、眼睛癢", ["MED-009"]),
    ("胸悶，有心血管疾病家族史", ["MED-010", "MED-006"]),
    ("失眠、睡不好", []),  # 只看診不開藥，用來測試 LEFT JOIN
]

FREQUENCIES = ["QD 每日一次", "BID 每日兩次", "TID 每日三次", "PRN 需要時"]
DOSAGES = {"錠": ["1 錠", "2 錠", "0.5 錠"], "膠囊": ["1 顆"]}
BLOOD_TYPES = ["O", "A", "B", "AB"]
ROOMS = ["A301", "A302", "A303", "B201", "B202", "C105", None]


def fake_id(i: int, gender: str) -> str:
    """虛構身分證字號：格式像身分證，但數字為流水號組成，非真實號碼。"""
    letter = "ABCDEFGH"[i % 8]
    sex_digit = "1" if gender == "男" else "2"
    return f"{letter}{sex_digit}{90000000 + i:08d}"


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main():
    patients = []
    # 固定兩位提示詞範例會用到的病患
    patients.append(("A123456789", "男", "1968-04-12", "O", "A302", 172.5, 78.3, "0900000001"))
    patients.append(("B223456780", "女", "1975-09-03", "A", "A301", 160.2, 55.8, "0900000002"))
    for i in range(3, 21):
        gender = random.choice(["男", "女"])
        pid = fake_id(i, gender)
        birth = datetime(1940, 1, 1) + timedelta(days=random.randint(0, 365 * 62))
        height = round(random.uniform(165, 185) if gender == "男" else random.uniform(150, 170), 1)
        weight = round(random.uniform(55, 95) if gender == "男" else random.uniform(42, 75), 1)
        patients.append((
            pid, gender, birth.strftime("%Y-%m-%d"), random.choice(BLOOD_TYPES),
            random.choice(ROOMS), height, weight, f"09000000{i:02d}",
        ))
    # 確保至少有幾位 O 型男性
    for idx in (4, 9):
        p = list(patients[idx])
        p[1], p[3] = "男", "O"
        p[0] = fake_id(idx + 1, "男")
        patients[idx] = tuple(p)

    records = []
    prescriptions = []
    rec_id = 0
    rx_id = 0
    base = datetime(2026, 1, 5, 9, 0)
    for p_idx, p in enumerate(patients):
        n_visits = 4 if p_idx == 0 else random.randint(1, 3)
        for v in range(n_visits):
            rec_id += 1
            if p_idx == 0:
                # A123456789：高血壓病人，固定開 Amlodipine，最近一次也有血壓
                complaint, meds = COMPLAINTS[v % 2] if v < 3 else COMPLAINTS[3]
                meds = ["MED-001"] + [m for m in meds if m != "MED-001"][:1]
            else:
                complaint, meds = random.choice(COMPLAINTS)
            hypertensive = any(m in ("MED-001", "MED-003") for m in meds)
            sbp = random.randint(140, 168) if hypertensive else random.randint(105, 132)
            dbp = random.randint(88, 102) if hypertensive else random.randint(65, 85)
            visit = base + timedelta(days=random.randint(0, 280) if p_idx else 60 * v,
                                     hours=random.randint(0, 8), minutes=random.choice([0, 15, 30, 45]))
            records.append((rec_id, p[0], visit.strftime("%Y-%m-%d %H:%M:%S"), complaint,
                            sbp, dbp, random.randint(60, 98)))
            chosen = meds if p_idx == 0 else random.sample(meds, k=min(len(meds), random.randint(1, 2)))
            for med in chosen:
                rx_id += 1
                unit = next(m[2] for m in MEDICATIONS if m[0] == med)
                prescriptions.append((rx_id, rec_id, med, random.choice(DOSAGES[unit]),
                                      random.choice(FREQUENCIES), random.choice([3, 7, 14, 28])))

    # 確保 MED-002 至少有兩位病患使用
    used_002 = {r[1] for r in prescriptions if r[2] == "MED-002"}
    if len(used_002) < 2:
        for r in records[5:7]:
            rx_id += 1
            prescriptions.append((rx_id, r[0], "MED-002", "1 錠", "PRN 需要時", 3))

    lines = [
        "-- 虛構測試資料（由 scripts/gen_seed.py 產生，請勿手動修改）",
        "-- 所有身分證字號、電話、病歷皆為虛構，不對應任何真實人物。",
        "SET NAMES utf8mb4;",
        "USE meddb;",
        "",
    ]

    def insert(table, cols, rows):
        lines.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES")
        lines.append(",\n".join("    (" + ", ".join(q(v) for v in r) + ")" for r in rows) + ";")
        lines.append("")

    insert("Patients", ["PatientID", "Gender", "BirthDate", "BloodType", "RoomNumber", "Height", "Weight", "Phone"], patients)
    insert("Medications", ["MedicationID", "MedName", "Unit", "Stock"], MEDICATIONS)
    insert("ClinicalRecords", ["RecordID", "PatientID", "VisitDate", "ChiefComplaint", "SystolicBP", "DiastolicBP", "Pulse"], records)
    insert("Prescriptions", ["PrescriptionID", "RecordID", "MedicationID", "Dosage", "Frequency", "Days"], prescriptions)

    OUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}: {len(patients)} patients, {len(records)} records, {len(prescriptions)} prescriptions")


if __name__ == "__main__":
    main()
