\set ON_ERROR_STOP on
\echo Installing SecondHandFraudDB schema (PostgreSQL 18, empty database)
\ir 001_core.sql
\ir 002_risk.sql
\ir 003_core_functions.sql
\ir 004_risk_functions.sql
\ir 005_views.sql
\echo Core schema installed. Seed separately with 006_seed.sql; optional extensions are not installed.
