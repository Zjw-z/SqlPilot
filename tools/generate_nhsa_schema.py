"""Generate PostgreSQL test DDL from the NHSA settlement-list DOCX tables."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document


TABLES = [
    "mdcs_fund_setl_list_d", "mdcs_fund_setl_list_diag_d", "mdcs_fund_setl_list_oprn_d",
    "mdcs_fund_setl_list_scs_d", "mdcs_fund_setl_list_chrgitm_d", "mdcs_fund_setl_list_invy_d",
    "mdcs_fund_setl_list_blood_d", "mdtrt_d", "fee_list_d", "setl_d", "setl_fee_stt_d",
    "hilist_b", "medins_info_b",
]
PRIMARY_KEYS = {
    "mdcs_fund_setl_list_d": "setl_id", "mdcs_fund_setl_list_diag_d": "setl_list_diag_id",
    "mdcs_fund_setl_list_oprn_d": "setl_list_oprn_id", "mdcs_fund_setl_list_scs_d": "setl_list_scs_cutd_id",
    "mdcs_fund_setl_list_chrgitm_d": "setl_list_chrgitm_id", "mdcs_fund_setl_list_invy_d": "setl_invy_id",
    "mdcs_fund_setl_list_blood_d": "setl_list_blood_id", "mdtrt_d": "mdtrt_id",
    "fee_list_d": "bkkp_sn", "setl_d": "setl_id", "hilist_b": "hilist_code",
    "medins_info_b": "medins_code",
}


def pg_type(kind: str, length: str) -> str:
    if kind.strip() == "数字":
        match = re.fullmatch(r"(\d+)(?:,(\d+))?", length.strip())
        return f"numeric({match.group(1)},{match.group(2) or '0'})" if match else "numeric"
    size = int(length.strip()) if length.strip().isdigit() else 500
    return f"varchar({size})"


def quote(value: str) -> str:
    return "'" + value.replace("'", "''").replace("\n", " / ") + "'"


def generate(source: Path) -> str:
    document = Document(source)
    output = ["-- Generated from 医疗保障基金结算清单采集接口规范 V2.3", "BEGIN;", "CREATE SCHEMA IF NOT EXISTS nhsa;", ""]
    for table_index, table_name in enumerate(TABLES, start=1):
        rows = document.tables[table_index].rows
        fields = []
        for row in rows[1:]:
            cells = [cell.text.strip().replace("\xa0", " ") for cell in row.cells]
            if len(cells) < 7 or not cells[2]:
                continue
            field = cells[2].lower()
            required = cells[5] == "是"
            description = cells[6]
            fields.append((field, cells[1], pg_type(cells[3], cells[4]), required, description))
        definitions = []
        for field, _, data_type, _, _ in fields:
            required_key = field == PRIMARY_KEYS.get(table_name) or field in {"setl_id", "mdtrt_id"}
            definitions.append(f"    {field} {data_type}{' NOT NULL' if required_key else ''}")
        pk = PRIMARY_KEYS.get(table_name)
        if pk:
            definitions.append(f"    CONSTRAINT pk_{table_name} PRIMARY KEY ({pk})")
        output.append(f"CREATE TABLE IF NOT EXISTS nhsa.{table_name} (\n" + ",\n".join(definitions) + "\n);")
        output.append(f"COMMENT ON TABLE nhsa.{table_name} IS {quote('医保结算清单规范测试表：' + table_name.upper())};")
        for field, label, _, required, description in fields:
            text = f"{label}；接口必填：{'是' if required else '否'}"
            if description:
                text += f"；{description}"
            output.append(f"COMMENT ON COLUMN nhsa.{table_name}.{field} IS {quote(text)};")
        output.append("")
    output.extend([
        "CREATE INDEX IF NOT EXISTS idx_mdcs_setl_time ON nhsa.mdcs_fund_setl_list_d(setl_time);",
        "CREATE INDEX IF NOT EXISTS idx_mdcs_org_time ON nhsa.mdcs_fund_setl_list_d(fixmedins_code, setl_time);",
        "CREATE INDEX IF NOT EXISTS idx_setl_query ON nhsa.setl_d(fixmedins_code, setl_time, med_type, vali_flag);",
        "CREATE INDEX IF NOT EXISTS idx_fee_setl ON nhsa.fee_list_d(setl_id);",
        "CREATE INDEX IF NOT EXISTS idx_diag_setl ON nhsa.mdcs_fund_setl_list_diag_d(setl_id);",
        "COMMIT;", "",
    ])
    return "\n".join(output)


def generate_dictionary(source: Path) -> str:
    document = Document(source)
    rows = document.tables[14].rows[1:]
    output = [
        "-- Code values from 医疗保障基金结算清单采集接口规范 V2.3",
        "BEGIN;",
        "CREATE TABLE IF NOT EXISTS nhsa.code_dictionary (",
        "    dictionary_name varchar(100) NOT NULL,",
        "    dictionary_label varchar(200) NOT NULL,",
        "    value_code varchar(100) NOT NULL,",
        "    value_name varchar(500) NOT NULL,",
        "    PRIMARY KEY (dictionary_name, value_code)",
        ");",
        "COMMENT ON TABLE nhsa.code_dictionary IS '医保结算清单规范代码字典，用于字段值解释和 Schema RAG';",
        "TRUNCATE TABLE nhsa.code_dictionary;",
        "INSERT INTO nhsa.code_dictionary(dictionary_name,dictionary_label,value_code,value_name) VALUES",
    ]
    values = []
    for row in rows:
        cells = [cell.text.strip().replace("\xa0", " ") for cell in row.cells]
        if len(cells) >= 5 and cells[1] and cells[3]:
            values.append("(" + ",".join(quote(value) for value in cells[1:5]) + ")")
    output.append(",\n".join(values) + ";")
    output.extend(["COMMIT;", "SELECT count(*) AS dictionary_value_count FROM nhsa.code_dictionary;", ""])
    return "\n".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dictionary-output", type=Path)
    args = parser.parse_args()
    args.output.write_text(generate(args.source), encoding="utf-8")
    if args.dictionary_output:
        args.dictionary_output.write_text(generate_dictionary(args.source), encoding="utf-8")
