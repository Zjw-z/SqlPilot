BEGIN;

TRUNCATE TABLE
    nhsa.mdcs_fund_setl_list_blood_d, nhsa.mdcs_fund_setl_list_invy_d,
    nhsa.mdcs_fund_setl_list_chrgitm_d, nhsa.mdcs_fund_setl_list_scs_d,
    nhsa.mdcs_fund_setl_list_oprn_d, nhsa.mdcs_fund_setl_list_diag_d,
    nhsa.setl_fee_stt_d, nhsa.fee_list_d, nhsa.mdcs_fund_setl_list_d,
    nhsa.setl_d, nhsa.mdtrt_d, nhsa.hilist_b, nhsa.medins_info_b;

INSERT INTO nhsa.medins_info_b(
    medins_code, local_medins_code, medins_name, medins_abbr, admdvs, addr,
    medins_type, medins_type_name, medinslv, yb_area, vali_flag
) VALUES
('H001','LOCAL-H001','市第一人民医院','市一医院','330100','测试地址1号','01','综合医院','01','330100','1'),
('H002','LOCAL-H002','市中西医结合医院','中西医医院','330100','测试地址2号','01','综合医院','01','330100','1'),
('H003','LOCAL-H003','市儿童医院','儿童医院','330100','测试地址3号','02','专科医院','01','330100','1'),
('H004','LOCAL-H004','城北医院','城北医院','330100','测试地址4号','01','综合医院','02','330100','1'),
('H005','LOCAL-H005','西湖区人民医院','西湖区医院','330100','测试地址5号','01','综合医院','03','330100','1'),
('H006','LOCAL-H006','湖滨社区卫生服务中心','湖滨中心','330100','测试地址6号','03','基层医疗机构','04','330100','1');

CREATE TEMP TABLE nhsa_seed_base ON COMMIT DROP AS
WITH months AS (
    SELECT d::date AS month_start
    FROM generate_series('2025-01-01'::date, '2026-08-01'::date, interval '1 month') d
), orgs AS (
    SELECT medins_code, medins_name, row_number() OVER (ORDER BY medins_code) AS org_no
    FROM nhsa.medins_info_b
), source AS (
    SELECT m.month_start, o.*, n,
           row_number() OVER (ORDER BY m.month_start, o.medins_code, n) AS seq
    FROM months m CROSS JOIN orgs o CROSS JOIN generate_series(1, 8) n
)
SELECT
    'SETL-' || to_char(month_start,'YYYYMM') || '-' || medins_code || '-' || lpad(n::text,2,'0') AS setl_id,
    'MDTRT-' || to_char(month_start,'YYYYMM') || '-' || medins_code || '-' || lpad(n::text,2,'0') AS mdtrt_id,
    medins_code, medins_name, month_start, n, seq,
    'TEST-PSN-' || lpad(((seq - 1) % 150 + 1)::text,4,'0') AS psn_no,
    CASE WHEN n <= 6 THEN '21' ELSE '11' END AS med_type,
    CASE WHEN n = 8 AND extract(month FROM month_start)::int IN (3,7) THEN '0' ELSE '1' END AS vali_flag,
    (2200 + org_no * 310 + n * 105)::numeric AS base_fee,
    CASE WHEN extract(year FROM month_start)=2025 THEN 1.00
         WHEN extract(month FROM month_start)=1 THEN 1.05
         WHEN extract(month FROM month_start)=2 THEN 1.12
         WHEN extract(month FROM month_start)=3 THEN 1.28
         WHEN extract(month FROM month_start)=4 THEN 1.08
         WHEN extract(month FROM month_start)=5 THEN 1.35
         WHEN extract(month FROM month_start)=6 THEN 0.97
         WHEN extract(month FROM month_start)=7 THEN 1.18 ELSE 1.42 END::numeric AS growth_factor
FROM source;

INSERT INTO nhsa.mdtrt_d(mdtrt_id, psn_no, psn_cert_type, certno, psn_name, insu_admdvs,
    fixmedins_code, fixmedins_name, fix_blng_admdvs, begntime, endtime, med_type,
    ipt_otp_no, dscg_maindiag_code, dscg_maindiag_name, inhosp_stas, ipt_days, vali_flag, akc190)
SELECT mdtrt_id, psn_no, '01', 'SYNTH-'||lpad(seq::text,12,'0'), '测试患者'||seq,
    '330100', medins_code, medins_name, '330100',
    to_char(month_start + ((n*2)%20), 'YYYY-MM-DD')||' 08:00:00',
    to_char(month_start + ((n*2)%20) + CASE WHEN med_type='21' THEN 5 ELSE 0 END, 'YYYY-MM-DD')||' 15:00:00',
    med_type, 'NO-'||seq, 'D001', '测试诊断', '0', CASE WHEN med_type='21' THEN 5 ELSE 0 END, vali_flag, '1'
FROM nhsa_seed_base;

INSERT INTO nhsa.setl_d(clr_optins, setl_id, mdtrt_id, psn_no, psn_name, psn_cert_type,
    certno, gend, brdy, insutype, psn_type, insu_admdvs, fixmedins_code, fixmedins_name,
    fix_blng_admdvs, begndate, enddate, setl_time, med_type, medfee_sumamt,
    fulamt_ownpay_amt, overlmt_selfpay, preselfpay_amt, inscp_amt, dedc_std, crt_dedc,
    act_pay_dedc, hifp_pay, hifes_pay, hifmi_pay, hifob_pay, hifdm_pay, maf_pay,
    othfund_pay, fund_pay_sumamt, psn_pay, acct_pay, cash_payamt, refd_setl_flag,
    year, vali_flag, akc190)
