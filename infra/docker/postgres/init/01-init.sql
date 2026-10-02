-- Dev bootstrap for the Postgres container. Runs once on first start.
-- Schema and tables are owned by the services' migrations; this only provisions
-- the databases and the extensions the architecture depends on (D-003).

-- Primary store: identity, catalogue, providers, capabilities.
CREATE EXTENSION IF NOT EXISTS vector;

-- Isolated payment store: own database and transaction boundary, so it can be
-- lifted out from behind the licensed partner later (architecture.md).
SELECT 'CREATE DATABASE sabi_payments'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sabi_payments')\gexec

\connect sabi_payments
CREATE EXTENSION IF NOT EXISTS vector;
