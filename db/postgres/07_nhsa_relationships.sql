BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_mdcs_mdtrt') THEN
        ALTER TABLE nhsa.mdcs_fund_setl_list_d ADD CONSTRAINT fk_mdcs_mdtrt FOREIGN KEY(mdtrt_id) REFERENCES nhsa.mdtrt_d(mdtrt_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_mdcs_setl') THEN
        ALTER TABLE nhsa.mdcs_fund_setl_list_d ADD CONSTRAINT fk_mdcs_setl FOREIGN KEY(setl_id) REFERENCES nhsa.setl_d(setl_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_setl_mdtrt') THEN
        ALTER TABLE nhsa.setl_d ADD CONSTRAINT fk_setl_mdtrt FOREIGN KEY(mdtrt_id) REFERENCES nhsa.mdtrt_d(mdtrt_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_diag_mdcs') THEN
        ALTER TABLE nhsa.mdcs_fund_setl_list_diag_d ADD CONSTRAINT fk_diag_mdcs FOREIGN KEY(setl_id) REFERENCES nhsa.mdcs_fund_setl_list_d(setl_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_oprn_mdcs') THEN
        ALTER TABLE nhsa.mdcs_fund_setl_list_oprn_d ADD CONSTRAINT fk_oprn_mdcs FOREIGN KEY(setl_id) REFERENCES nhsa.mdcs_fund_setl_list_d(setl_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_chrg_mdcs') THEN
        ALTER TABLE nhsa.mdcs_fund_setl_list_chrgitm_d ADD CONSTRAINT fk_chrg_mdcs FOREIGN KEY(setl_id) REFERENCES nhsa.mdcs_fund_setl_list_d(setl_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_invy_mdcs') THEN
        ALTER TABLE nhsa.mdcs_fund_setl_list_invy_d ADD CONSTRAINT fk_invy_mdcs FOREIGN KEY(setl_id) REFERENCES nhsa.mdcs_fund_setl_list_d(setl_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_fee_setl') THEN
        ALTER TABLE nhsa.fee_list_d ADD CONSTRAINT fk_fee_setl FOREIGN KEY(setl_id) REFERENCES nhsa.setl_d(setl_id);
    END IF;
END
$$;

COMMIT;
