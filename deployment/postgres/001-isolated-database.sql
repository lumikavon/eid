DO $$ BEGIN
  IF current_database() <> 'eid_local_dev' THEN
    RAISE EXCEPTION 'refusing non-eid database: %', current_database();
  END IF;
END $$;
COMMENT ON DATABASE eid_local_dev IS 'eid-local-dev-v1';
CREATE ROLE eid_migrator LOGIN PASSWORD 'local-migrate-only';
CREATE ROLE eid_api LOGIN PASSWORD 'local-api-only';
CREATE ROLE eid_worker LOGIN PASSWORD 'local-worker-only';
GRANT CONNECT, CREATE ON DATABASE eid_local_dev TO eid_migrator;
GRANT CONNECT ON DATABASE eid_local_dev TO eid_api, eid_worker;
GRANT USAGE, CREATE ON SCHEMA public TO eid_migrator;
GRANT USAGE ON SCHEMA public TO eid_api, eid_worker;
