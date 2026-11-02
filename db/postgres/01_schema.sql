BEGIN;

CREATE SCHEMA IF NOT EXISTS healthcare;

CREATE TABLE IF NOT EXISTS healthcare.region (
    region_code varchar(12) PRIMARY KEY,
    region_name varchar(100) NOT NULL,
    parent_region_code varchar(12) REFERENCES healthcare.region(region_code)
);

CREATE TABLE IF NOT EXISTS healthcare.medical_org (
    org_code varchar(32) PRIMARY KEY,
    org_name varchar(200) NOT NULL,
    org_level varchar(20) NOT NULL,
    org_type varchar(40) NOT NULL,
    region_code varchar(12) NOT NULL REFERENCES healthcare.region(region_code),
    active boolean NOT NULL DEFAULT true,
    opened_on date
);

CREATE TABLE IF NOT EXISTS healthcare.diagnosis (
    diagnosis_code varchar(20) PRIMARY KEY,
    diagnosis_name varchar(200) NOT NULL,
    diagnosis_category varchar(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS healthcare.medical_settlement (
    settlement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    settlement_no varchar(40) NOT NULL UNIQUE,
    org_code varchar(32) NOT NULL REFERENCES healthcare.medical_org(org_code),
    patient_ref varchar(64) NOT NULL,
    diagnosis_code varchar(20) REFERENCES healthcare.diagnosis(diagnosis_code),
    settlement_date date NOT NULL,
    medical_type varchar(20) NOT NULL CHECK (medical_type IN ('inpatient', 'outpatient')),
    settlement_status varchar(20) NOT NULL CHECK (settlement_status IN ('valid', 'cancelled')),
    total_fee numeric(14,2) NOT NULL CHECK (total_fee >= 0),
    fund_pay_amount numeric(14,2) NOT NULL CHECK (fund_pay_amount >= 0),
    personal_account_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (personal_account_amount >= 0),
    cash_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (cash_amount >= 0),
    cancelled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (fund_pay_amount + personal_account_amount + cash_amount <= total_fee + 0.02)
);

CREATE TABLE IF NOT EXISTS healthcare.settlement_detail (
    detail_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    settlement_id bigint NOT NULL REFERENCES healthcare.medical_settlement(settlement_id),
    item_category varchar(30) NOT NULL CHECK (item_category IN ('drug', 'material', 'service', 'exam')),
    item_name varchar(200) NOT NULL,
    quantity numeric(12,2) NOT NULL CHECK (quantity > 0),
    unit_price numeric(14,2) NOT NULL CHECK (unit_price >= 0),
    detail_amount numeric(14,2) NOT NULL CHECK (detail_amount >= 0)
);

CREATE INDEX IF NOT EXISTS idx_settlement_date ON healthcare.medical_settlement(settlement_date);
CREATE INDEX IF NOT EXISTS idx_settlement_org_date ON healthcare.medical_settlement(org_code, settlement_date);
CREATE INDEX IF NOT EXISTS idx_settlement_query_filters ON healthcare.medical_settlement(medical_type, settlement_status, settlement_date);
CREATE INDEX IF NOT EXISTS idx_settlement_diagnosis ON healthcare.medical_settlement(diagnosis_code);
CREATE INDEX IF NOT EXISTS idx_detail_settlement ON healthcare.settlement_detail(settlement_id);

COMMENT ON SCHEMA healthcare IS 'SQLPilot 医保分析测试数据域';
COMMENT ON TABLE healthcare.region IS '行政区划维表';
COMMENT ON COLUMN healthcare.region.region_code IS '行政区划编码';
COMMENT ON COLUMN healthcare.region.region_name IS '行政区划名称';
COMMENT ON TABLE healthcare.medical_org IS '医疗机构维表，一家机构一行';
COMMENT ON COLUMN healthcare.medical_org.org_code IS '医疗机构唯一编码';
COMMENT ON COLUMN healthcare.medical_org.org_name IS '医疗机构名称';
COMMENT ON COLUMN healthcare.medical_org.org_level IS '医疗机构等级，如三级甲等、三级乙等、二级甲等';
COMMENT ON COLUMN healthcare.medical_org.org_type IS '医疗机构类型，如综合医院、专科医院、社区卫生服务中心';
COMMENT ON TABLE healthcare.diagnosis IS '诊断维表，使用测试诊断编码';
COMMENT ON TABLE healthcare.medical_settlement IS '医保结算事实表，一次结算一行';
COMMENT ON COLUMN healthcare.medical_settlement.settlement_date IS '结算日期，月度统计和同比均以此字段为准';
COMMENT ON COLUMN healthcare.medical_settlement.medical_type IS '就医类型：inpatient=住院，outpatient=门诊';
COMMENT ON COLUMN healthcare.medical_settlement.settlement_status IS '结算状态：valid=有效，cancelled=已撤销；默认统计仅包含有效结算';
COMMENT ON COLUMN healthcare.medical_settlement.total_fee IS '医疗总费用，单位元';
COMMENT ON COLUMN healthcare.medical_settlement.fund_pay_amount IS '医保基金支付金额，单位元；医保基金使用情况默认使用本字段';
COMMENT ON COLUMN healthcare.medical_settlement.patient_ref IS '脱敏患者标识，仅用于测试，不代表真实个人';
COMMENT ON TABLE healthcare.settlement_detail IS '医保结算费用明细事实表，一次结算可对应多条药品、材料、服务或检查明细';
COMMENT ON COLUMN healthcare.settlement_detail.detail_amount IS '明细金额，单位元';

COMMIT;
