-- 醫療 Text-to-SQL 資料庫結構
-- 依 Dify LLM 節點系統提示詞中的 Schema 建立（欄位、型別、COMMENT、外鍵保持一致）

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS meddb DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE meddb;

-- 1. 病患基本資料表 (Patients)
CREATE TABLE Patients (
    PatientID VARCHAR(20) PRIMARY KEY COMMENT '病患身分證字號',
    Gender VARCHAR(10) COMMENT '性別',
    BirthDate DATE COMMENT '出生日期',
    BloodType VARCHAR(5) COMMENT '血型',
    RoomNumber VARCHAR(10) COMMENT '病房號碼',
    Height DECIMAL(5,2) COMMENT '身高(cm)',
    Weight DECIMAL(5,2) COMMENT '體重(kg)',
    Phone VARCHAR(15) COMMENT '手機號碼'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 臨床看診紀錄表 (ClinicalRecords)
CREATE TABLE ClinicalRecords (
    RecordID INT AUTO_INCREMENT PRIMARY KEY COMMENT '看診紀錄流水號',
    PatientID VARCHAR(20) COMMENT '病患身分證字號',
    VisitDate DATETIME COMMENT '就醫日期時間',
    ChiefComplaint TEXT COMMENT '主訴症狀/病患自述',
    SystolicBP INT COMMENT '收縮壓',
    DiastolicBP INT COMMENT '舒張壓',
    Pulse INT COMMENT '脈搏',
    FOREIGN KEY (PatientID) REFERENCES Patients(PatientID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 藥品字典表 (Medications)
CREATE TABLE Medications (
    MedicationID VARCHAR(20) PRIMARY KEY COMMENT '藥品代碼',
    MedName VARCHAR(100) NOT NULL COMMENT '藥品名稱',
    Unit VARCHAR(20) COMMENT '單位',
    Stock INT COMMENT '庫存量'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. 處方明細表 (Prescriptions)
CREATE TABLE Prescriptions (
    PrescriptionID INT AUTO_INCREMENT PRIMARY KEY COMMENT '處方流水號',
    RecordID INT COMMENT '對應的看診紀錄流水號',
    MedicationID VARCHAR(20) COMMENT '藥品代碼',
    Dosage VARCHAR(50) COMMENT '用量',
    Frequency VARCHAR(50) COMMENT '頻率',
    Days INT COMMENT '開立天數',
    FOREIGN KEY (RecordID) REFERENCES ClinicalRecords(RecordID),
    FOREIGN KEY (MedicationID) REFERENCES Medications(MedicationID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