SELECT '330100', setl_id, mdtrt_id, psn_no, '测试患者'||seq, '01',
    'SYNTH-'||lpad(seq::text,12,'0'), CASE WHEN seq%2=0 THEN '1' ELSE '2' END,
    '19800101', '310', '11', '330100', medins_code, medins_name, '330100',
    to_char(month_start,'YYYYMMDD'), to_char((month_start + interval '1 month - 1 day')::date,'YYYYMMDD'),
    to_char(month_start + ((n*3)%25), 'YYYY-MM-DD')||' 10:00:00', med_type,
    round(base_fee*growth_factor,2), 0, 0, 0, round(base_fee*growth_factor,2), 0, 0, 0,
    round(base_fee*growth_factor*0.68,2), 0, 0, 0, 0, 0, 0,
    round(base_fee*growth_factor*0.68,2), round(base_fee*growth_factor*0.32,2),
    round(base_fee*growth_factor*0.12,2), round(base_fee*growth_factor*0.20,2),
    CASE WHEN vali_flag='1' THEN '0' ELSE '1' END, extract(year FROM month_start)::int::text, vali_flag, '1'
FROM nhsa_seed_base;

INSERT INTO nhsa.mdcs_fund_setl_list_d(setl_id, fixmedins_name, fixmedins_code, hi_setl_lv,
    psn_no, setl_type, mdtrt_id, dcla_time, psn_name, gend, brdy, age, psn_cert_type,
    certno, insutype, diag_code_cnt, oprn_oprt_code_cnt, inhosp_stas, biz_sn, bill_code,
    billno, setl_begndate, setl_enddate, setl_time, psn_selfpay_amt, psn_ownpay_fee,
    acct_payamt, psn_cashpay, medins_fill_dept, medins_fill_psn, vali_flag, akc190, type)
SELECT setl_id, medins_name, medins_code, '1', psn_no, '1', mdtrt_id,
    to_char(month_start + ((n*3)%25), 'YYYY-MM-DD')||' 11:00:00', '测试患者'||seq,
    CASE WHEN seq%2=0 THEN '1' ELSE '2' END, '19800101', 46, '01',
    'SYNTH-'||lpad(seq::text,12,'0'), '310', 1, 0, '0', 'BIZ-'||seq,
    'TEST-BILL', 'BILL-'||seq, to_char(month_start,'YYYY-MM-DD')||' 00:00:00',
    to_char((month_start + interval '1 month - 1 day')::date,'YYYY-MM-DD')||' 23:59:59',
    to_char(month_start + ((n*3)%25), 'YYYY-MM-DD')||' 10:00:00',
    round(base_fee*growth_factor*0.08,2), 0, round(base_fee*growth_factor*0.12,2),
    round(base_fee*growth_factor*0.20,2), '医保办', '测试填报员', vali_flag, '1',
    CASE WHEN seq%3=0 THEN 'JM' ELSE 'ZG' END
FROM nhsa_seed_base;

INSERT INTO nhsa.mdcs_fund_setl_list_diag_d(setl_list_diag_id, setl_id, diag_type,
    maindiag_flag, diag_code, diag_name, adm_cond_type)
SELECT 'DIAG-'||seq, setl_id, '1', '1',
    CASE seq%4 WHEN 0 THEN 'I10' WHEN 1 THEN 'E11.9' WHEN 2 THEN 'J18.9' ELSE 'K35.8' END,
    CASE seq%4 WHEN 0 THEN '高血压' WHEN 1 THEN '2型糖尿病' WHEN 2 THEN '肺炎' ELSE '急性阑尾炎' END, '1'
FROM nhsa_seed_base;

INSERT INTO nhsa.mdcs_fund_setl_list_chrgitm_d(setl_list_chrgitm_id, setl_id,
    med_chrgitm_type, item_sumamt, item_claa_amt, item_clab_amt, item_ownpay_amt, item_oth_amt)
SELECT 'CHRG-'||seq, setl_id, '01', round(base_fee*growth_factor,2),
    round(base_fee*growth_factor*0.70,2), round(base_fee*growth_factor*0.20,2),
    round(base_fee*growth_factor*0.10,2), 0 FROM nhsa_seed_base;

INSERT INTO nhsa.mdcs_fund_setl_list_invy_d(setl_invy_id, setl_id, fund_pay_type,
    fund_pay_name, fund_payamt)
SELECT 'FUND-'||seq, setl_id, '310100', '基本医疗保险统筹基金',
    round(base_fee*growth_factor*0.68,2) FROM nhsa_seed_base;

INSERT INTO nhsa.setl_fee_stt_d(setl_id, mdtrt_id, psn_no, med_chrgitm_type,
    item_sumamt, item_claa_amt, item_clab_amt, item_ownpay_amt, item_oth_amt, vali_flag)
SELECT setl_id, mdtrt_id, psn_no, '01', round(base_fee*growth_factor,2),
    round(base_fee*growth_factor*0.70,2), round(base_fee*growth_factor*0.20,2),
    round(base_fee*growth_factor*0.10,2), 0, vali_flag FROM nhsa_seed_base;

COMMIT;

SELECT count(*) AS settlement_count FROM nhsa.setl_d;
SELECT min(to_timestamp(setl_time,'YYYY-MM-DD HH24:MI:SS')) AS min_time,
       max(to_timestamp(setl_time,'YYYY-MM-DD HH24:MI:SS')) AS max_time
FROM nhsa.setl_d;
