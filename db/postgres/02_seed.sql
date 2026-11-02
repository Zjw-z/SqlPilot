BEGIN;

TRUNCATE TABLE healthcare.settlement_detail, healthcare.medical_settlement, healthcare.diagnosis, healthcare.medical_org, healthcare.region RESTART IDENTITY CASCADE;

INSERT INTO healthcare.region(region_code, region_name, parent_region_code) VALUES
('330100', '杭州市', NULL),
('330102', '上城区', '330100'),
('330105', '拱墅区', '330100'),
('330106', '西湖区', '330100');

INSERT INTO healthcare.medical_org(org_code, org_name, org_level, org_type, region_code, opened_on) VALUES
('H001', '市第一人民医院', '三级甲等', '综合医院', '330102', '1952-01-01'),
('H002', '市中西医结合医院', '三级甲等', '综合医院', '330105', '1960-05-01'),
('H003', '市儿童医院', '三级甲等', '专科医院', '330106', '1988-06-01'),
('H004', '城北医院', '三级乙等', '综合医院', '330105', '1996-03-01'),
('H005', '西湖区人民医院', '二级甲等', '综合医院', '330106', '2001-09-01'),
('H006', '湖滨社区卫生服务中心', '一级', '社区卫生服务中心', '330102', '2008-01-01');

INSERT INTO healthcare.diagnosis(diagnosis_code, diagnosis_name, diagnosis_category) VALUES
('D001', '高血压', '循环系统疾病'),
('D002', '糖尿病', '内分泌疾病'),
('D003', '肺炎', '呼吸系统疾病'),
('D004', '骨折', '损伤与中毒'),
('D005', '急性阑尾炎', '消化系统疾病');

WITH months AS (
    SELECT d::date AS month_start
    FROM generate_series('2025-01-01'::date, '2026-08-01'::date, interval '1 month') AS d
), generated AS (
    SELECT
        o.org_code,
        m.month_start,
        n,
        row_number() OVER (ORDER BY m.month_start, o.org_code, n) AS seq,
        CASE WHEN n <= 6 THEN 'inpatient' ELSE 'outpatient' END AS medical_type,
        CASE WHEN n = 8 AND extract(month FROM m.month_start)::int IN (3, 7) THEN 'cancelled' ELSE 'valid' END AS settlement_status,
        (1800 + substring(o.org_code FROM 2)::int * 260 + n * 95) AS base_fee,
        CASE
            WHEN extract(year FROM m.month_start) = 2025 THEN 1.00
            WHEN extract(month FROM m.month_start) = 1 THEN 1.05
            WHEN extract(month FROM m.month_start) = 2 THEN 1.12
            WHEN extract(month FROM m.month_start) = 3 THEN 1.28
            WHEN extract(month FROM m.month_start) = 4 THEN 1.08
            WHEN extract(month FROM m.month_start) = 5 THEN 1.35
            WHEN extract(month FROM m.month_start) = 6 THEN 0.97
            WHEN extract(month FROM m.month_start) = 7 THEN 1.18
            ELSE 1.42
        END AS yoy_factor
    FROM healthcare.medical_org o
    CROSS JOIN months m
    CROSS JOIN generate_series(1, 8) AS n
)
INSERT INTO healthcare.medical_settlement(
    settlement_no, org_code, patient_ref, diagnosis_code, settlement_date,
    medical_type, settlement_status, total_fee, fund_pay_amount,
    personal_account_amount, cash_amount, cancelled_at
)
SELECT
    'TEST-' || to_char(month_start, 'YYYYMM') || '-' || org_code || '-' || lpad(n::text, 2, '0'),
    org_code,
    'PATIENT-' || lpad(((seq - 1) % 120 + 1)::text, 4, '0'),
    'D00' || (((seq - 1) % 5) + 1),
    month_start + ((n * 3 + substring(org_code FROM 2)::int) % 25),
    medical_type,
    settlement_status,
    round((base_fee * yoy_factor)::numeric, 2),
    round((base_fee * yoy_factor * CASE WHEN medical_type = 'inpatient' THEN 0.68 ELSE 0.55 END)::numeric, 2),
    round((base_fee * yoy_factor * 0.12)::numeric, 2),
    round((base_fee * yoy_factor * CASE WHEN medical_type = 'inpatient' THEN 0.20 ELSE 0.33 END)::numeric, 2),
    CASE WHEN settlement_status = 'cancelled' THEN month_start + interval '27 days' END
FROM generated;

INSERT INTO healthcare.settlement_detail(settlement_id, item_category, item_name, quantity, unit_price, detail_amount)
SELECT settlement_id, 'service', '诊疗服务费', 1, round(total_fee * 0.45, 2), round(total_fee * 0.45, 2)
FROM healthcare.medical_settlement
UNION ALL
SELECT settlement_id, 'drug', '测试药品费用', 1, round(total_fee * 0.35, 2), round(total_fee * 0.35, 2)
FROM healthcare.medical_settlement
UNION ALL
SELECT settlement_id, 'exam', '检验检查费', 1, round(total_fee * 0.20, 2), round(total_fee * 0.20, 2)
FROM healthcare.medical_settlement;

COMMIT;

SELECT count(*) AS organization_count FROM healthcare.medical_org;
SELECT count(*) AS settlement_count FROM healthcare.medical_settlement;
SELECT min(settlement_date) AS min_date, max(settlement_date) AS max_date FROM healthcare.medical_settlement;
