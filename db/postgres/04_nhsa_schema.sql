-- Generated from 医疗保障基金结算清单采集接口规范 V2.3
BEGIN;
CREATE SCHEMA IF NOT EXISTS nhsa;

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_d (
    setl_id varchar(30) NOT NULL,
    fixmedins_name varchar(200),
    fixmedins_code varchar(30),
    hi_setl_lv varchar(3),
    psn_no varchar(30),
    setl_type varchar(1),
    mdtrt_id varchar(30) NOT NULL,
    medcasno varchar(40),
    dcla_time varchar(20),
    psn_name varchar(100),
    gend varchar(6),
    brdy varchar(8),
    age numeric(3,0),
    age_days numeric(3,0),
    ntly varchar(6),
    naty varchar(3),
    psn_cert_type varchar(6),
    certno varchar(50),
    prfs varchar(6),
    curr_addr_s0 varchar(6),
    curr_addr_s1 varchar(6),
    curr_addr_x varchar(6),
    curr_addr_dz varchar(500),
    emp_name varchar(200),
    emp_addr varchar(500),
    emp_tel varchar(50),
    emp_poscode varchar(6),
    coner_name varchar(100),
    patn_rlts varchar(6),
    coner_addr_s0 varchar(6),
    coner_addr_s1 varchar(6),
    coner_addr_x varchar(6),
    coner_addr_dz varchar(500),
    coner_tel varchar(50),
    insutype varchar(6),
    sp_psn_type varchar(6),
    insu_admdvs varchar(6),
    nwb_adm_type varchar(3),
    nwb_bir_wt varchar(50),
    nwb_adm_wt numeric(6,2),
    opsp_diag_caty varchar(20),
    opsp_mdtrt_time varchar(20),
    ipt_med_type varchar(3),
    adm_way_code varchar(3),
    trt_type varchar(3),
    adm_time varchar(20),
    dscg_time varchar(20),
    adm_caty varchar(6),
    refl_caty varchar(100),
    dscg_caty varchar(6),
    act_ipt_days numeric(10,0),
    otp_wm_diag varchar(500),
    otp_wm_diag_dise_code varchar(20),
    otp_tcm_diag varchar(500),
    otp_tcm_diag_dise_code varchar(20),
    diag_code_cnt numeric(10,0),
    oprn_oprt_code_cnt numeric(10,0),
    vent_used_days numeric(3,0),
    vent_used_h_cnt numeric(2,0),
    vent_used_m_cnt numeric(2,0),
    bfadm_coma_days numeric(3,0),
    bfadm_coma_h_cnt numeric(2,0),
    bfadm_coma_m_cnt numeric(2,0),
    afadm_coma_days numeric(3,0),
    afadm_coma_h_cnt numeric(2,0),
    afadm_coma_m_cnt numeric(2,0),
    spga_nurscare_days numeric(10,0),
    lv1_nurscare_days numeric(10,0),
    scd_nurscare_days numeric(10,0),
    lv3_nurscare_days numeric(10,0),
    dscg_way varchar(3),
    acp_optins_name varchar(100),
    acp_optins_code varchar(30),
    dscg_31days_rinp_flag varchar(3),
    rinp_pup varchar(100),
    chfpdr_name varchar(100),
    chfpdr_code varchar(30),
    respns_name varchar(100),
    respns_code varchar(30),
    inhosp_stas varchar(3),
    biz_sn varchar(50),
    bill_code varchar(500),
    billno varchar(500),
    setl_begndate varchar(20),
    setl_enddate varchar(20),
    setl_time varchar(20),
    psn_selfpay_amt numeric(16,2),
    psn_ownpay_fee numeric(16,2),
    acct_payamt numeric(16,2),
    psn_cashpay numeric(16,2),
    hi_paymtd varchar(3),
    medins_fill_dept varchar(100),
    medins_fill_psn varchar(50),
    vali_flag varchar(3),
    akc190 varchar(3),
    type varchar(3),
    CONSTRAINT pk_mdcs_fund_setl_list_d PRIMARY KEY (setl_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.setl_id IS '结算ID；接口必填：是；数据主键';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.fixmedins_name IS '定点医药机构名称；接口必填：是；按照《医疗机构执业许可证》登记的机构名称填写。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.fixmedins_code IS '定点医药机构编号；接口必填：是；在国家医保局“医保业务编码标准动态维护”平台上，获取的本机构代码。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.hi_setl_lv IS '医保结算等级；接口必填：是；数据字典，详见字典【医保结算等级HI_SETL_LV】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.psn_no IS '医保编号；接口必填：是；参保人在医保系统中的唯一身份代码';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.setl_type IS '清单类型；接口必填：是；数据字典，详见字典【清单类型SETL_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.mdtrt_id IS '就诊ID；接口必填：是；一次诊疗的唯一标识。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.medcasno IS '病案号；接口必填：否；原则上，同一患者在同一医疗机构多次住院应使用同一病案号。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.dcla_time IS '申报时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss定点医疗机构上报医保结算清单的时间。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.psn_name IS '人员姓名；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.gend IS '性别；接口必填：是；数据字典，详见字典【性别GEND】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.brdy IS '出生日期；接口必填：是；格式：YYYYMMDD';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.age IS '年龄；接口必填：是；患者年龄1周岁的实足年龄，为患者出生后按照日历计算的历法年龄，以实足年龄的相应整数填写。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.age_days IS '年龄(天)；接口必填：否；患者实足年龄不足1周岁的（必填），按照实足天龄的相应整数填写。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.ntly IS '国籍；接口必填：否；数据字典，详见字典【国家地区代码NAT_REGN_CODE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.naty IS '民族；接口必填：否；数据字典，详见字典【民族NATY】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.psn_cert_type IS '人员证件类型；接口必填：是；数据字典，详见字典【人员证件类型PSN_CERT_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.certno IS '证件号码；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.prfs IS '职业；接口必填：否；数据字典，详见字典【职业PRFS】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.curr_addr_s0 IS '现住址（省）；接口必填：否；参照中华人民共和国统计局网站发布行政区划代码，GB/T2260-2017。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.curr_addr_s1 IS '现住址（市）；接口必填：否；参照中华人民共和国统计局网站发布行政区划代码，GB/T2260-2017。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.curr_addr_x IS '现住址（县）；接口必填：否；参照中华人民共和国统计局网站发布行政区划代码，GB/T2260-2017。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.curr_addr_dz IS '现住址；接口必填：否；患者近期的常住地址。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.emp_name IS '单位名称；接口必填：否；患者在就诊前的工作单位名称。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.emp_addr IS '单位地址；接口必填：否；患者当前所在的工作单位地址。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.emp_tel IS '单位电话；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.emp_poscode IS '单位邮编；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.coner_name IS '联系人姓名；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.patn_rlts IS '与患者关系；接口必填：否；数据字典，详见字典【与患者关系PATN_RLTS】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.coner_addr_s0 IS '联系人地址（省）；接口必填：否；参照中华人民共和国统计局网站发布行政区划代码，GB/T2260-2017。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.coner_addr_s1 IS '联系人地址（市）；接口必填：否；参照中华人民共和国统计局网站发布行政区划代码，GB/T2260-2017。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.coner_addr_x IS '联系人地址（县）；接口必填：否；参照中华人民共和国统计局网站发布行政区划代码，GB/T2260-2017。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.coner_addr_dz IS '联系人地址；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.coner_tel IS '联系人电话；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.insutype IS '医保类型；接口必填：是；数据字典，详见字典【医保类型INSUTYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.sp_psn_type IS '特殊人员类型；接口必填：否；数据字典，详见字典【特殊人员类型SP_PSN_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.insu_admdvs IS '参保所属医保区划；接口必填：否；患者参加基本医疗保险并缴纳参保费的统筹地区。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.nwb_adm_type IS '新生儿入院类型；接口必填：否；数据字典，详见字典【新生儿入院类型NWB_ADM_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.nwb_bir_wt IS '新生儿出生体重；接口必填：否；单位：克，若多胞胎，以半角逗号隔开，依次填写，新生儿必填。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.nwb_adm_wt IS '新生儿入院体重；接口必填：否；单位：克，新生儿必填';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.opsp_diag_caty IS '门诊慢特病诊断科别；接口必填：否；门诊慢特病必填。数据字典，详见字典【科别CATY】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.opsp_mdtrt_time IS '门诊慢特病就诊时间；接口必填：否；门诊慢特病必填。格式：yyyy-MM-dd HH:mm:ss（门诊慢特病必填）';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.ipt_med_type IS '住院医疗类型；接口必填：否；住院必填。数据字典，详见字典【住院医疗类型IPT_MED_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.adm_way_code IS '入院途径代码；接口必填：否；住院必填。数据字典，详见字典【入院途径代码ADM_WAY_CODE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.trt_type IS '治疗类别；接口必填：否；数据字典，详见字典【治疗类别TRT_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.adm_time IS '入院时间；接口必填：否；住院必填。格式：yyyy-MM-dd  HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.dscg_time IS '出院时间；接口必填：否；住院必填。格式：yyyy-MM-dd  HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.adm_caty IS '入院科别；接口必填：否；住院必填。数据字典，详见字典【科别CATY】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.refl_caty IS '转院科别；接口必填：否；数据字典，详见字典【科别CATY】，如果超过一次以上的转科，依次以半角逗号隔开。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.dscg_caty IS '出院科别；接口必填：否；住院必填。数据字典，详见字典【科别CATY】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.act_ipt_days IS '实际住院天数；接口必填：否；住院必填。患者实际的住院天数，入院日与出院日只计算1天。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.otp_wm_diag IS '门急诊西医诊断；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.otp_wm_diag_dise_code IS '门急诊西医诊断疾病代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.otp_tcm_diag IS '门急诊中医诊断；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.otp_tcm_diag_dise_code IS '门急诊中医诊断疾病代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.diag_code_cnt IS '诊断代码计数；接口必填：是；大于0的整数。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.oprn_oprt_code_cnt IS '手术操作代码计数；接口必填：是；大于等于0的整数。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.vent_used_days IS '呼吸机使用天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.vent_used_h_cnt IS '呼吸机使用小时数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.vent_used_m_cnt IS '呼吸机使用分钟数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.bfadm_coma_days IS '入院前颅脑损伤患者昏迷天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.bfadm_coma_h_cnt IS '入院前颅脑损伤患者昏迷小时数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.bfadm_coma_m_cnt IS '入院前颅脑损伤患者昏迷分钟数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.afadm_coma_days IS '入院后颅脑损伤患者昏迷天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.afadm_coma_h_cnt IS '入院后颅脑损伤患者昏迷小时数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.afadm_coma_m_cnt IS '入院后颅脑损伤患者昏迷分钟数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.spga_nurscare_days IS '特级护理天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.lv1_nurscare_days IS '一级护理天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.scd_nurscare_days IS '二级护理天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.lv3_nurscare_days IS '三级护理天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.dscg_way IS '离院方式；接口必填：否；住院必填。数据字典，详见字典【离院方式DSCG_WAY】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.acp_optins_name IS '拟接收机构名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.acp_optins_code IS '拟接收机构代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.dscg_31days_rinp_flag IS '出院31天内再住院标志；接口必填：否；住院必填。数据字典，详见字典【出院31天内再住院标志DSCG_31DAYS_RINP_FLAG】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.rinp_pup IS '再住院目的；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.chfpdr_name IS '主诊医师姓名；接口必填：否；对于某一参保患者直接负责并且实施具体医疗行为的最高级别医师。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.chfpdr_code IS '主诊医师代码；接口必填：否；为定点医疗机构在国家医保局“医保业务编码标准动态维护”平台上维护获取的医保医师代码。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.respns_name IS '责任护士姓名；接口必填：否；在已开展责任制护理的科室，负责本患者整体护理的责任护士。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.respns_code IS '责任护士代码；接口必填：否；在国家医保局“医保业 务编码标准动态维护”平台上维护获取的医保护士代码。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.inhosp_stas IS '在院状态；接口必填：是；数据字典，详见字典【在院状态INHOSP_STAS】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.biz_sn IS '业务流水号；接口必填：是；医疗卫生机构收费系统自动生成的流水号码。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.bill_code IS '票据代码；接口必填：是；为定点医疗机构按照财政部门票据管理相关规定出具的医疗收费电子票据上的票据代码。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.billno IS '票据号；接口必填：是；为定点医疗机构按照财政部门票据管理相关规定出具的医疗收费电子票据上的票据流水号。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.setl_begndate IS '结算期间开始日期；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.setl_enddate IS '结算期间结束日期；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.setl_time IS '结算时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.psn_selfpay_amt IS '个人自付金额；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.psn_ownpay_fee IS '个人自费费用；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.acct_payamt IS '个人账户支付金额；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.psn_cashpay IS '个人现金支付；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.hi_paymtd IS '医保支付方式；接口必填：否；数据字典，详见字典【医保支付方式HI_PAYMTD】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.medins_fill_dept IS '医疗机构填报部门；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.medins_fill_psn IS '医疗机构填报人；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.akc190 IS 'AKC190；接口必填：是；FIXMEDINS_CODE、AKC190为与医保结算数据关联变量，确保填报完整、准确';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_d.type IS '参保类型；接口必填：是；TYPE列用于存放居民或职工类型。居民为"JM"职工为"ZG"；';

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_diag_d (
    setl_list_diag_id varchar(30) NOT NULL,
    setl_id varchar(30) NOT NULL,
    diag_type varchar(3),
    maindiag_flag varchar(3),
    diag_code varchar(30),
    diag_name varchar(500),
    adm_cond_type varchar(100),
    CONSTRAINT pk_mdcs_fund_setl_list_diag_d PRIMARY KEY (setl_list_diag_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_diag_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_DIAG_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.setl_list_diag_id IS '结算清单诊断ID；接口必填：是；数据主键。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.setl_id IS '结算ID；接口必填：是；关联主表。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.diag_type IS '诊断类别；接口必填：否；住院必填。数据字典，详见字典【诊断类别DIAG_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.maindiag_flag IS '主诊断标志；接口必填：否；住院必填。数据字典，详见字典【主诊断标志MAINDIAG_FLAG】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.diag_code IS '诊断代码；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.diag_name IS '诊断名称；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_diag_d.adm_cond_type IS '入院病情类型；接口必填：否；住院必填。数据字典详见字典【入院病情类型ADM_COND_TYPE】';

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_oprn_d (
    setl_list_oprn_id varchar(30) NOT NULL,
    setl_id varchar(30) NOT NULL,
    main_oprn_flag varchar(3),
    oprn_oprt_name varchar(500),
    oprn_oprt_code varchar(30),
    oprn_oprt_date varchar(8),
    anst_way varchar(6),
    oper_dr_name varchar(100),
    oper_dr_code varchar(20),
    anst_dr_name varchar(100),
    anst_dr_code varchar(20),
    oper_begndate varchar(20),
    oper_enddate varchar(20),
    anst_begndate varchar(20),
    anst_enddate varchar(20),
    CONSTRAINT pk_mdcs_fund_setl_list_oprn_d PRIMARY KEY (setl_list_oprn_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_oprn_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_OPRN_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.setl_list_oprn_id IS '结算清单手术操作ID；接口必填：是；数据主键。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.setl_id IS '结算ID；接口必填：是；关联主表。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.main_oprn_flag IS '主手术操作标志；接口必填：是；数据字典，详见字典【主手术操作标志MAIN_OPRN_FLAG】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oprn_oprt_name IS '手术操作名称；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oprn_oprt_code IS '手术操作代码；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oprn_oprt_date IS '手术操作日期；接口必填：是；格式：YYYYMMDD';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.anst_way IS '麻醉方式；接口必填：否；数据字典，详见字典【麻醉方式ANST_WAY】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oper_dr_name IS '术者医师姓名；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oper_dr_code IS '术者医师代码；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.anst_dr_name IS '麻醉医师姓名；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.anst_dr_code IS '麻醉医师代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oper_begndate IS '手术及操作开始时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss，手术开始时间指手术医师正式开始手术（即：“刀碰皮”）的时间';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.oper_enddate IS '手术及操作结束时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss，手术结束时间指手术医师完成全部手术操作的时间';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.anst_begndate IS '麻醉开始时间；接口必填：否；格式：yyyy-MM-dd HH:mm:ss，麻醉开始时间指麻醉医师正式实施麻醉（全麻指开始麻醉诱导、局麻指开始注射药物）的时间';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_oprn_d.anst_enddate IS '麻醉结束时间；接口必填：否；格式：yyyy-MM-dd HH:mm:ss，麻醉结束时间指手术结束离开手术室的时间';

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_scs_d (
    setl_list_scs_cutd_id varchar(30) NOT NULL,
    setl_id varchar(30) NOT NULL,
    scs_cutd_ward_type varchar(6),
    scs_cutd_inpool_time varchar(20),
    scs_cutd_exit_time varchar(20),
    scs_cutd_sum_dura_h numeric(6,0),
    scs_cutd_sum_dura_mi numeric(6,0),
    CONSTRAINT pk_mdcs_fund_setl_list_scs_d PRIMARY KEY (setl_list_scs_cutd_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_scs_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_SCS_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.setl_list_scs_cutd_id IS '结算清单重症监护ID；接口必填：是；数据主键。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.setl_id IS '结算ID；接口必填：是；关联主表。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.scs_cutd_ward_type IS '重症监护病房类型；接口必填：是；数据字典，详见字典【重症监护病房类型ICU_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.scs_cutd_inpool_time IS '重症监护进入时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.scs_cutd_exit_time IS '重症监护退出时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.scs_cutd_sum_dura_h IS '重症监护合计时长（时）；接口必填：是；单位：小时。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_scs_d.scs_cutd_sum_dura_mi IS '重症监护合计时长（分）；接口必填：是；单位：分钟。';

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_chrgitm_d (
    setl_list_chrgitm_id varchar(30) NOT NULL,
    setl_id varchar(30) NOT NULL,
    med_chrgitm_type varchar(6),
    item_sumamt numeric(16,2),
    item_claa_amt numeric(16,2),
    item_clab_amt numeric(16,2),
    item_ownpay_amt numeric(16,2),
    item_oth_amt numeric(16,2),
    CONSTRAINT pk_mdcs_fund_setl_list_chrgitm_d PRIMARY KEY (setl_list_chrgitm_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_chrgitm_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_CHRGITM_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.setl_list_chrgitm_id IS '结算清单收费项目ID；接口必填：是；数据主键。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.setl_id IS '结算ID；接口必填：是；关联主表。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.med_chrgitm_type IS '医疗收费项目类别；接口必填：是；数据字典，详见字典【医疗收费项目类别MED_CHRGITM_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.item_sumamt IS '项目总金额；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.item_claa_amt IS '项目甲类金额；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.item_clab_amt IS '项目乙类金额；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.item_ownpay_amt IS '项目自费金额；接口必填：是';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_chrgitm_d.item_oth_amt IS '项目其他金额；接口必填：是';

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_invy_d (
    setl_invy_id varchar(30) NOT NULL,
    setl_id varchar(30) NOT NULL,
    fund_pay_type varchar(6),
    fund_pay_name varchar(200),
    fund_payamt numeric(16,2),
    CONSTRAINT pk_mdcs_fund_setl_list_invy_d PRIMARY KEY (setl_invy_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_invy_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_INVY_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_invy_d.setl_invy_id IS '结算清单基金支付ID；接口必填：是；数据主键。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_invy_d.setl_id IS '结算ID；接口必填：是；关联主表。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_invy_d.fund_pay_type IS '基金支付类型；接口必填：是；数据字典，详见字典【基金支付类型FUND_PAY_TYPE】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_invy_d.fund_pay_name IS '基金支付类型名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_invy_d.fund_payamt IS '基金支付金额；接口必填：是';

CREATE TABLE IF NOT EXISTS nhsa.mdcs_fund_setl_list_blood_d (
    setl_list_blood_id varchar(30) NOT NULL,
    setl_id varchar(30) NOT NULL,
    bld_cat varchar(3),
    bld_amt numeric(10,2),
    bld_unt varchar(6),
    CONSTRAINT pk_mdcs_fund_setl_list_blood_d PRIMARY KEY (setl_list_blood_id)
);
COMMENT ON TABLE nhsa.mdcs_fund_setl_list_blood_d IS '医保结算清单规范测试表：MDCS_FUND_SETL_LIST_BLOOD_D';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_blood_d.setl_list_blood_id IS '结算清单输血信息ID；接口必填：是；数据主键。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_blood_d.setl_id IS '结算ID；接口必填：是；关联主表。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_blood_d.bld_cat IS '输血品种；接口必填：是；数据字典，详见字典【输血品种BLD_CAT】';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_blood_d.bld_amt IS '输血量；接口必填：是；给予患者输入体内的各成分血的数量。';
COMMENT ON COLUMN nhsa.mdcs_fund_setl_list_blood_d.bld_unt IS '输血计量单位；接口必填：是';

CREATE TABLE IF NOT EXISTS nhsa.mdtrt_d (
    mdtrt_id varchar(30) NOT NULL,
    medins_setl_id varchar(30),
    psn_no varchar(30),
    psn_insu_rlts_id varchar(20),
    psn_cert_type varchar(6),
    certno varchar(50),
    psn_name varchar(100),
    gend varchar(6),
    naty varchar(3),
    brdy varchar(8),
    age numeric(3,0),
    coner_name varchar(100),
    tel varchar(50),
    addr varchar(500),
    insutype varchar(6),
    psn_type varchar(6),
    cvlserv_flag varchar(3),
    cvlserv_lv varchar(6),
    sp_psn_type varchar(6),
    sp_psn_type_lv varchar(3),
    clct_grde varchar(3),
    flxempe_flag varchar(3),
    nwb_flag varchar(3),
    insu_admdvs varchar(6),
    emp_no varchar(40),
    emp_name varchar(200),
    emp_type varchar(6),
    econ_type varchar(6),
    afil_indu varchar(6),
    afil_rlts varchar(6),
    emp_mgt_type varchar(6),
    pay_loc varchar(6),
    fixmedins_code varchar(30),
    fixmedins_name varchar(200),
    hosp_lv varchar(6),
    fix_blng_admdvs varchar(6),
    lmtpric_hosp_lv varchar(6),
    dedc_hosp_lv varchar(6),
    begntime varchar(20),
    endtime varchar(20),
    mdtrt_cert_type varchar(3),
    mdtrt_cert_no varchar(50),
    med_type varchar(6),
    rloc_type varchar(6),
    ars_year_ipt_flag varchar(3),
    pre_pay_flag varchar(3),
    year varchar(4),
    refl_old_mdtrt_id varchar(30),
    ipt_otp_no varchar(30),
    medrcdno varchar(30),
    chfpdr_code varchar(30),
    chfpdr_name varchar(50),
    adm_diag_dscr varchar(200),
    adm_dept_codg varchar(30),
    adm_dept_name varchar(100),
    adm_bed varchar(30),
    wardarea_bed varchar(50),
    traf_dept_flag varchar(6),
    dscg_maindiag_code varchar(20),
    dscg_maindiag_name varchar(300),
    dscg_dept_codg varchar(30),
    dscg_dept_name varchar(100),
    dscg_bed varchar(30),
    dscg_way varchar(3),
    main_cond_dscr varchar(1000),
    dise_no varchar(30),
    dise_name varchar(500),
    oprn_oprt_code varchar(30),
    oprn_oprt_name varchar(500),
    otp_diag_info varchar(200),
    inhosp_stas varchar(3),
    die_date varchar(8),
    ipt_days numeric(16,0),
    geso_val numeric(2,0),
    birctrl_type varchar(6),
    fetts numeric(3,0),
    fetus_cnt numeric(3,0),
    matn_type varchar(6),
    prey_time varchar(20),
    latechb_flag varchar(3),
    pret_flag varchar(3),
    fpsc_no varchar(50),
    birctrl_matn_date varchar(8),
    cop_flag varchar(3),
    trt_dcla_detl_sn varchar(30),
    ttp_pay_flag varchar(3),
    ttp_pay_prop numeric(5,4),
    memo varchar(500),
    vali_flag varchar(3),
    akc190 varchar(3),
    CONSTRAINT pk_mdtrt_d PRIMARY KEY (mdtrt_id)
);
COMMENT ON TABLE nhsa.mdtrt_d IS '医保结算清单规范测试表：MDTRT_D';
COMMENT ON COLUMN nhsa.mdtrt_d.mdtrt_id IS '就诊ID；接口必填：是；一次诊疗的唯一标识。';
COMMENT ON COLUMN nhsa.mdtrt_d.medins_setl_id IS '医药机构结算ID；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.psn_no IS '人员编号；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.psn_insu_rlts_id IS '人员参保关系ID；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.psn_cert_type IS '人员证件类型；接口必填：是；数据字典，详见字典【人员证件类型PSN_CERT_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.certno IS '证件号码；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.psn_name IS '人员姓名；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.gend IS '性别；接口必填：否；数据字典，详见字典【性别GEND】';
COMMENT ON COLUMN nhsa.mdtrt_d.naty IS '民族；接口必填：否；数据字典，详见字典【民族NATY】';
COMMENT ON COLUMN nhsa.mdtrt_d.brdy IS '出生日期；接口必填：否；YYYYMMDD';
COMMENT ON COLUMN nhsa.mdtrt_d.age IS '年龄；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.coner_name IS '联系人姓名；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.tel IS '联系电话；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.addr IS '联系地址；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.insutype IS '险种类型；接口必填：否；数据字典，详见字典【医保类型INSUTYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.psn_type IS '人员类别；接口必填：否；数据字典，详见字典【人员类别PSN_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.cvlserv_flag IS '公务员标志；接口必填：否；数据字典，详见字典【公务员标志CVLSERV_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.cvlserv_lv IS '公务员等级；接口必填：否；数据字典，详见字典【公务员等级CVLSERV_LV】';
COMMENT ON COLUMN nhsa.mdtrt_d.sp_psn_type IS '特殊人员类型；接口必填：否；数据字典，详见字典【特殊人员类型SP_PSN_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.sp_psn_type_lv IS '特殊人员类型等级；接口必填：否；数据字典，详见字典【特殊人员类型等级SP_PSN_TYPE_LV】';
COMMENT ON COLUMN nhsa.mdtrt_d.clct_grde IS '缴费档次；接口必填：否；数据字典，详见字典【缴费档次CLCT_GRDE】';
COMMENT ON COLUMN nhsa.mdtrt_d.flxempe_flag IS '灵活就业标志；接口必填：否；数据字典，详见字典【灵活就业标志FLXEMPE_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.nwb_flag IS '新生儿标志；接口必填：否；数据字典，详见字典【新生儿标志NWB_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.insu_admdvs IS '参保所属医保区划；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.emp_no IS '单位编号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.emp_name IS '单位名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.emp_type IS '单位类型；接口必填：否；数据字典，详见字典【单位类型EMP_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.econ_type IS '经济类型；接口必填：否；数据字典，详见字典【经济类型ECON_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.afil_indu IS '所属行业；接口必填：否；数据字典，详见字典【所属行业AFIL_INDU】';
COMMENT ON COLUMN nhsa.mdtrt_d.afil_rlts IS '隶属关系；接口必填：否；数据字典，详见字典【隶属关系AFIL_RLTS】';
COMMENT ON COLUMN nhsa.mdtrt_d.emp_mgt_type IS '单位管理类型；接口必填：否；数据字典，详见字典【单位管理类型EMP_MGT_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.pay_loc IS '支付地点类别；接口必填：否；数据字典，详见字典【支付地点类别PAY_LOC】';
COMMENT ON COLUMN nhsa.mdtrt_d.fixmedins_code IS '定点医药机构编号；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.fixmedins_name IS '定点医药机构名称；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.hosp_lv IS '医院等级；接口必填：否；数据字典，详见字典【医院等级HOSP_LV】';
COMMENT ON COLUMN nhsa.mdtrt_d.fix_blng_admdvs IS '定点归属医保区划；接口必填：是';
COMMENT ON COLUMN nhsa.mdtrt_d.lmtpric_hosp_lv IS '限价医院等级；接口必填：否；数据字典，详见字典【限价医院等级LMTPRIC_HOSP_LV】';
COMMENT ON COLUMN nhsa.mdtrt_d.dedc_hosp_lv IS '起付线医院等级；接口必填：否；数据字典，详见字典【起付线医院等级DEDC_HOSP_LV】';
COMMENT ON COLUMN nhsa.mdtrt_d.begntime IS '开始时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdtrt_d.endtime IS '结束时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.mdtrt_d.mdtrt_cert_type IS '就诊凭证类型；接口必填：否；数据字典，详见字典【就诊凭证类型MDTRT_CERT_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.mdtrt_cert_no IS '就诊凭证编号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.med_type IS '医疗类别；接口必填：否；数据字典，详见字典【医疗类别MED_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.rloc_type IS '异地安置类别；接口必填：否；数据字典，详见字典【异地安置类别RLOC_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.ars_year_ipt_flag IS '跨年度住院标志；接口必填：否；数据字典，详见字典【跨年度住院标志ARS_YEAR_IPT_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.pre_pay_flag IS '先行支付标志；接口必填：否；数据字典，详见字典【先行支付标志PRE_PAY_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.year IS '年度；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.refl_old_mdtrt_id IS '转诊前就诊ID；接口必填：否；使用就诊信息表中升位后的就诊ID，用于关联就诊信息表';
COMMENT ON COLUMN nhsa.mdtrt_d.ipt_otp_no IS '住院/门诊号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.medrcdno IS '病历号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.chfpdr_code IS '主诊医师代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.chfpdr_name IS '主诊医师姓名；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.adm_diag_dscr IS '入院诊断描述；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.adm_dept_codg IS '入院科室编码；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.adm_dept_name IS '入院科室名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.adm_bed IS '入院床位；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.wardarea_bed IS '病区床位；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.traf_dept_flag IS '转科室标志；接口必填：否；数据字典，详见字典【转科室标志TRAF_DEPT_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.dscg_maindiag_code IS '住院主诊断代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dscg_maindiag_name IS '住院主诊断名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dscg_dept_codg IS '出院科室编码；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dscg_dept_name IS '出院科室名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dscg_bed IS '出院床位；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dscg_way IS '离院方式；接口必填：否；数据字典，详见字典【离院方式DSCG_WAY】';
COMMENT ON COLUMN nhsa.mdtrt_d.main_cond_dscr IS '主要病情描述；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dise_no IS '病种编号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.dise_name IS '病种名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.oprn_oprt_code IS '手术操作代码；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.oprn_oprt_name IS '手术操作名称；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.otp_diag_info IS '门诊诊断信息；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.inhosp_stas IS '在院状态；接口必填：是；数据字典，详见字典【在院状态INHOSP_STAS】';
COMMENT ON COLUMN nhsa.mdtrt_d.die_date IS '死亡日期；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.ipt_days IS '住院天数；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.geso_val IS '孕周数；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.birctrl_type IS '计划生育手术类别；接口必填：否；数据字典，详见字典【计划生育手术类别BIRCTRL_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.fetts IS '胎次；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.fetus_cnt IS '胎儿数；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.matn_type IS '生育类别；接口必填：否；数据字典，详见字典【生育类别MATN_TYPE】';
COMMENT ON COLUMN nhsa.mdtrt_d.prey_time IS '妊娠时间；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.latechb_flag IS '晚育标志；接口必填：否；数据字典，详见字典【晚育标志LATECHB_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.pret_flag IS '早产标志；接口必填：否；数据字典，详见字典【早产标志PRET_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.fpsc_no IS '计划生育服务证号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.birctrl_matn_date IS '计划生育手术或生育日期；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.cop_flag IS '伴有并发症标志；接口必填：否；数据字典，详见字典【伴有并发症标志COP_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.trt_dcla_detl_sn IS '待遇申报明细流水号；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.ttp_pay_flag IS '第三方赔付标志；接口必填：否；数据字典，详见字典【第三方赔付标志TTP_PAY_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.ttp_pay_prop IS '第三方赔付比例；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.memo IS '备注；接口必填：否';
COMMENT ON COLUMN nhsa.mdtrt_d.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';
COMMENT ON COLUMN nhsa.mdtrt_d.akc190 IS 'AKC190；接口必填：是；FIXMEDINS_CODE、AKC190为与医保结算数据关联变量，确保填报完整、准确';

CREATE TABLE IF NOT EXISTS nhsa.fee_list_d (
    bkkp_sn varchar(30) NOT NULL,
    mdtrt_id varchar(30) NOT NULL,
    fee_ocur_time varchar(20),
    setl_id varchar(30) NOT NULL,
    rx_drord_no varchar(30),
    fixmedins_code varchar(30),
    fixmedins_name varchar(200),
    psn_no varchar(30),
    psn_insu_rlts_id varchar(20),
    insu_admdvs varchar(6),
    pay_loc varchar(6),
    med_type varchar(6),
    cnt numeric(16,4),
    pric numeric(16,6),
    det_item_fee_sumamt numeric(16,2),
    pric_uplmt_amt numeric(16,6),
    selfpay_prop numeric(5,4),
    fulamt_ownpay_amt numeric(16,2),
    overlmt_selfpay numeric(16,2),
    preselfpay_amt numeric(16,2),
    inscp_amt numeric(16,2),
    cvlserv_bedfee_amt numeric(16,2),
    medins_disc_amt numeric(16,2),
    chrgitm_lv varchar(3),
    hilist_code varchar(50),
    hilist_name varchar(200),
    list_type varchar(6),
    med_list_codg varchar(50),
    medins_list_codg varchar(150),
    medins_list_name varchar(100),
    med_chrgitm_type varchar(6),
    prodname varchar(2000),
    spec varchar(200),
    dosform_name varchar(200),
    bilg_dept_codg varchar(30),
    bilg_dept_name varchar(100),
    bilg_dr_code varchar(30),
    bilg_dr_name varchar(50),
    acord_dept_codg varchar(30),
    acord_dept_name varchar(100),
    acord_dr_code varchar(30),
    acord_dr_name varchar(50),
    lmt_used_flag varchar(3),
    hosp_prep_flag varchar(3),
    hosp_appr_flag varchar(3),
    tcmdrug_used_way varchar(6),
    prodplac_type varchar(6),
    bas_medn_flag varchar(3),
    hi_nego_drug_flag varchar(3),
    prcu_drug_flag varchar(3),
    chld_medc_flag varchar(3),
    etip_flag varchar(3),
    etip_hosp_code varchar(30),
    dscg_tkdrug_flag varchar(3),
    list_sp_item_flag varchar(3),
    matn_fee_flag varchar(6),
    drt_reim_flag varchar(3),
    reim_prop numeric(5,4),
    oprn_oprt_code varchar(30),
    sin_dos_dscr varchar(200),
    used_frqu_dscr varchar(200),
    prd_days numeric(4,2),
    medc_way_dscr varchar(200),
    rx_circ_flag varchar(3),
    dise_codg varchar(30),
    chrg_bchno varchar(30),
    init_feedetl_sn varchar(30),
    memo varchar(500),
    vali_flag varchar(3),
    CONSTRAINT pk_fee_list_d PRIMARY KEY (bkkp_sn)
);
COMMENT ON TABLE nhsa.fee_list_d IS '医保结算清单规范测试表：FEE_LIST_D';
COMMENT ON COLUMN nhsa.fee_list_d.bkkp_sn IS '记账流水号；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.mdtrt_id IS '就诊ID；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.fee_ocur_time IS '费用发生时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.fee_list_d.setl_id IS '结算ID；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.rx_drord_no IS '处方/医嘱号；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.fixmedins_code IS '定点医药机构编号；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.fixmedins_name IS '定点医药机构名称；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.psn_no IS '人员编号；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.psn_insu_rlts_id IS '人员参保关系ID；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.insu_admdvs IS '参保所属医保区划；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.pay_loc IS '支付地点类别；接口必填：否；数据字典，详见字典【支付地点类别PAY_LOC】';
COMMENT ON COLUMN nhsa.fee_list_d.med_type IS '医疗类别；接口必填：是；数据字典，详见字典【医疗类别MED_TYPE】';
COMMENT ON COLUMN nhsa.fee_list_d.cnt IS '数量；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.pric IS '单价；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.det_item_fee_sumamt IS '明细项目费用总额；接口必填：是；明细项目费用总额 = 单价 * 数量';
COMMENT ON COLUMN nhsa.fee_list_d.pric_uplmt_amt IS '定价上限金额；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.selfpay_prop IS '自付比例；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.fulamt_ownpay_amt IS '全自费金额；接口必填：否；自费项目的总费用';
COMMENT ON COLUMN nhsa.fee_list_d.overlmt_selfpay IS '超限价自费费用；接口必填：否；超限价金额 = 单价-定价上限金额';
COMMENT ON COLUMN nhsa.fee_list_d.preselfpay_amt IS '先行自付金额；接口必填：否；先行自付金额 = (明细项目费用总额-超限价金额)*自付比例';
COMMENT ON COLUMN nhsa.fee_list_d.inscp_amt IS '符合范围金额；接口必填：否；符合范围金额 = 明细项目费用总额-超限价金额-全自费金额-先行自付金额';
COMMENT ON COLUMN nhsa.fee_list_d.cvlserv_bedfee_amt IS '公务员床位费金额；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.medins_disc_amt IS '医院减免金额；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.chrgitm_lv IS '收费项目等级；接口必填：否；数据字典，详见字典【收费项目等级CHRGITM_LV】';
COMMENT ON COLUMN nhsa.fee_list_d.hilist_code IS '医保目录编码；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.hilist_name IS '医保目录名称；接口必填：是';
COMMENT ON COLUMN nhsa.fee_list_d.list_type IS '目录类别；接口必填：是；数据字典，详见字典【目录类别LIST_TYPE】';
COMMENT ON COLUMN nhsa.fee_list_d.med_list_codg IS '医疗目录编码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.medins_list_codg IS '医药机构目录编码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.medins_list_name IS '医药机构目录名称；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.med_chrgitm_type IS '医疗收费项目类别；接口必填：否；数据字典，详见字典【医疗收费项目类别MED_CHRGITM_TYPE】';
COMMENT ON COLUMN nhsa.fee_list_d.prodname IS '商品名；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.spec IS '规格；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.dosform_name IS '剂型名称；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.bilg_dept_codg IS '开单科室编码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.bilg_dept_name IS '开单科室名称；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.bilg_dr_code IS '开单医师代码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.bilg_dr_name IS '开单医师姓名；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.acord_dept_codg IS '受单科室编码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.acord_dept_name IS '受单科室名称；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.acord_dr_code IS '受单医师代码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.acord_dr_name IS '受单医师姓名；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.lmt_used_flag IS '限制使用标志；接口必填：否；数据字典，详见字典【限制使用标志LMT_USED_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.hosp_prep_flag IS '医院制剂标志；接口必填：否；数据字典，详见字典【医院制剂标志HOSP_PREP_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.hosp_appr_flag IS '医院审批标志；接口必填：否；数据字典，详见字典【医院审批标志HOSP_APPR_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.tcmdrug_used_way IS '中药使用方式；接口必填：否；数据字典，详见字典【中药使用方式TCMDRUG_USED_WAY】';
COMMENT ON COLUMN nhsa.fee_list_d.prodplac_type IS '生产地类别；接口必填：否；数据字典，详见字典【生产地类别PRODPLAC_TYPE】';
COMMENT ON COLUMN nhsa.fee_list_d.bas_medn_flag IS '基本药物标志；接口必填：否；数据字典，详见字典【基本药物标志BAS_MEDN_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.hi_nego_drug_flag IS '医保谈判药品标志；接口必填：否；数据字典，详见字典【医保谈判药品标志HI_NEGO_DRUG_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.prcu_drug_flag IS '贵重药品标志；接口必填：否；数据字典，详见字典【贵重药品标志PRCU_DRUG_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.chld_medc_flag IS '儿童用药标志；接口必填：否；数据字典，详见字典【儿童用药标志CHLD_MEDC_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.etip_flag IS '外检标志；接口必填：否；数据字典，详见字典【外检标志ETIP_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.etip_hosp_code IS '外检医院编码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.dscg_tkdrug_flag IS '出院带药标志；接口必填：否；数据字典，详见字典【出院带药标志DSCG_TKDRUG_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.list_sp_item_flag IS '目录特项标志；接口必填：否；数据字典，详见字典【目录特项标志LIST_SP_ITEM_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.matn_fee_flag IS '生育费用标志；接口必填：否；数据字典，详见字典【生育费用标志MATN_FEE_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.drt_reim_flag IS '直报标志；接口必填：否；数据字典，详见字典【直报标志DRT_REIM_FLAG】';
COMMENT ON COLUMN nhsa.fee_list_d.reim_prop IS '报销比例；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.oprn_oprt_code IS '手术操作代码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.sin_dos_dscr IS '单次剂量描述；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.used_frqu_dscr IS '使用频次描述；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.prd_days IS '周期天数；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.medc_way_dscr IS '用药途径描述；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.rx_circ_flag IS '处方流转标志；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.dise_codg IS '病种编码；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.chrg_bchno IS '收费批次号；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.init_feedetl_sn IS '原费用明细流水号；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.memo IS '备注；接口必填：否';
COMMENT ON COLUMN nhsa.fee_list_d.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';

CREATE TABLE IF NOT EXISTS nhsa.setl_d (
    clr_optins varchar(300),
    setl_id varchar(30) NOT NULL,
    mdtrt_id varchar(30) NOT NULL,
    init_setl_id varchar(30),
    psn_no varchar(30),
    psn_insu_rlts_id varchar(30),
    psn_name varchar(50),
    psn_cert_type varchar(3),
    certno varchar(30),
    gend varchar(3),
    naty varchar(3),
    brdy varchar(8),
    age numeric(4,1),
    insutype varchar(6),
    psn_type varchar(6),
    cvlserv_flag varchar(3),
    cvlserv_lv varchar(6),
    sp_psn_type varchar(6),
    sp_psn_type_lv varchar(3),
    clct_grde varchar(3),
    flxempe_flag varchar(3),
    nwb_flag varchar(3),
    insu_admdvs varchar(6),
    emp_no varchar(40),
    emp_name varchar(200),
    emp_type varchar(3),
    econ_type varchar(3),
    afil_indu varchar(6),
    afil_rlts varchar(3),
    emp_mgt_type varchar(50),
    pay_loc varchar(6),
    fixmedins_code varchar(30),
    fixmedins_name varchar(200),
    hosp_lv varchar(3),
    fix_blng_admdvs varchar(6),
    lmtpric_hosp_lv varchar(6),
    dedc_hosp_lv varchar(6),
    begndate varchar(8),
    enddate varchar(8),
    setl_time varchar(20),
    mdtrt_cert_type varchar(3),
    mdtrt_cert_no varchar(50),
    med_type varchar(6),
    setl_type varchar(6),
    clr_type varchar(6),
    clr_way varchar(6),
    psn_setlway varchar(6),
    medfee_sumamt numeric(16,2),
    fulamt_ownpay_amt numeric(16,2),
    overlmt_selfpay numeric(16,2),
    preselfpay_amt numeric(16,2),
    inscp_amt numeric(16,2),
    dedc_std numeric(16,2),
    crt_dedc numeric(16,2),
    act_pay_dedc numeric(16,2),
    hifp_pay numeric(16,2),
    pool_prop_selfpay numeric(5,4),
    hi_agre_sumfee numeric(16,2),
    cvlserv_pay numeric(16,2),
    hifes_pay numeric(16,2),
    hifmi_pay numeric(16,2),
    hifob_pay numeric(16,2),
    hifdm_pay numeric(16,2),
    maf_pay numeric(16,2),
    othfund_pay numeric(16,2),
    fund_pay_sumamt numeric(16,2),
    psn_pay numeric(16,2),
    acct_pay numeric(16,2),
    cash_payamt numeric(16,2),
    ownpay_hosp_part numeric(16,2),
    refd_setl_flag varchar(3),
    year varchar(4),
    dise_no varchar(30),
    dise_name varchar(500),
    invono varchar(20),
    manl_reim_rea varchar(6),
    memo varchar(500),
    poolarea_no varchar(6),
    medins_lv varchar(6),
    fixmedins_poolarea varchar(6),
    medins_setl_id varchar(30),
    balc numeric(16,2),
    acct_mulaid_pay numeric(16,2),
    cal_ipt_cnt varchar(3),
    setl_cashpay_way varchar(6),
    mid_setl_flag varchar(3),
    acct_used_flag varchar(3),
    vali_flag varchar(3),
    akc190 varchar(3),
    CONSTRAINT pk_setl_d PRIMARY KEY (setl_id)
);
COMMENT ON TABLE nhsa.setl_d IS '医保结算清单规范测试表：SETL_D';
COMMENT ON COLUMN nhsa.setl_d.clr_optins IS '清算经办机构；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.setl_id IS '结算ID；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.mdtrt_id IS '就诊ID；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.init_setl_id IS '原结算ID；接口必填：否；用于回退时记录被回退数据的ID';
COMMENT ON COLUMN nhsa.setl_d.psn_no IS '人员编号；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.psn_insu_rlts_id IS '人员参保关系ID；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.psn_name IS '人员姓名；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.psn_cert_type IS '人员证件类型；接口必填：是；数据字典，详见字典【人员证件类型PSN_CERT_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.certno IS '证件号码；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.gend IS '性别；接口必填：是；数据字典，详见字典【性别GEND】';
COMMENT ON COLUMN nhsa.setl_d.naty IS '民族；接口必填：否；数据字典，详见字典【民族NATY】';
COMMENT ON COLUMN nhsa.setl_d.brdy IS '出生日期；接口必填：是；yyyymmdd';
COMMENT ON COLUMN nhsa.setl_d.age IS '年龄；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.insutype IS '险种类型；接口必填：是；数据字典，详见字典【医保类型INSUTYPE】';
COMMENT ON COLUMN nhsa.setl_d.psn_type IS '人员类别；接口必填：是；数据字典，详见字典【人员类别PSN_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.cvlserv_flag IS '公务员标志；接口必填：否；数据字典，详见字典【公务员标志CVLSERV_FLAG】';
COMMENT ON COLUMN nhsa.setl_d.cvlserv_lv IS '公务员等级；接口必填：否；数据字典，详见字典【公务员等级CVLSERV_LV】';
COMMENT ON COLUMN nhsa.setl_d.sp_psn_type IS '特殊人员类型；接口必填：否；数据字典，详见字典【特殊人员类型SP_PSN_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.sp_psn_type_lv IS '特殊人员类型等级；接口必填：否；数据字典，详见字典【特殊人员类型等级SP_PSN_TYPE_LV】';
COMMENT ON COLUMN nhsa.setl_d.clct_grde IS '缴费档次；接口必填：否；数据字典，详见字典【缴费档次CLCT_GRDE】';
COMMENT ON COLUMN nhsa.setl_d.flxempe_flag IS '灵活就业标志；接口必填：否；数据字典，详见字典【灵活就业标志FLXEMPE_FLAG】';
COMMENT ON COLUMN nhsa.setl_d.nwb_flag IS '新生儿标志；接口必填：否；数据字典，详见字典【新生儿标志NWB_FLAG】';
COMMENT ON COLUMN nhsa.setl_d.insu_admdvs IS '参保所属医保区划；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.emp_no IS '单位编号；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.emp_name IS '单位名称；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.emp_type IS '单位类型；接口必填：否；数据字典，详见字典【单位类型EMP_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.econ_type IS '经济类型；接口必填：否；数据字典，详见字典【经济类型ECON_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.afil_indu IS '所属行业；接口必填：否；数据字典，详见字典【所属行业AFIL_INDU】';
COMMENT ON COLUMN nhsa.setl_d.afil_rlts IS '隶属关系；接口必填：否；数据字典，详见字典【隶属关系AFIL_RLTS】';
COMMENT ON COLUMN nhsa.setl_d.emp_mgt_type IS '单位管理类型；接口必填：否；数据字典，详见字典【单位管理类型EMP_MGT_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.pay_loc IS '支付地点类别；接口必填：否；数据字典，详见字典【支付地点类别PAY_LOC】';
COMMENT ON COLUMN nhsa.setl_d.fixmedins_code IS '定点医药机构编号；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.fixmedins_name IS '定点医药机构名称；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.hosp_lv IS '医院等级；接口必填：否；数据字典，详见字典【医院等级HOSP_LV】';
COMMENT ON COLUMN nhsa.setl_d.fix_blng_admdvs IS '定点归属医保区划；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.lmtpric_hosp_lv IS '限价医院等级；接口必填：否；数据字典，详见字典【限价医院等级LMTPRIC_HOSP_LV】';
COMMENT ON COLUMN nhsa.setl_d.dedc_hosp_lv IS '起付线医院等级；接口必填：否；数据字典，详见字典【起付线医院等级DEDC_HOSP_LV】';
COMMENT ON COLUMN nhsa.setl_d.begndate IS '开始日期；接口必填：是；格式：YYYYMMDD';
COMMENT ON COLUMN nhsa.setl_d.enddate IS '结束日期；接口必填：是；格式：YYYYMMDD';
COMMENT ON COLUMN nhsa.setl_d.setl_time IS '结算时间；接口必填：是；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.setl_d.mdtrt_cert_type IS '就诊凭证类型；接口必填：否；数据字典，详见字典【就诊凭证类型MDTRT_CERT_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.mdtrt_cert_no IS '就诊凭证编号；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.med_type IS '医疗类别；接口必填：是；数据字典，详见字典【医疗类别MED_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.setl_type IS '结算类别；接口必填：否；数据字典，详见字典【结算类别SETL_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.clr_type IS '清算类别；接口必填：否；数据字典，详见字典【清算类别CLR_TYPE】';
COMMENT ON COLUMN nhsa.setl_d.clr_way IS '清算方式；接口必填：否；数据字典，详见字典【清算方式CLR_WAY】';
COMMENT ON COLUMN nhsa.setl_d.psn_setlway IS '个人结算方式；接口必填：否；数据字典，详见字典【个人结算方式PSN_SETLWAY】';
COMMENT ON COLUMN nhsa.setl_d.medfee_sumamt IS '医疗费总额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.fulamt_ownpay_amt IS '全自费金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.overlmt_selfpay IS '超限价自费费用；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.preselfpay_amt IS '先行自付金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.inscp_amt IS '符合范围金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.dedc_std IS '起付标准；接口必填：是；本次就诊基本医疗的起付线标准';
COMMENT ON COLUMN nhsa.setl_d.crt_dedc IS '本次起付线；接口必填：是；本次实际进入基本医疗的起付线金额';
COMMENT ON COLUMN nhsa.setl_d.act_pay_dedc IS '实际支付起付线；接口必填：是；本次就诊因其他满足起付线减免后的起付金额';
COMMENT ON COLUMN nhsa.setl_d.hifp_pay IS '统筹基金支出；接口必填：是；本次基本医疗报销金额（离休、老红军等特殊人员的基金支出放该指标）';
COMMENT ON COLUMN nhsa.setl_d.pool_prop_selfpay IS '基本医疗统筹支付比例；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.hi_agre_sumfee IS '医保认可费用总额；接口必填：否；一般情况下与“医疗费总额”相等，当存在按定额、限额支付号或者医院有对费用进行减免或承担等情况下，与“医疗费总额”不等';
COMMENT ON COLUMN nhsa.setl_d.cvlserv_pay IS '公务员医疗补助基金支出；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.hifes_pay IS '补充医疗保险基金支出；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.hifmi_pay IS '大病补充医疗保险基金支出；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.hifob_pay IS '大额医疗补助基金支出；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.hifdm_pay IS '伤残人员医疗保障基金支出；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.maf_pay IS '医疗救助基金支出；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.othfund_pay IS '其它基金支付；接口必填：是；除以上列出的基本医疗、公务员医疗救助等基金支出外的其他基金支出金额，这里不包含个人账户支出';
COMMENT ON COLUMN nhsa.setl_d.fund_pay_sumamt IS '基金支付总额；接口必填：是；除个人账户支出金额之外的所有基金支出金额，统筹基金支出+补充医疗保险基金支出+公务员医疗补助基金支出+大额医疗补助基金支出+大病补充医疗保险基金支出+伤残人员医疗保障基金支出+医疗救助基金支出+其它基金支付<=基金支付总额';
COMMENT ON COLUMN nhsa.setl_d.psn_pay IS '个人支付金额；接口必填：是；本次结算个人承担金额总额；个人账户支出+现金支付金额';
COMMENT ON COLUMN nhsa.setl_d.acct_pay IS '个人账户支出；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.cash_payamt IS '现金支付金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.ownpay_hosp_part IS '自费中医院负担部分；接口必填：否；个人自费部分中，医院负责承担的金额';
COMMENT ON COLUMN nhsa.setl_d.refd_setl_flag IS '退费结算标志；接口必填：是；数据字典，详见字典【退费结算标志REFD_SETL_FLAG】';
COMMENT ON COLUMN nhsa.setl_d.year IS '年度；接口必填：是';
COMMENT ON COLUMN nhsa.setl_d.dise_no IS '病种编号；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.dise_name IS '病种名称；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.invono IS '发票号；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.manl_reim_rea IS '零星报销原因；接口必填：否；数据字典，详见字典【零星报销原因MANL_REIM_REA】';
COMMENT ON COLUMN nhsa.setl_d.memo IS '备注；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.poolarea_no IS '统筹区编号；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.medins_lv IS '医药机构等级；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.fixmedins_poolarea IS '定点归属机构；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.medins_setl_id IS '医药机构结算ID；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.balc IS '余额；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.acct_mulaid_pay IS '账户共济支付金额；接口必填：否';
COMMENT ON COLUMN nhsa.setl_d.cal_ipt_cnt IS '计算住院次数标志；接口必填：否；数据字典，详见字典【计算住院次数标志CAL_IPT_CNT】';
COMMENT ON COLUMN nhsa.setl_d.setl_cashpay_way IS '结算现金支付方式；接口必填：否；数据字典，详见字典【结算现金支付方式SETL_CASHPAY_WAY】';
COMMENT ON COLUMN nhsa.setl_d.mid_setl_flag IS '中途结算标志；接口必填：否；数据字典，参见字典【中途结算标志 MID_SETL_FLAG 】';
COMMENT ON COLUMN nhsa.setl_d.acct_used_flag IS '账户使用标志；接口必填：否；数据字典，参见字典【个人账户使用标志 ACCT_USED_FLAG 】';
COMMENT ON COLUMN nhsa.setl_d.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';
COMMENT ON COLUMN nhsa.setl_d.akc190 IS 'AKC190；接口必填：是；FIXMEDINS_CODE、AKC190为与医保结算数据关联变量，确保填报完整、准确';

CREATE TABLE IF NOT EXISTS nhsa.setl_fee_stt_d (
    setl_id varchar(30) NOT NULL,
    mdtrt_id varchar(30) NOT NULL,
    evt_inst_id varchar(40),
    psn_no varchar(30),
    psn_insu_rlts_id varchar(20),
    med_chrgitm_type varchar(6),
    item_sumamt numeric(16,2),
    item_claa_amt numeric(16,2),
    item_clab_amt numeric(16,2),
    item_ownpay_amt numeric(16,2),
    item_oth_amt numeric(16,2),
    vali_flag varchar(3)
);
COMMENT ON TABLE nhsa.setl_fee_stt_d IS '医保结算清单规范测试表：SETL_FEE_STT_D';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.setl_id IS '结算ID；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.mdtrt_id IS '就诊ID；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.evt_inst_id IS '事件实例ID；接口必填：否';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.psn_no IS '人员编号；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.psn_insu_rlts_id IS '人员参保关系 ID；接口必填：否';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.med_chrgitm_type IS '医疗收费项目类别；接口必填：是；数据字典，详见字典【医疗收费项目类别MED_CHRGITM_TYPE】';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.item_sumamt IS '项目总金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.item_claa_amt IS '项目甲类金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.item_clab_amt IS '项目乙类金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.item_ownpay_amt IS '项目自费金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.item_oth_amt IS '项目其他金额；接口必填：是';
COMMENT ON COLUMN nhsa.setl_fee_stt_d.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';

CREATE TABLE IF NOT EXISTS nhsa.hilist_b (
    hilist_code varchar(50) NOT NULL,
    hilist_name varchar(200),
    begndate varchar(8),
    enddate varchar(8),
    med_chrgitm_type varchar(6),
    chrgitm_lv varchar(3),
    lmt_used_flag varchar(3),
    list_type varchar(6),
    med_use_flag varchar(3),
    matn_used_flag varchar(3),
    hilist_use_type varchar(3),
    lmt_cpnd_type varchar(3),
    memo varchar(500),
    vali_flag varchar(3),
    CONSTRAINT pk_hilist_b PRIMARY KEY (hilist_code)
);
COMMENT ON TABLE nhsa.hilist_b IS '医保结算清单规范测试表：HILIST_B';
COMMENT ON COLUMN nhsa.hilist_b.hilist_code IS '医保目录编码；接口必填：是；第一主键';
COMMENT ON COLUMN nhsa.hilist_b.hilist_name IS '医保目录名称；接口必填：是';
COMMENT ON COLUMN nhsa.hilist_b.begndate IS '开始日期；接口必填：是；第二主键，格式：YYYYMMDD';
COMMENT ON COLUMN nhsa.hilist_b.enddate IS '结束日期；接口必填：否；格式：YYYYMMDD';
COMMENT ON COLUMN nhsa.hilist_b.med_chrgitm_type IS '医疗收费项目类别；接口必填：是；数据字典，详见字典【医疗收费项目类别MED_CHRGITM_TYPE】';
COMMENT ON COLUMN nhsa.hilist_b.chrgitm_lv IS '收费项目等级；接口必填：是；数据字典，详见字典【收费项目等级CHRGITM_LV】';
COMMENT ON COLUMN nhsa.hilist_b.lmt_used_flag IS '限制使用标志；接口必填：是；数据字典，详见字典【限制使用标志LMT_USED_FLAG】';
COMMENT ON COLUMN nhsa.hilist_b.list_type IS '目录类别；接口必填：是；数据字典，详见字典【目录类别LIST_TYPE】';
COMMENT ON COLUMN nhsa.hilist_b.med_use_flag IS '医疗使用标志；接口必填：是；数据字典，详见字典【医疗使用标志MED_USE_FLAG】';
COMMENT ON COLUMN nhsa.hilist_b.matn_used_flag IS '生育使用标志；接口必填：是；数据字典，详见字典【生育使用标志MATN_USE_FLAG】';
COMMENT ON COLUMN nhsa.hilist_b.hilist_use_type IS '医保目录使用类别；接口必填：是；数据字典，详见字典【医保目录使用类别HILIST_USE_TYPE】';
COMMENT ON COLUMN nhsa.hilist_b.lmt_cpnd_type IS '限复方使用类型；接口必填：是；数据字典，详见字典【限复方使用类型LMT_CPND_TYPE】';
COMMENT ON COLUMN nhsa.hilist_b.memo IS '备注；接口必填：否';
COMMENT ON COLUMN nhsa.hilist_b.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';

CREATE TABLE IF NOT EXISTS nhsa.medins_info_b (
    medins_code varchar(40) NOT NULL,
    local_medins_code varchar(40),
    medins_name varchar(200),
    medins_abbr varchar(50),
    admdvs varchar(20),
    addr varchar(500),
    medins_type varchar(6),
    medins_type_name varchar(50),
    medinslv varchar(3),
    lnt varchar(20),
    lat varchar(20),
    begntime varchar(20),
    endtime varchar(20),
    memo varchar(500),
    prnt_medins_no varchar(20),
    yb_area varchar(10),
    vali_flag varchar(3),
    CONSTRAINT pk_medins_info_b PRIMARY KEY (medins_code)
);
COMMENT ON TABLE nhsa.medins_info_b IS '医保结算清单规范测试表：MEDINS_INFO_B';
COMMENT ON COLUMN nhsa.medins_info_b.medins_code IS '医疗机构代码；接口必填：是；国家统一编码（15项信息业务编码标准）';
COMMENT ON COLUMN nhsa.medins_info_b.local_medins_code IS '本地医疗机构代码；接口必填：是；原系统医疗机构系统编码';
COMMENT ON COLUMN nhsa.medins_info_b.medins_name IS '医疗机构名称；接口必填：是';
COMMENT ON COLUMN nhsa.medins_info_b.medins_abbr IS '医疗机构简称；接口必填：是';
COMMENT ON COLUMN nhsa.medins_info_b.admdvs IS '医保区划；接口必填：是';
COMMENT ON COLUMN nhsa.medins_info_b.addr IS '地址；接口必填：是';
COMMENT ON COLUMN nhsa.medins_info_b.medins_type IS '医疗服务机构类型；接口必填：是；数据字典，详见字典【医疗机构类别MEDINS_TYPE】';
COMMENT ON COLUMN nhsa.medins_info_b.medins_type_name IS '医疗服务机构类型名称；接口必填：否';
COMMENT ON COLUMN nhsa.medins_info_b.medinslv IS '医疗机构等级；接口必填：是；数据字典，详见字典【医疗机构等级MEDINSLV】';
COMMENT ON COLUMN nhsa.medins_info_b.lnt IS '经度；接口必填：否';
COMMENT ON COLUMN nhsa.medins_info_b.lat IS '纬度；接口必填：否';
COMMENT ON COLUMN nhsa.medins_info_b.begntime IS '开始时间；接口必填：否；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.medins_info_b.endtime IS '结束时间；接口必填：否；格式：yyyy-MM-dd HH:mm:ss';
COMMENT ON COLUMN nhsa.medins_info_b.memo IS '备注；接口必填：否';
COMMENT ON COLUMN nhsa.medins_info_b.prnt_medins_no IS '上级医疗机构编号；接口必填：否';
COMMENT ON COLUMN nhsa.medins_info_b.yb_area IS '医保区划编码；接口必填：是';
COMMENT ON COLUMN nhsa.medins_info_b.vali_flag IS '有效标志；接口必填：是；数据字典，详见字典【有效标志VALI_FLAG】';

CREATE INDEX IF NOT EXISTS idx_mdcs_setl_time ON nhsa.mdcs_fund_setl_list_d(setl_time);
CREATE INDEX IF NOT EXISTS idx_mdcs_org_time ON nhsa.mdcs_fund_setl_list_d(fixmedins_code, setl_time);
CREATE INDEX IF NOT EXISTS idx_setl_query ON nhsa.setl_d(fixmedins_code, setl_time, med_type, vali_flag);
CREATE INDEX IF NOT EXISTS idx_fee_setl ON nhsa.fee_list_d(setl_id);
CREATE INDEX IF NOT EXISTS idx_diag_setl ON nhsa.mdcs_fund_setl_list_diag_d(setl_id);
COMMIT;
