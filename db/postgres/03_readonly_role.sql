BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqlpilot_readonly') THEN
        CREATE ROLE sqlpilot_readonly NOLOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE sqlpilot_test TO sqlpilot_readonly;
DO $$
DECLARE
    schema_name text;
BEGIN
    FOREACH schema_name IN ARRAY ARRAY['healthcare', 'nhsa'] LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = schema_name) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO sqlpilot_readonly', schema_name);
            EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO sqlpilot_readonly', schema_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO sqlpilot_readonly', schema_name);
        END IF;
    END LOOP;
END
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqlpilot_app') THEN
        EXECUTE 'GRANT sqlpilot_readonly TO sqlpilot_app';
    END IF;
END
$$;

COMMIT;

-- 连接账号应由管理员单独创建并安全保存密码：
-- CREATE USER sqlpilot_app WITH PASSWORD '请替换为强密码';
-- GRANT sqlpilot_readonly TO sqlpilot_app;
-- ALTER ROLE sqlpilot_app SET statement_timeout = '15s';
-- ALTER ROLE sqlpilot_app SET default_transaction_read_only = on;
