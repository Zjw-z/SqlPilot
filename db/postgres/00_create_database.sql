\set ON_ERROR_STOP on

-- Required psql variable: sqlpilot_app_password
SELECT 'CREATE ROLE sqlpilot_owner NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqlpilot_owner') \gexec

SELECT format('CREATE ROLE sqlpilot_app LOGIN PASSWORD %L', :'sqlpilot_app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sqlpilot_app') \gexec

ALTER ROLE sqlpilot_app PASSWORD :'sqlpilot_app_password';
ALTER ROLE sqlpilot_app SET statement_timeout = '15s';
ALTER ROLE sqlpilot_app SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE sqlpilot_app SET default_transaction_read_only = on;

SELECT 'CREATE DATABASE sqlpilot_test OWNER sqlpilot_owner ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'sqlpilot_test') \gexec

REVOKE ALL ON DATABASE sqlpilot_test FROM PUBLIC;
GRANT CONNECT ON DATABASE sqlpilot_test TO sqlpilot_app;
