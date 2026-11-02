from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sqlpilot.db"


def connect(read_only: bool = False) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if read_only and DB_PATH.exists():
        connection = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_demo_database() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS medical_org (
                org_code TEXT PRIMARY KEY,
                org_name TEXT NOT NULL,
                org_level_code TEXT NOT NULL,
                org_level_name TEXT NOT NULL,
                region_code TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settlement (
                settlement_id TEXT PRIMARY KEY,
                org_code TEXT NOT NULL,
                settle_date TEXT NOT NULL,
                total_fee REAL NOT NULL,
                fund_pay_amt REAL NOT NULL,
                medical_type TEXT NOT NULL,
                valid_flag INTEGER NOT NULL,
                cancelled_flag INTEGER NOT NULL,
                FOREIGN KEY (org_code) REFERENCES medical_org(org_code)
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM medical_org").fetchone()[0]:
            return
        db.executemany(
            "INSERT INTO medical_org VALUES (?, ?, ?, ?, ?)",
            [
                ("H001", "上海市第一人民医院", "3A", "三级甲等", "310000"),
                ("H002", "浦东新区中心医院", "3A", "三级甲等", "310115"),
                ("H003", "社区健康服务中心", "1A", "一级甲等", "310115"),
            ],
        )
        rows = []
        for month in range(1, 7):
            for index, org in enumerate(("H001", "H002", "H003"), start=1):
                for visit in range(1, 4):
                    total = 8000 + month * 600 + index * 900 + visit * 100
                    fund = round(total * (0.68 + index * 0.03), 2)
                    rows.append((f"2025{month:02d}{index}{visit}", org, f"2025-{month:02d}-{visit + 5:02d}", total, fund, "21", 1, 0))
        rows.append(("CANCEL001", "H001", "2025-03-10", 99999, 80000, "21", 1, 1))
        db.executemany("INSERT INTO settlement VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

