"""Expand the durable inventory protocol with DB-owned fences and recovery.

The old claim/finish entry points are deliberately revoked. Deploy the v2 Worker
with this migration; an old Worker fails closed while the new one is rolled out.
No historical task, attempt, receipt, result or Outbox row is removed.
"""
from alembic import op


revision = "0009_fenced_recovery"
down_revision = "0008_durable_submission"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
-- Remove only the two 0008 constraints that assumed one delivery for a task.
-- The per-event Inbox primary key and one accepted task_result remain intact.
ALTER TABLE task_outbox DROP CONSTRAINT task_outbox_task_id_key;
ALTER TABLE task_inbox DROP CONSTRAINT task_inbox_task_id_key;
CREATE INDEX task_outbox_task_event ON task_outbox(task_id,event_id);
CREATE INDEX task_inbox_task_event ON task_inbox(task_id,event_id);

ALTER TABLE durable_task
 ADD COLUMN fence_token bigint NOT NULL DEFAULT 0 CHECK (fence_token BETWEEN 0 AND 9007199254740991),
 ADD COLUMN current_event_id uuid,
 ADD COLUMN next_retry_at timestamptz CHECK (next_retry_at IS NULL OR isfinite(next_retry_at)),
 ADD COLUMN cancel_requested boolean NOT NULL DEFAULT false,
 ADD COLUMN cancel_requested_at timestamptz CHECK (cancel_requested_at IS NULL OR isfinite(cancel_requested_at)),
 ADD COLUMN error_class text CHECK (error_class IS NULL OR error_class IN
   ('TRANSIENT','FORMAT','PERMANENT','LEASE_EXPIRED','ATTEMPTS_EXHAUSTED')),
 ADD COLUMN format_repairs smallint NOT NULL DEFAULT 0 CHECK (format_repairs BETWEEN 0 AND 1),
 ADD COLUMN external_effect_state text NOT NULL DEFAULT 'none'
   CHECK (external_effect_state IN ('none','receipt_pending','unknown','confirmed'));
UPDATE durable_task t SET fence_token=t.attempt,current_event_id=o.event_id
 FROM task_outbox o WHERE o.task_id=t.id;
ALTER TABLE durable_task ADD CONSTRAINT durable_task_current_event_fk
 FOREIGN KEY(current_event_id) REFERENCES task_outbox(event_id);
CREATE INDEX durable_task_retry_due ON durable_task(next_retry_at,id)
 WHERE state='RETRY_WAIT';

ALTER TABLE durable_task DROP CONSTRAINT durable_task_state_check;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_stage_check;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_error_code_check;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_check;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_check1;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_check2;
ALTER TABLE durable_task ADD CONSTRAINT durable_task_state_v2 CHECK
 (state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED','FAILED','CANCELLED','DEAD_LETTER'));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_stage_v2 CHECK
 (stage IN ('waiting','inventory','retry_wait','done','blocked','failed','cancelled','dead_letter'));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_error_v2 CHECK
 (error_code IS NULL OR error_code IN ('AUTHORIZATION_EXPIRED_OR_REVOKED','DEPENDENCY_BLOCKED',
 'INVALID_INVENTORY_INPUT','TRANSIENT_DEPENDENCY','FORMAT_REPAIRABLE','LEASE_EXPIRED',
 'ATTEMPTS_EXHAUSTED','CANCELLED_BY_ACTOR','OUTBOX_POISONED'));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_result_v2 CHECK
 ((state='SUCCEEDED')=(result_id IS NOT NULL));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_failure_v2 CHECK
 ((state IN ('BLOCKED','FAILED','DEAD_LETTER'))=(error_code IS NOT NULL));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_state_stage_v2 CHECK
 ((state,stage) IN (('QUEUED','waiting'),('RUNNING','inventory'),
 ('RETRY_WAIT','retry_wait'),('SUCCEEDED','done'),('BLOCKED','blocked'),
 ('FAILED','failed'),('CANCELLED','cancelled'),('DEAD_LETTER','dead_letter')));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_retry_v2 CHECK
 ((state='RETRY_WAIT')=(next_retry_at IS NOT NULL));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_cancel_time_v2 CHECK
 (cancel_requested= (cancel_requested_at IS NOT NULL));

ALTER TABLE task_event DROP CONSTRAINT task_event_event_type_check;
ALTER TABLE task_event DROP CONSTRAINT task_event_state_check;
ALTER TABLE task_event ADD CONSTRAINT task_event_type_v2 CHECK
 (event_type IN ('task.queued','task.running','task.retry_wait','task.succeeded',
 'task.blocked','task.failed','task.cancelled','task.dead_letter','task.cancel_requested'));
ALTER TABLE task_event ADD CONSTRAINT task_event_state_v2 CHECK
 (state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED','FAILED','CANCELLED','DEAD_LETTER'));

ALTER TABLE task_attempt ADD COLUMN event_id uuid REFERENCES task_outbox(event_id),
 ADD COLUMN fence_token bigint CHECK (fence_token BETWEEN 1 AND 9007199254740991),
 ADD COLUMN lease_until timestamptz CHECK (lease_until IS NULL OR isfinite(lease_until)),
 ADD COLUMN base_hash text CHECK (base_hash IS NULL OR base_hash ~ '^[0-9a-f]{64}$'),
 ADD COLUMN workspace_epoch bigint CHECK (workspace_epoch IS NULL OR workspace_epoch>0),
 ADD COLUMN policy_epoch bigint CHECK (policy_epoch IS NULL OR policy_epoch>0);
UPDATE task_attempt a SET fence_token=a.attempt,base_hash=t.input_hash,
 event_id=(SELECT i.event_id FROM task_inbox i WHERE i.task_id=a.task_id
           AND i.owner_token=a.owner_token ORDER BY i.received_at DESC LIMIT 1),
 lease_until=coalesce((SELECT i.lease_until FROM task_inbox i WHERE i.task_id=a.task_id
           AND i.owner_token=a.owner_token ORDER BY i.received_at DESC LIMIT 1),
           a.completed_at,a.started_at)
 FROM durable_task t
 WHERE t.id=a.task_id;
ALTER TABLE task_attempt ALTER COLUMN fence_token SET NOT NULL;
CREATE UNIQUE INDEX task_attempt_one_running ON task_attempt(task_id) WHERE state='RUNNING';
CREATE UNIQUE INDEX task_attempt_event ON task_attempt(event_id) WHERE event_id IS NOT NULL;
CREATE UNIQUE INDEX task_attempt_task_fence ON task_attempt(task_id,fence_token);
CREATE UNIQUE INDEX task_attempt_stage_binding
 ON task_attempt(task_id,attempt,fence_token,event_id);
CREATE UNIQUE INDEX task_attempt_effect_binding
 ON task_attempt(task_id,attempt,fence_token);

-- Staging has no runtime table grants. A new attempt always gets a distinct key;
-- completed/abandoned rows are immutable even if the Worker still holds its UUID.
CREATE TABLE task_attempt_stage (
 task_id uuid NOT NULL,attempt bigint NOT NULL,fence_token bigint NOT NULL,
 event_id uuid NOT NULL REFERENCES task_outbox(event_id),
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object' AND octet_length(payload::text)<=16384),
 payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 base_hash text NOT NULL CHECK (base_hash ~ '^[0-9a-f]{64}$'),
 workspace_epoch bigint NOT NULL CHECK (workspace_epoch>0),
 policy_epoch bigint NOT NULL CHECK (policy_epoch>0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(created_at)),
 PRIMARY KEY(task_id,attempt),
 FOREIGN KEY(task_id,attempt,fence_token,event_id)
  REFERENCES task_attempt(task_id,attempt,fence_token,event_id)
);
REVOKE ALL ON task_attempt_stage FROM PUBLIC,eid_worker,eid_api;
GRANT SELECT ON task_attempt_stage TO eid_api;

-- No connector is present in Story 1.5. This ledger prevents future consumers
-- from interpreting task cancellation as proof that a sent effect was revoked.
CREATE TABLE task_effect_intent (
 id uuid PRIMARY KEY,task_id uuid NOT NULL REFERENCES durable_task(id),
 attempt bigint NOT NULL,fence_token bigint NOT NULL,
 state text NOT NULL CHECK (state IN ('receipt_pending','unknown','confirmed')),
 effect_key text NOT NULL CHECK (length(effect_key) BETWEEN 1 AND 128),
 declared_compensation text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(created_at)),
 UNIQUE(task_id,effect_key),
 FOREIGN KEY(task_id,attempt,fence_token)
  REFERENCES task_attempt(task_id,attempt,fence_token),
 CHECK (declared_compensation IS NULL)
);
REVOKE ALL ON task_effect_intent FROM PUBLIC,eid_worker,eid_api;
GRANT SELECT ON task_effect_intent TO eid_api;

CREATE TABLE task_scheduler_lease (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 owner_token uuid, fence_token bigint NOT NULL DEFAULT 0 CHECK(fence_token BETWEEN 0 AND 9007199254740991),
 lease_until timestamptz,
 CHECK ((owner_token IS NULL)=(lease_until IS NULL))
);
INSERT INTO task_scheduler_lease(singleton) VALUES(true);
REVOKE ALL ON task_scheduler_lease FROM PUBLIC,eid_worker,eid_api;

-- API submission still INSERTs task before its first event/outbox. Bind the
-- initial event only when the first Outbox appears in the same transaction.
""")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    security = f"SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}, pg_temp"
    op.execute(f"""
CREATE FUNCTION eid_task_bind_initial_event() RETURNS trigger
LANGUAGE plpgsql {security} AS $$
BEGIN
 UPDATE durable_task SET current_event_id=NEW.event_id
 WHERE id=NEW.task_id AND current_event_id IS NULL;
 RETURN NEW;
END $$;
CREATE TRIGGER task_outbox_bind_initial AFTER INSERT ON task_outbox
 FOR EACH ROW EXECUTE FUNCTION eid_task_bind_initial_event();
REVOKE ALL ON FUNCTION eid_task_bind_initial_event() FROM PUBLIC;

-- 0008 code must never claim or finish a v2 attempt. Revocation also fences
-- an old process whose statement begins after the migration commits.
REVOKE EXECUTE ON FUNCTION eid_task_claim(uuid,jsonb,text,uuid),
 eid_task_finish_inventory(uuid,uuid) FROM eid_worker;

-- Exact v1 envelope is still accepted for an initial or scheduled delivery.
-- A scheduled envelope changes only event_id and occurred_at, so existing
-- transport parsers remain adjacent-version compatible.
CREATE FUNCTION eid_task_envelope_hash(p_envelope jsonb) RETURNS text
LANGUAGE sql IMMUTABLE {security} AS $$
 SELECT encode(sha256(convert_to('{{'||string_agg(to_jsonb(key)::text||':'||value::text,
 ',' ORDER BY key)||'}}','UTF8')),'hex') FROM jsonb_each(p_envelope)
$$;
REVOKE ALL ON FUNCTION eid_task_envelope_hash(jsonb) FROM PUBLIC;

-- Only a current, queued event can poison its task. Lock the task before its
-- Outbox so a repaired row, expired relay lease, or superseded event loses.
-- There is no new Attempt for a message that cannot be safely executed.
CREATE FUNCTION eid_task_isolate_poison_v2(p_event uuid,p_envelope jsonb,
 p_stored_hash text,p_reason text,p_relay_owner uuid) RETURNS boolean
LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; chosen task_outbox; now_at timestamptz;
        task_id uuid; bad_binding boolean; bad_shape boolean;
BEGIN
 IF session_user<>'eid_worker' OR p_event IS NULL OR p_envelope IS NULL
 OR p_stored_hash IS NULL OR p_reason IS NULL OR p_reason NOT IN ('INVALID_ENVELOPE',
 'UNSUPPORTED_VERSION','BINDING_MISMATCH','STORED_ENVELOPE_HASH_MISMATCH')
 THEN RAISE EXCEPTION 'Invalid poison isolation request'; END IF;
 SELECT o.task_id INTO task_id FROM task_outbox o WHERE o.event_id=p_event;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO task FROM durable_task WHERE id=task_id FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO chosen FROM task_outbox WHERE event_id=p_event FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 now_at:=clock_timestamp();
 IF chosen.task_id IS DISTINCT FROM task.id
 OR task.current_event_id IS DISTINCT FROM p_event OR task.state<>'QUEUED'
 OR task.cancel_requested OR task.next_retry_at IS NOT NULL
 OR chosen.quarantined_at IS NOT NULL
 OR chosen.envelope::text IS DISTINCT FROM p_envelope::text
 OR chosen.envelope_hash IS DISTINCT FROM p_stored_hash
 OR (p_relay_owner IS NOT NULL AND
     (chosen.owner_token IS DISTINCT FROM p_relay_owner OR chosen.lease_until<=now_at))
 OR EXISTS(SELECT 1 FROM task_attempt a WHERE a.task_id=task.id AND a.state='RUNNING')
 OR EXISTS(SELECT 1 FROM task_inbox i WHERE i.consumer='inventory-v1'
           AND i.event_id=p_event AND i.state='received' AND i.lease_until>now_at)
 THEN RETURN false; END IF;
 bad_binding:=chosen.envelope->>'source' IS DISTINCT FROM 'eid-api'
 OR chosen.envelope->>'message_schema_version' IS DISTINCT FROM '1.0'
 OR chosen.envelope->>'event_type' IS DISTINCT FROM 'task.inventory.requested'
 OR chosen.envelope->>'category' IS DISTINCT FROM 'integration'
 OR chosen.envelope->>'aggregate_version' IS DISTINCT FROM '1'
 OR chosen.envelope->>'event_id' IS DISTINCT FROM p_event::text
 OR chosen.envelope->>'task_id' IS DISTINCT FROM task.id::text
 OR chosen.envelope->>'aggregate_id' IS DISTINCT FROM task.id::text
 OR chosen.envelope->>'input_ref' IS DISTINCT FROM task.id::text
 OR chosen.envelope->>'actor_id' IS DISTINCT FROM task.actor_id::text
 OR chosen.envelope->>'workspace_id' IS DISTINCT FROM task.workspace_id::text
 OR chosen.envelope->>'delegation_id' IS DISTINCT FROM task.delegation_id::text
 OR chosen.envelope->>'input_hash' IS DISTINCT FROM task.input_hash
 OR chosen.envelope->>'request_id' IS DISTINCT FROM task.request_id
 OR chosen.envelope->>'trace_id' IS DISTINCT FROM task.trace_id;
 -- The reason supplied by a Worker is only a hint. In particular, an exact,
 -- well-formed stored envelope must never be killed as INVALID_ENVELOPE.
 bad_shape:=(SELECT count(*)<>16 FROM jsonb_object_keys(chosen.envelope))
 OR octet_length(chosen.envelope::text)>8192
 OR jsonb_typeof(chosen.envelope->'message_schema_version') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'source') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'event_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'event_type') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'occurred_at') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'aggregate_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'aggregate_version') IS DISTINCT FROM 'number'
 OR chosen.envelope->'aggregate_version' IS DISTINCT FROM '1'::jsonb
 OR jsonb_typeof(chosen.envelope->'task_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'category') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'input_ref') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'input_hash') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'actor_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'workspace_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'delegation_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'request_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(chosen.envelope->'trace_id') IS DISTINCT FROM 'string'
 OR (chosen.envelope->>'occurred_at') IS NULL
 OR (chosen.envelope->>'occurred_at') !~
  '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}([.][0-9]{{1,6}})?(Z|[+]00:00)$';
 IF NOT bad_shape THEN
  BEGIN
   PERFORM (chosen.envelope->>'occurred_at')::timestamptz;
  EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
   bad_shape:=true;
  END;
 END IF;
 IF (p_reason='BINDING_MISMATCH' AND NOT bad_binding)
 OR (p_reason='UNSUPPORTED_VERSION' AND
     chosen.envelope->>'message_schema_version' IS NOT DISTINCT FROM '1.0')
 OR (p_reason='STORED_ENVELOPE_HASH_MISMATCH' AND
     eid_task_envelope_hash(chosen.envelope)=chosen.envelope_hash)
 OR (p_reason='INVALID_ENVELOPE' AND NOT (bad_binding OR bad_shape OR
     eid_task_envelope_hash(chosen.envelope) IS DISTINCT FROM chosen.envelope_hash))
 THEN RETURN false; END IF;
 INSERT INTO task_quarantine(event_id,payload_hash,reason,schema_version)
 VALUES(chosen.event_id,encode(sha256(convert_to(chosen.envelope::text,'UTF8')),'hex'),
 p_reason,left(chosen.envelope->>'message_schema_version',32)) ON CONFLICT DO NOTHING;
 UPDATE task_outbox SET quarantined_at=now_at,owner_token=NULL,lease_until=NULL
 WHERE event_id=chosen.event_id;
 UPDATE task_inbox SET state='processed',processed_at=now_at
 WHERE consumer='inventory-v1' AND event_id=p_event AND state='received';
 UPDATE durable_task SET state='DEAD_LETTER',stage='dead_letter',
 error_code='OUTBOX_POISONED',error_class='FORMAT',current_seq=current_seq+1,
 updated_at=now_at WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.dead_letter','DEAD_LETTER');
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION eid_task_isolate_poison_v2(uuid,jsonb,text,text,uuid) FROM PUBLIC;

-- Supersede relay selection. Confirm retains its v1 lease/body fence; the
-- six-argument quarantine interface now transitions the current task too.
CREATE OR REPLACE FUNCTION eid_task_relay_claim(p_owner uuid) RETURNS jsonb
LANGUAGE plpgsql {security} AS $$
DECLARE chosen task_outbox; blocked_id uuid; propagated integer;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 FOR propagated IN 1..64 LOOP
  SELECT t.id INTO blocked_id FROM durable_task t
  WHERE t.state='QUEUED' AND EXISTS(
   SELECT 1 FROM task_dependency d JOIN durable_task predecessor ON predecessor.id=d.depends_on
   WHERE d.task_id=t.id AND predecessor.state IN ('BLOCKED','FAILED','CANCELLED','DEAD_LETTER'))
  ORDER BY t.created_at,t.id FOR UPDATE OF t SKIP LOCKED LIMIT 1;
  EXIT WHEN NOT FOUND;
  PERFORM eid_task_block_dependency(blocked_id);
 END LOOP;
 SELECT o.* INTO chosen FROM task_outbox o JOIN durable_task t ON t.id=o.task_id
 WHERE t.current_event_id=o.event_id AND t.state='QUEUED' AND NOT t.cancel_requested
 AND o.available_at<=clock_timestamp() AND o.quarantined_at IS NULL
 AND (o.lease_until IS NULL OR o.lease_until<=clock_timestamp())
 AND NOT EXISTS(SELECT 1 FROM task_inbox i WHERE i.event_id=o.event_id
                AND (i.state='processed' OR i.lease_until>clock_timestamp()))
 AND NOT EXISTS(SELECT 1 FROM task_dependency d JOIN durable_task predecessor
                ON predecessor.id=d.depends_on
                WHERE d.task_id=o.task_id AND predecessor.state<>'SUCCEEDED')
 ORDER BY o.available_at,o.created_at,o.event_id
 FOR UPDATE OF o SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE task_outbox SET owner_token=p_owner,lease_until=clock_timestamp()+interval '30 seconds',
 available_at=clock_timestamp()+interval '30 seconds',publish_attempts=publish_attempts+1
 WHERE event_id=chosen.event_id;
 RETURN jsonb_build_object('event_id',chosen.event_id,'task_id',chosen.task_id,
 'envelope',chosen.envelope,'envelope_hash',chosen.envelope_hash);
END $$;

-- Retain the 0008 signature and grant used by the Python relay. The helper
-- rechecks the claimed body, live lease, and current task before any write.
CREATE OR REPLACE FUNCTION eid_task_relay_quarantine(p_owner uuid,p_event uuid,
 p_envelope jsonb,p_hash text,p_reason text,p_version text) RETURNS boolean
LANGUAGE plpgsql {security} AS $$
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL OR p_event IS NULL
 OR p_envelope IS NULL OR jsonb_typeof(p_envelope)<>'object' OR p_hash IS NULL
 OR p_reason IS NULL OR p_reason NOT IN ('INVALID_ENVELOPE','UNSUPPORTED_VERSION',
 'BINDING_MISMATCH','STORED_ENVELOPE_HASH_MISMATCH')
 OR (p_version IS NOT NULL AND p_version !~ '^[0-9.]{{1,32}}$')
 THEN RAISE EXCEPTION 'Invalid relay quarantine request'; END IF;
 RETURN eid_task_isolate_poison_v2(p_event,p_envelope,p_hash,p_reason,p_owner);
END $$;
REVOKE ALL ON FUNCTION eid_task_relay_quarantine(uuid,uuid,jsonb,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_task_relay_quarantine(uuid,uuid,jsonb,text,text,text) TO eid_worker;

CREATE FUNCTION eid_task_claim_v2(p_event uuid,p_envelope jsonb,p_hash text,p_owner uuid)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE outbox task_outbox; task durable_task; inbox task_inbox; facts access_current_facts;
        now_at timestamptz;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL OR p_event IS NULL
 OR p_envelope IS NULL OR p_hash IS NULL THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT * INTO outbox FROM task_outbox WHERE event_id=p_event;
 IF NOT FOUND OR outbox.envelope::text IS DISTINCT FROM p_envelope::text THEN
  PERFORM eid_task_quarantine(p_event,p_hash,'BINDING_MISMATCH',p_envelope->>'message_schema_version');
  RETURN jsonb_build_object('status','quarantined');
 END IF;
 SELECT * INTO task FROM durable_task WHERE id=outbox.task_id;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','stale'); END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 IF task.current_event_id IS DISTINCT FROM p_event
 THEN RETURN jsonb_build_object('status','stale'); END IF;
 SELECT * INTO outbox FROM task_outbox WHERE event_id=p_event FOR UPDATE;
 IF NOT FOUND OR outbox.task_id IS DISTINCT FROM task.id
 OR outbox.quarantined_at IS NOT NULL
 OR outbox.envelope::text IS DISTINCT FROM p_envelope::text
 THEN RETURN jsonb_build_object('status','stale'); END IF;
 IF eid_task_envelope_hash(outbox.envelope) IS DISTINCT FROM outbox.envelope_hash THEN
  IF eid_task_isolate_poison_v2(p_event,outbox.envelope,outbox.envelope_hash,
   'STORED_ENVELOPE_HASH_MISMATCH',NULL)
  THEN RETURN jsonb_build_object('status','quarantined'); END IF;
  RETURN jsonb_build_object('status','stale');
 END IF;
 IF outbox.envelope_hash IS DISTINCT FROM p_hash THEN
  PERFORM eid_task_quarantine(p_event,p_hash,'BINDING_MISMATCH',p_envelope->>'message_schema_version');
  RETURN jsonb_build_object('status','quarantined');
 END IF;
 IF outbox.envelope->>'source' IS DISTINCT FROM 'eid-api'
 OR outbox.envelope->>'message_schema_version' IS DISTINCT FROM '1.0'
 OR outbox.envelope->>'event_type' IS DISTINCT FROM 'task.inventory.requested'
 OR outbox.envelope->>'category' IS DISTINCT FROM 'integration'
 OR outbox.envelope->>'aggregate_version' IS DISTINCT FROM '1'
 OR outbox.envelope->>'event_id' IS DISTINCT FROM p_event::text
 OR outbox.envelope->>'task_id' IS DISTINCT FROM task.id::text
 OR outbox.envelope->>'aggregate_id' IS DISTINCT FROM task.id::text
 OR outbox.envelope->>'input_ref' IS DISTINCT FROM task.id::text
 OR outbox.envelope->>'actor_id' IS DISTINCT FROM task.actor_id::text
 OR outbox.envelope->>'workspace_id' IS DISTINCT FROM task.workspace_id::text
 OR outbox.envelope->>'delegation_id' IS DISTINCT FROM task.delegation_id::text
 OR outbox.envelope->>'input_hash' IS DISTINCT FROM task.input_hash
 OR outbox.envelope->>'request_id' IS DISTINCT FROM task.request_id
 OR outbox.envelope->>'trace_id' IS DISTINCT FROM task.trace_id THEN
  IF eid_task_isolate_poison_v2(p_event,outbox.envelope,outbox.envelope_hash,
   'BINDING_MISMATCH',NULL)
  THEN RETURN jsonb_build_object('status','quarantined'); END IF;
  RETURN jsonb_build_object('status','stale');
 END IF;
 SELECT * INTO inbox FROM task_inbox WHERE consumer='inventory-v1' AND event_id=p_event FOR UPDATE;
 IF FOUND THEN
  IF inbox.payload_hash<>p_hash THEN
   PERFORM eid_task_quarantine(p_event,p_hash,'BINDING_MISMATCH','1.0');
   RETURN jsonb_build_object('status','quarantined');
  END IF;
  IF inbox.state='processed' THEN RETURN jsonb_build_object('status','processed'); END IF;
  IF inbox.lease_until>clock_timestamp() THEN RETURN jsonb_build_object('status','busy'); END IF;
 END IF;
 IF task.state<>'QUEUED' OR task.cancel_requested OR task.next_retry_at IS NOT NULL THEN
  RETURN jsonb_build_object('status','stale');
 END IF;
 IF EXISTS(SELECT 1 FROM task_dependency d JOIN durable_task predecessor
  ON predecessor.id=d.depends_on WHERE d.task_id=task.id AND predecessor.state<>'SUCCEEDED')
 THEN RETURN jsonb_build_object('status','busy'); END IF;
 IF task.attempt>=3 OR task.fence_token>=9007199254740991 THEN
  RAISE EXCEPTION 'Attempt budget or fence exhausted';
 END IF;
 now_at:=clock_timestamp();
 INSERT INTO task_inbox(consumer,event_id,task_id,payload_hash,owner_token,lease_until)
 VALUES('inventory-v1',p_event,task.id,p_hash,p_owner,now_at+interval '30 seconds')
 ON CONFLICT(consumer,event_id) DO UPDATE SET owner_token=p_owner,
 lease_until=excluded.lease_until WHERE task_inbox.state='received'
 AND task_inbox.lease_until<=now_at;
 SELECT * INTO facts FROM access_current_facts
 WHERE actor_id=task.actor_id AND workspace_id=task.workspace_id;
 IF NOT eid_inventory_allowed(task,now_at) THEN
  UPDATE durable_task SET state='BLOCKED',stage='blocked',error_code='AUTHORIZATION_EXPIRED_OR_REVOKED',
  error_class='PERMANENT',current_seq=current_seq+1,updated_at=now_at
  WHERE id=task.id RETURNING * INTO task;
  INSERT INTO task_event(event_id,task_id,seq,event_type,state)
  VALUES(gen_random_uuid(),task.id,task.current_seq,'task.blocked','BLOCKED');
  UPDATE task_inbox SET state='processed',processed_at=now_at
  WHERE consumer='inventory-v1' AND event_id=p_event;
  RETURN jsonb_build_object('status','blocked');
 END IF;
 UPDATE durable_task SET state='RUNNING',stage='inventory',attempt=attempt+1,
 fence_token=fence_token+1,current_seq=current_seq+1,updated_at=now_at
 WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_attempt(task_id,attempt,owner_token,state,event_id,fence_token,lease_until,
 base_hash,workspace_epoch,policy_epoch)
 VALUES(task.id,task.attempt,p_owner,'RUNNING',p_event,task.fence_token,
 now_at+interval '30 seconds',task.input_hash,facts.workspace_epoch,facts.policy_epoch);
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.running','RUNNING');
 RETURN jsonb_build_object('status','claimed','task_id',task.id,'attempt',task.attempt,
 'fence_token',task.fence_token,'lease_until',now_at+interval '30 seconds');
END $$;

CREATE FUNCTION eid_task_heartbeat_v2(p_event uuid,p_owner uuid,p_fence bigint)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; now_at timestamptz;
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_outbox o ON o.task_id=t.id
 WHERE o.event_id=p_event;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','lost'); END IF;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 now_at:=clock_timestamp();
 IF task.cancel_requested THEN RETURN jsonb_build_object('status','cancel_requested'); END IF;
 IF task.state<>'RUNNING' OR task.current_event_id IS DISTINCT FROM p_event
 OR task.fence_token IS DISTINCT FROM p_fence OR NOT EXISTS(
  SELECT 1 FROM task_attempt a JOIN task_inbox i ON i.event_id=a.event_id
  WHERE a.task_id=task.id AND a.attempt=task.attempt AND a.owner_token=p_owner
  AND a.fence_token=p_fence AND a.state='RUNNING' AND a.lease_until>now_at
  AND i.consumer='inventory-v1' AND i.owner_token=p_owner
  AND i.state='received' AND i.lease_until>now_at)
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 UPDATE task_attempt SET lease_until=now_at+interval '30 seconds'
 WHERE task_id=task.id AND attempt=task.attempt;
 UPDATE task_inbox SET lease_until=now_at+interval '30 seconds'
 WHERE consumer='inventory-v1' AND event_id=p_event;
 RETURN jsonb_build_object('status','renewed','lease_until',now_at+interval '30 seconds');
END $$;

CREATE FUNCTION eid_task_stage_inventory_v2(p_event uuid,p_owner uuid,p_fence bigint)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; attempt_row task_attempt; facts access_current_facts;
        stage_row task_attempt_stage; items jsonb; payload jsonb;
        now_at timestamptz; item_limit integer; result_id uuid;
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_outbox o ON o.task_id=t.id
 WHERE o.event_id=p_event;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','lost'); END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 now_at:=clock_timestamp();
 SELECT * INTO attempt_row FROM task_attempt WHERE task_id=task.id AND attempt=task.attempt FOR UPDATE;
 IF task.state<>'RUNNING' OR task.cancel_requested
 OR task.current_event_id IS DISTINCT FROM p_event OR task.fence_token IS DISTINCT FROM p_fence
 OR attempt_row.owner_token IS DISTINCT FROM p_owner OR attempt_row.fence_token IS DISTINCT FROM p_fence
 OR attempt_row.state<>'RUNNING' OR attempt_row.lease_until<=now_at
 OR NOT EXISTS(SELECT 1 FROM task_inbox WHERE consumer='inventory-v1' AND event_id=p_event
  AND owner_token=p_owner AND state='received' AND lease_until>now_at)
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 SELECT * INTO stage_row FROM task_attempt_stage
 WHERE task_id=task.id AND attempt=task.attempt;
 IF FOUND THEN RETURN jsonb_build_object('status','staged','content_hash',stage_row.payload_hash); END IF;
 IF NOT eid_inventory_allowed(task,now_at) THEN
  RETURN jsonb_build_object('status','authorization_denied');
 END IF;
 IF task.input->>'operation' IS DISTINCT FROM 'inventory'
 OR jsonb_typeof(task.input->'input') IS DISTINCT FROM 'object'
 OR jsonb_typeof(task.input->'input'->'limit') IS DISTINCT FROM 'number'
 OR (task.input->'input'->>'limit') !~ '^([1-9]|[1-4][0-9]|50)$'
 THEN RETURN jsonb_build_object('status','invalid_input'); END IF;
 SELECT * INTO facts FROM access_current_facts
 WHERE actor_id=task.actor_id AND workspace_id=task.workspace_id;
 IF attempt_row.workspace_epoch IS DISTINCT FROM facts.workspace_epoch
 OR attempt_row.policy_epoch IS DISTINCT FROM facts.policy_epoch
 THEN RETURN jsonb_build_object('status','authorization_denied'); END IF;
 item_limit:=(task.input->'input'->>'limit')::integer;
 SELECT coalesce(jsonb_agg(jsonb_build_object('resource_id',r.id,'kind',r.kind,
  'revision',r.revision,'resource_epoch',r.policy_epoch) ORDER BY r.id),'[]'::jsonb)
 INTO items FROM (
  SELECT r.id,r.kind,r.policy_epoch,d.revision
  FROM access_resource r JOIN discovery_record d ON d.resource_id=r.id
  WHERE r.workspace_id=task.workspace_id AND d.kind=r.kind AND d.visibility='visible'
  AND length(r.title) BETWEEN 1 AND 512
  AND r.valid_from<=now_at AND (r.valid_until IS NULL OR r.valid_until>now_at)
  AND r.classification BETWEEN 0 AND facts.clearance AND r.policy_epoch>0
  AND (r.project_id=ANY(facts.project_scope) OR '*'=ANY(facts.project_scope))
  AND (r.customer_id=ANY(facts.customer_scope) OR '*'=ANY(facts.customer_scope))
  AND (r.product_id=ANY(facts.product_scope) OR '*'=ANY(facts.product_scope))
  AND (r.department=ANY(facts.department_scope) OR '*'=ANY(facts.department_scope))
  AND (facts.owner_scope='any' OR r.owner_id=facts.actor_id)
  AND r.approval_state=ANY(facts.approval_states)
  ORDER BY r.id LIMIT item_limit FOR SHARE OF r,d
 ) r;
 IF NOT eid_inventory_allowed(task,clock_timestamp()) THEN
  RETURN jsonb_build_object('status','authorization_denied');
 END IF;
 result_id:=gen_random_uuid();
 payload:=jsonb_build_object('result_id',result_id,'task_id',task.id,
  'workspace_id',task.workspace_id,'measured_at',now_at,
  'scope','first_authorized_visible_records','limit',item_limit,'items',items,
  'policy_epoch',jsonb_build_array(facts.workspace_epoch,facts.policy_epoch,facts.workspace_epoch));
 INSERT INTO task_attempt_stage(task_id,attempt,fence_token,event_id,payload,payload_hash,
 base_hash,workspace_epoch,policy_epoch)
 VALUES(task.id,task.attempt,p_fence,p_event,payload,
 encode(sha256(convert_to(payload::text,'UTF8')),'hex'),task.input_hash,
 facts.workspace_epoch,facts.policy_epoch) RETURNING * INTO stage_row;
 RETURN jsonb_build_object('status','staged','content_hash',stage_row.payload_hash);
END $$;

CREATE FUNCTION eid_task_finish_inventory_v2(p_event uuid,p_owner uuid,p_fence bigint,
 p_base_hash text,p_content_hash text) RETURNS jsonb
LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; attempt_row task_attempt; stage_row task_attempt_stage;
        inbox task_inbox; facts access_current_facts; now_at timestamptz; result_uuid uuid;
        item jsonb; item_id uuid; previous_id uuid; item_limit integer;
        item_revision bigint; item_epoch bigint; current_item record;
        earliest_valid_until timestamptz;
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_outbox o ON o.task_id=t.id
 WHERE o.event_id=p_event;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','lost'); END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 SELECT * INTO inbox FROM task_inbox WHERE consumer='inventory-v1' AND event_id=p_event FOR UPDATE;
 SELECT * INTO attempt_row FROM task_attempt WHERE task_id=task.id AND attempt=task.attempt FOR UPDATE;
 SELECT * INTO stage_row FROM task_attempt_stage WHERE task_id=task.id AND attempt=task.attempt;
 now_at:=clock_timestamp();
 IF task.cancel_requested THEN RETURN jsonb_build_object('status','cancel_requested'); END IF;
 IF task.state<>'RUNNING' OR task.current_event_id IS DISTINCT FROM p_event
 OR task.fence_token IS DISTINCT FROM p_fence OR inbox.owner_token IS DISTINCT FROM p_owner
 OR inbox.state IS DISTINCT FROM 'received' OR inbox.lease_until<=now_at
 OR attempt_row.owner_token IS DISTINCT FROM p_owner
 OR attempt_row.fence_token IS DISTINCT FROM p_fence OR attempt_row.state IS DISTINCT FROM 'RUNNING'
 OR attempt_row.lease_until<=now_at OR attempt_row.base_hash IS DISTINCT FROM p_base_hash
 OR stage_row.event_id IS DISTINCT FROM p_event OR stage_row.fence_token IS DISTINCT FROM p_fence
 OR stage_row.base_hash IS DISTINCT FROM task.input_hash
 OR stage_row.base_hash IS DISTINCT FROM p_base_hash
 OR stage_row.payload_hash IS DISTINCT FROM p_content_hash
 OR stage_row.payload_hash IS DISTINCT FROM
   encode(sha256(convert_to(stage_row.payload::text,'UTF8')),'hex')
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 SELECT * INTO facts FROM access_current_facts
 WHERE actor_id=task.actor_id AND workspace_id=task.workspace_id;
 IF NOT eid_inventory_allowed(task,now_at)
 OR attempt_row.workspace_epoch IS DISTINCT FROM facts.workspace_epoch
 OR attempt_row.policy_epoch IS DISTINCT FROM facts.policy_epoch
 OR stage_row.workspace_epoch IS DISTINCT FROM facts.workspace_epoch
 OR stage_row.policy_epoch IS DISTINCT FROM facts.policy_epoch
 THEN RETURN jsonb_build_object('status','authorization_denied'); END IF;
 -- A staged body is immutable to runtime roles, but its records can change
 -- between staging and finishing. Validate the bounded result shape first.
 IF task.input->>'operation' IS DISTINCT FROM 'inventory'
 OR jsonb_typeof(task.input->'input') IS DISTINCT FROM 'object'
 OR jsonb_typeof(task.input->'input'->'limit') IS DISTINCT FROM 'number'
 OR (task.input->'input'->>'limit') !~ '^([1-9]|[1-4][0-9]|50)$'
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 item_limit:=(task.input->'input'->>'limit')::integer;
 IF (SELECT count(*)<>8 FROM jsonb_object_keys(stage_row.payload))
 OR jsonb_typeof(stage_row.payload->'result_id') IS DISTINCT FROM 'string'
 OR (stage_row.payload->>'result_id') !~
  '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
 OR stage_row.payload->>'task_id' IS DISTINCT FROM task.id::text
 OR stage_row.payload->>'workspace_id' IS DISTINCT FROM task.workspace_id::text
 OR jsonb_typeof(stage_row.payload->'task_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(stage_row.payload->'workspace_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(stage_row.payload->'measured_at') IS DISTINCT FROM 'string'
 OR length(stage_row.payload->>'measured_at')>64
 OR stage_row.payload->>'scope' IS DISTINCT FROM 'first_authorized_visible_records'
 OR jsonb_typeof(stage_row.payload->'scope') IS DISTINCT FROM 'string'
 OR jsonb_typeof(stage_row.payload->'limit') IS DISTINCT FROM 'number'
 OR stage_row.payload->'limit' IS DISTINCT FROM to_jsonb(item_limit)
 OR stage_row.payload->'policy_epoch' IS DISTINCT FROM
  jsonb_build_array(facts.workspace_epoch,facts.policy_epoch,facts.workspace_epoch)
 OR jsonb_typeof(stage_row.payload->'items') IS DISTINCT FROM 'array'
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 IF jsonb_array_length(stage_row.payload->'items')>least(item_limit,50)
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(stage_row.payload->'items')
  WITH ORDINALITY AS staged(value,ordinal) ORDER BY ordinal LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object'
  OR jsonb_typeof(item->'resource_id') IS DISTINCT FROM 'string'
  OR (item->>'resource_id') !~
   '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
  OR jsonb_typeof(item->'kind') IS DISTINCT FROM 'string'
  OR item->>'kind' NOT IN ('document','knowledge','reference')
  OR jsonb_typeof(item->'revision') IS DISTINCT FROM 'number'
  OR (item->>'revision') !~ '^[1-9][0-9]{{0,15}}$'
  OR jsonb_typeof(item->'resource_epoch') IS DISTINCT FROM 'number'
  OR (item->>'resource_epoch') !~ '^[1-9][0-9]{{0,15}}$'
  THEN RETURN jsonb_build_object('status','lost'); END IF;
  item_id:=(item->>'resource_id')::uuid;
  item_revision:=(item->>'revision')::bigint;
  item_epoch:=(item->>'resource_epoch')::bigint;
  IF item_revision>9007199254740991 OR item_epoch>9007199254740991
  OR (previous_id IS NOT NULL AND item_id<=previous_id)
  OR item IS DISTINCT FROM jsonb_build_object('resource_id',item_id,
   'kind',item->>'kind','revision',item_revision,'resource_epoch',item_epoch)
  THEN RETURN jsonb_build_object('status','lost'); END IF;
  previous_id:=item_id;
  SELECT r.kind,r.policy_epoch,d.revision,r.valid_until INTO current_item
  FROM access_resource r JOIN discovery_record d ON d.resource_id=r.id
  WHERE r.id=item_id AND r.workspace_id=task.workspace_id
  AND d.kind=r.kind AND d.visibility='visible'
  AND length(r.title) BETWEEN 1 AND 512
  AND r.valid_from<=clock_timestamp()
  AND (r.valid_until IS NULL OR r.valid_until>clock_timestamp())
  AND r.classification BETWEEN 0 AND facts.clearance AND r.policy_epoch>0
  AND (r.project_id=ANY(facts.project_scope) OR '*'=ANY(facts.project_scope))
  AND (r.customer_id=ANY(facts.customer_scope) OR '*'=ANY(facts.customer_scope))
  AND (r.product_id=ANY(facts.product_scope) OR '*'=ANY(facts.product_scope))
  AND (r.department=ANY(facts.department_scope) OR '*'=ANY(facts.department_scope))
  AND (facts.owner_scope='any' OR r.owner_id=facts.actor_id)
  AND r.approval_state=ANY(facts.approval_states)
  FOR SHARE OF r,d;
  IF NOT FOUND THEN RETURN jsonb_build_object('status','authorization_denied'); END IF;
  IF current_item.kind IS DISTINCT FROM item->>'kind'
  OR current_item.revision IS DISTINCT FROM item_revision
  OR current_item.policy_epoch IS DISTINCT FROM item_epoch
  THEN RETURN jsonb_build_object('status','authorization_denied'); END IF;
  IF current_item.valid_until IS NOT NULL THEN
   earliest_valid_until:=least(earliest_valid_until,current_item.valid_until);
  END IF;
 END LOOP;
 -- Row locks keep the checked resource and discovery revisions stable until
 -- commit; wall-clock expiry and the task lease still require a final check.
 IF earliest_valid_until IS NOT NULL AND earliest_valid_until<=clock_timestamp()
 THEN RETURN jsonb_build_object('status','authorization_denied'); END IF;
 IF NOT eid_inventory_allowed(task,clock_timestamp())
 THEN RETURN jsonb_build_object('status','authorization_denied'); END IF;
 IF inbox.lease_until<=clock_timestamp() OR attempt_row.lease_until<=clock_timestamp()
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 result_uuid:=(stage_row.payload->>'result_id')::uuid;
 INSERT INTO task_result(id,task_id,payload)
 VALUES(result_uuid,task.id,stage_row.payload);
 UPDATE durable_task SET state='SUCCEEDED',stage='done',result_id=result_uuid,
 current_seq=current_seq+1,updated_at=clock_timestamp()
 WHERE id=task.id RETURNING * INTO task;
 UPDATE task_attempt SET state='SUCCEEDED',completed_at=clock_timestamp()
 WHERE task_id=task.id AND attempt=task.attempt AND owner_token=p_owner AND fence_token=p_fence;
 IF NOT FOUND THEN RAISE EXCEPTION 'Attempt ownership mismatch'; END IF;
 UPDATE task_inbox SET state='processed',processed_at=clock_timestamp()
 WHERE consumer='inventory-v1' AND event_id=p_event AND owner_token=p_owner;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.succeeded','SUCCEEDED');
 RETURN jsonb_build_object('status','SUCCEEDED','result_id',result_uuid);
END $$;

-- Retry classification is a closed inventory-specific set. No caller can
-- choose a delay, attempt count, diagnostic body or terminal state.
CREATE FUNCTION eid_task_fail_v2(p_event uuid,p_owner uuid,p_fence bigint,p_kind text)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; attempt_row task_attempt; inbox task_inbox;
        now_at timestamptz; terminal boolean; code text; class_name text;
        delay_seconds double precision; effective_kind text;
BEGIN
 IF session_user<>'eid_worker' OR p_kind IS NULL OR p_kind NOT IN
 ('transient_dependency','format_repairable','invalid_input','authorization_denied')
 THEN RAISE EXCEPTION 'Invalid Worker failure classification'; END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_outbox o ON o.task_id=t.id
 WHERE o.event_id=p_event;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','lost'); END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 SELECT * INTO inbox FROM task_inbox WHERE consumer='inventory-v1' AND event_id=p_event FOR UPDATE;
 SELECT * INTO attempt_row FROM task_attempt WHERE task_id=task.id AND attempt=task.attempt FOR UPDATE;
 now_at:=clock_timestamp();
 IF task.state<>'RUNNING' OR task.cancel_requested OR task.current_event_id IS DISTINCT FROM p_event
 OR task.fence_token IS DISTINCT FROM p_fence OR attempt_row.owner_token IS DISTINCT FROM p_owner
 OR attempt_row.fence_token IS DISTINCT FROM p_fence OR attempt_row.state IS DISTINCT FROM 'RUNNING'
 OR attempt_row.lease_until<=now_at OR inbox.owner_token IS DISTINCT FROM p_owner
 OR inbox.state IS DISTINCT FROM 'received' OR inbox.lease_until<=now_at
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 -- The Worker may report a transient error after access or input changed.
 -- Current server-side facts and stored input take priority over its label.
 effective_kind:=p_kind;
 IF NOT eid_inventory_allowed(task,now_at) THEN
  effective_kind:='authorization_denied';
 ELSIF task.input->>'operation' IS DISTINCT FROM 'inventory'
 OR jsonb_typeof(task.input->'input') IS DISTINCT FROM 'object'
 OR jsonb_typeof(task.input->'input'->'limit') IS DISTINCT FROM 'number'
 OR (task.input->'input'->>'limit') !~ '^([1-9]|[1-4][0-9]|50)$' THEN
  effective_kind:='invalid_input';
 END IF;
 IF effective_kind='invalid_input' THEN
  IF task.input->>'operation'='inventory'
  AND jsonb_typeof(task.input->'input')='object'
  AND jsonb_typeof(task.input->'input'->'limit')='number'
  AND (task.input->'input'->>'limit') ~ '^([1-9]|[1-4][0-9]|50)$'
  THEN RAISE EXCEPTION 'Invalid input classification does not match stored task'; END IF;
  code:='INVALID_INVENTORY_INPUT'; class_name:='PERMANENT'; terminal:=true;
 ELSIF effective_kind='authorization_denied' THEN
  IF eid_inventory_allowed(task,now_at) THEN
   RAISE EXCEPTION 'Authorization classification does not match current facts'; END IF;
  code:='AUTHORIZATION_EXPIRED_OR_REVOKED'; class_name:='PERMANENT'; terminal:=true;
 ELSIF effective_kind='format_repairable' THEN
  code:='FORMAT_REPAIRABLE'; class_name:='FORMAT';
  terminal:=task.format_repairs>=1 OR task.attempt>=3;
 ELSE
  code:='TRANSIENT_DEPENDENCY'; class_name:='TRANSIENT'; terminal:=task.attempt>=3;
 END IF;
 UPDATE task_attempt SET state='ABANDONED',completed_at=now_at
 WHERE task_id=task.id AND attempt=task.attempt AND fence_token=p_fence;
 UPDATE task_inbox SET state='processed',processed_at=now_at
 WHERE consumer='inventory-v1' AND event_id=p_event;
 IF terminal THEN
  UPDATE durable_task SET state=CASE WHEN class_name='PERMANENT' THEN 'FAILED' ELSE 'DEAD_LETTER' END,
  stage=CASE WHEN class_name='PERMANENT' THEN 'failed' ELSE 'dead_letter' END,
  error_code=CASE WHEN class_name='PERMANENT' THEN code ELSE 'ATTEMPTS_EXHAUSTED' END,
  error_class=CASE WHEN class_name='PERMANENT' THEN class_name ELSE 'ATTEMPTS_EXHAUSTED' END,
  current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
  INSERT INTO task_event(event_id,task_id,seq,event_type,state)
  VALUES(gen_random_uuid(),task.id,task.current_seq,
  CASE WHEN task.state='FAILED' THEN 'task.failed' ELSE 'task.dead_letter' END,task.state);
 ELSE
  delay_seconds:=least(60.0,power(2.0,task.attempt::double precision))
   + (mod(hashtextextended(task.id::text||':'||task.fence_token::text,0)
     & 9223372036854775807::bigint,1000)::double precision/1000.0);
  UPDATE durable_task SET state='RETRY_WAIT',stage='retry_wait',
  next_retry_at=now_at+make_interval(secs=>delay_seconds),
  error_code=NULL,error_class=class_name,
  format_repairs=format_repairs+CASE WHEN class_name='FORMAT' THEN 1 ELSE 0 END,
  current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
  INSERT INTO task_event(event_id,task_id,seq,event_type,state)
  VALUES(gen_random_uuid(),task.id,task.current_seq,'task.retry_wait','RETRY_WAIT');
 END IF;
 RETURN jsonb_build_object('status',task.state,'next_retry_at',task.next_retry_at,
 'error_code',task.error_code,'error_class',task.error_class);
END $$;

CREATE FUNCTION eid_task_stop_v2(p_event uuid,p_owner uuid,p_fence bigint)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; attempt_row task_attempt; now_at timestamptz;
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_outbox o ON o.task_id=t.id WHERE o.event_id=p_event;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','lost'); END IF;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 SELECT * INTO attempt_row FROM task_attempt WHERE task_id=task.id AND attempt=task.attempt FOR UPDATE;
 now_at:=clock_timestamp();
 IF task.state<>'RUNNING' OR NOT task.cancel_requested
 OR task.current_event_id IS DISTINCT FROM p_event OR task.fence_token IS DISTINCT FROM p_fence
 OR attempt_row.owner_token IS DISTINCT FROM p_owner OR attempt_row.fence_token IS DISTINCT FROM p_fence
 OR attempt_row.state IS DISTINCT FROM 'RUNNING' OR attempt_row.lease_until<=now_at
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 UPDATE task_attempt SET state='ABANDONED',completed_at=now_at
 WHERE task_id=task.id AND attempt=task.attempt;
 UPDATE task_inbox SET state='processed',processed_at=now_at
 WHERE consumer='inventory-v1' AND event_id=p_event AND owner_token=p_owner
 AND state='received' AND lease_until>now_at;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbox ownership mismatch'; END IF;
 UPDATE durable_task SET state='CANCELLED',stage='cancelled',current_seq=current_seq+1,
 updated_at=now_at WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.cancelled','CANCELLED');
 RETURN jsonb_build_object('status','CANCELLED','external_effect_state',task.external_effect_state);
END $$;

CREATE FUNCTION eid_task_cancel_v2(p_task uuid,p_actor uuid,p_request_id text)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; facts access_current_facts; now_at timestamptz;
BEGIN
 IF session_user<>'eid_api' OR p_task IS NULL OR p_actor IS NULL
 OR p_request_id IS NULL OR p_request_id !~ '^[A-Za-z0-9._-]{{1,128}}$'
 THEN RAISE EXCEPTION 'Invalid API cancellation context'; END IF;
 SELECT * INTO task FROM durable_task WHERE id=p_task;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','not_found'); END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=p_task FOR UPDATE;
 SELECT * INTO facts FROM access_current_facts
 WHERE actor_id=p_actor AND workspace_id=task.workspace_id;
 now_at:=clock_timestamp();
 IF task.actor_id IS DISTINCT FROM p_actor OR facts.actor_id IS NULL
 OR NOT facts.identity_active OR NOT facts.membership_active
 OR cardinality(facts.roles)=0
 OR NOT facts.roles <@ ARRAY['author','expert','quality','template_admin',
  'knowledge_admin','approver','system_admin']::text[]
 OR facts.classification>facts.clearance
 OR facts.policy_epoch<=0 OR facts.workspace_epoch<=0
 OR (facts.project_id=ANY(facts.project_scope) OR '*'=ANY(facts.project_scope)) IS NOT TRUE
 OR (facts.customer_id=ANY(facts.customer_scope) OR '*'=ANY(facts.customer_scope)) IS NOT TRUE
 OR (facts.product_id=ANY(facts.product_scope) OR '*'=ANY(facts.product_scope)) IS NOT TRUE
 OR (facts.department=ANY(facts.department_scope) OR '*'=ANY(facts.department_scope)) IS NOT TRUE
 OR facts.valid_from>now_at OR (facts.valid_until IS NOT NULL AND facts.valid_until<=now_at)
 THEN RETURN jsonb_build_object('status','forbidden'); END IF;
 IF task.state='CANCELLED' THEN
  RETURN jsonb_build_object('status','cancel_requested','state','CANCELLED',
   'external_effect_state',task.external_effect_state);
 END IF;
 IF task.state IN ('SUCCEEDED','BLOCKED','FAILED','DEAD_LETTER') THEN
  RETURN jsonb_build_object('status','too_late','state',task.state);
 END IF;
 IF task.cancel_requested THEN
  RETURN jsonb_build_object('status','cancel_requested','state',task.state);
 END IF;
 INSERT INTO access_audit(id,workspace_id,actor_id,target_id,action,before_policy,
 after_policy,request_id,occurred_at)
 VALUES(gen_random_uuid(),task.workspace_id,p_actor,task.id,'task.cancel_requested',
 jsonb_build_object('state',task.state,'fence_token',task.fence_token),
 jsonb_build_object('cancel_requested',true),p_request_id,now_at);
 IF task.state='RUNNING' THEN
  UPDATE durable_task SET cancel_requested=true,cancel_requested_at=now_at,
  current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
  INSERT INTO task_event(event_id,task_id,seq,event_type,state)
  VALUES(gen_random_uuid(),task.id,task.current_seq,'task.cancel_requested','RUNNING');
 ELSE
  UPDATE durable_task SET cancel_requested=true,cancel_requested_at=now_at,
  state='CANCELLED',stage='cancelled',next_retry_at=NULL,
  current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
  INSERT INTO task_event(event_id,task_id,seq,event_type,state)
  VALUES(gen_random_uuid(),task.id,task.current_seq,'task.cancelled','CANCELLED');
 END IF;
 RETURN jsonb_build_object('status','cancel_requested','state',task.state,
 'external_effect_state',task.external_effect_state);
END $$;

CREATE OR REPLACE FUNCTION eid_task_block_dependency(p_task uuid) RETURNS boolean
LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task;
BEGIN
 SELECT * INTO task FROM durable_task WHERE id=p_task FOR UPDATE;
 IF NOT FOUND OR task.state<>'QUEUED' THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM task_dependency d JOIN durable_task predecessor
  ON predecessor.id=d.depends_on WHERE d.task_id=task.id
  AND predecessor.state IN ('BLOCKED','FAILED','CANCELLED','DEAD_LETTER')) THEN RETURN false; END IF;
 UPDATE durable_task SET state='BLOCKED',stage='blocked',error_code='DEPENDENCY_BLOCKED',
 error_class='PERMANENT',current_seq=current_seq+1,updated_at=clock_timestamp()
 WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.blocked','BLOCKED');
 RETURN true;
END $$;

CREATE FUNCTION eid_task_scheduler_lease_v2(p_owner uuid) RETURNS jsonb
LANGUAGE plpgsql {security} AS $$
DECLARE lease_row task_scheduler_lease; now_at timestamptz;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT * INTO lease_row FROM task_scheduler_lease WHERE singleton FOR UPDATE;
 now_at:=clock_timestamp();
 IF lease_row.owner_token IS NOT NULL AND lease_row.owner_token<>p_owner
 AND lease_row.lease_until>now_at THEN RETURN jsonb_build_object('status','busy'); END IF;
 IF lease_row.owner_token IS DISTINCT FROM p_owner OR lease_row.lease_until<=now_at THEN
  IF lease_row.fence_token>=9007199254740991 THEN RAISE EXCEPTION 'Scheduler fence exhausted'; END IF;
  UPDATE task_scheduler_lease SET owner_token=p_owner,fence_token=fence_token+1,
  lease_until=now_at+interval '15 seconds' WHERE singleton RETURNING * INTO lease_row;
 ELSE
  UPDATE task_scheduler_lease SET lease_until=now_at+interval '15 seconds'
  WHERE singleton RETURNING * INTO lease_row;
 END IF;
 RETURN jsonb_build_object('status','leased','fence_token',lease_row.fence_token,
 'lease_until',lease_row.lease_until);
END $$;

-- The API needs a narrow readiness fact without a table grant or lease token.
CREATE FUNCTION eid_task_scheduler_ready_v2() RETURNS boolean
LANGUAGE plpgsql {security} AS $$
BEGIN
 IF session_user<>'eid_api' THEN RAISE EXCEPTION 'API identity required'; END IF;
 RETURN coalesce((SELECT lease_until>clock_timestamp()
  FROM task_scheduler_lease WHERE singleton=true),false);
END $$;
REVOKE ALL ON FUNCTION eid_task_scheduler_ready_v2() FROM PUBLIC,eid_worker;
GRANT EXECUTE ON FUNCTION eid_task_scheduler_ready_v2() TO eid_api;

-- One short transaction handles one expired lease or due retry. The durable
-- next_retry_at field is the only execution retry clock. Relay handles transport
-- retries independently; it cannot create an Attempt or change a fence.
CREATE FUNCTION eid_task_schedule_v2(p_owner uuid,p_scheduler_fence bigint)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE leader task_scheduler_lease; task durable_task; attempt_row task_attempt;
        old_outbox task_outbox; now_at timestamptz; delay_seconds double precision;
        new_event uuid; new_envelope jsonb;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL OR p_scheduler_fence IS NULL
 THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 IF NOT pg_try_advisory_xact_lock(45133,15) THEN
  RETURN jsonb_build_object('status','busy'); END IF;
 SELECT * INTO leader FROM task_scheduler_lease WHERE singleton FOR UPDATE;
 now_at:=clock_timestamp();
 IF leader.owner_token IS DISTINCT FROM p_owner
 OR leader.fence_token IS DISTINCT FROM p_scheduler_fence OR leader.lease_until<=now_at
 THEN RETURN jsonb_build_object('status','lost'); END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_attempt a
  ON a.task_id=t.id AND a.attempt=t.attempt
 WHERE t.state='RUNNING' AND a.state='RUNNING' AND a.lease_until<=now_at
 ORDER BY a.lease_until,t.id FOR UPDATE OF t SKIP LOCKED LIMIT 1;
 IF FOUND THEN
  SELECT * INTO attempt_row FROM task_attempt
  WHERE task_id=task.id AND attempt=task.attempt FOR UPDATE;
  now_at:=clock_timestamp();
  IF attempt_row.lease_until>now_at THEN RETURN jsonb_build_object('status','busy'); END IF;
  UPDATE task_attempt SET state='ABANDONED',completed_at=now_at
  WHERE task_id=task.id AND attempt=task.attempt;
  IF task.fence_token>=9007199254740991 THEN RAISE EXCEPTION 'Task fence exhausted'; END IF;
  IF task.cancel_requested THEN
   UPDATE durable_task SET state='CANCELLED',stage='cancelled',fence_token=fence_token+1,
   current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
   INSERT INTO task_event(event_id,task_id,seq,event_type,state)
   VALUES(gen_random_uuid(),task.id,task.current_seq,'task.cancelled','CANCELLED');
  ELSIF task.attempt>=3 THEN
   UPDATE durable_task SET state='DEAD_LETTER',stage='dead_letter',
   error_code='ATTEMPTS_EXHAUSTED',error_class='ATTEMPTS_EXHAUSTED',
   fence_token=fence_token+1,current_seq=current_seq+1,updated_at=now_at
   WHERE id=task.id RETURNING * INTO task;
   INSERT INTO task_event(event_id,task_id,seq,event_type,state)
   VALUES(gen_random_uuid(),task.id,task.current_seq,'task.dead_letter','DEAD_LETTER');
  ELSE
   delay_seconds:=least(60.0,power(2.0,task.attempt::double precision))
    + (mod(hashtextextended(task.id::text||':'||task.fence_token::text,0)
      & 9223372036854775807::bigint,1000)::double precision/1000.0);
   UPDATE durable_task SET state='RETRY_WAIT',stage='retry_wait',
   fence_token=fence_token+1,error_class='LEASE_EXPIRED',
   next_retry_at=now_at+make_interval(secs=>delay_seconds),
   current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
   INSERT INTO task_event(event_id,task_id,seq,event_type,state)
   VALUES(gen_random_uuid(),task.id,task.current_seq,'task.retry_wait','RETRY_WAIT');
  END IF;
  RETURN jsonb_build_object('status',task.state,'task_id',task.id,
  'fence_token',task.fence_token,'next_retry_at',task.next_retry_at);
 END IF;
 SELECT * INTO task FROM durable_task WHERE state='RETRY_WAIT'
 AND next_retry_at<=now_at ORDER BY next_retry_at,id FOR UPDATE SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','idle'); END IF;
 IF task.cancel_requested OR task.attempt>=3 THEN RAISE EXCEPTION 'Invalid retry plan'; END IF;
 SELECT * INTO old_outbox FROM task_outbox WHERE event_id=task.current_event_id;
 IF NOT FOUND OR old_outbox.task_id<>task.id THEN RAISE EXCEPTION 'Missing retry template'; END IF;
 new_event:=gen_random_uuid();
 new_envelope:=old_outbox.envelope || jsonb_build_object(
  'event_id',new_event,
  'occurred_at',to_char(now_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
 IF jsonb_typeof(new_envelope)<>'object' OR octet_length(new_envelope::text)>8192
 THEN RAISE EXCEPTION 'Retry envelope exceeds bound'; END IF;
 UPDATE durable_task SET state='QUEUED',stage='waiting',next_retry_at=NULL,
 current_seq=current_seq+1,updated_at=now_at WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(new_event,task.id,task.current_seq,'task.queued','QUEUED');
 INSERT INTO task_outbox(event_id,task_id,envelope,envelope_hash,available_at)
 VALUES(new_event,task.id,new_envelope,eid_task_envelope_hash(new_envelope),now_at);
 UPDATE durable_task SET current_event_id=new_event WHERE id=task.id;
 RETURN jsonb_build_object('status','queued','task_id',task.id,'event_id',new_event);
END $$;

REVOKE ALL ON FUNCTION eid_task_claim_v2(uuid,jsonb,text,uuid),
 eid_task_heartbeat_v2(uuid,uuid,bigint),eid_task_stage_inventory_v2(uuid,uuid,bigint),
 eid_task_finish_inventory_v2(uuid,uuid,bigint,text,text),
 eid_task_fail_v2(uuid,uuid,bigint,text),eid_task_stop_v2(uuid,uuid,bigint),
 eid_task_cancel_v2(uuid,uuid,text),eid_task_scheduler_lease_v2(uuid),
 eid_task_schedule_v2(uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_task_claim_v2(uuid,jsonb,text,uuid),
 eid_task_heartbeat_v2(uuid,uuid,bigint),eid_task_stage_inventory_v2(uuid,uuid,bigint),
 eid_task_finish_inventory_v2(uuid,uuid,bigint,text,text),
 eid_task_fail_v2(uuid,uuid,bigint,text),eid_task_stop_v2(uuid,uuid,bigint),
 eid_task_scheduler_lease_v2(uuid),eid_task_schedule_v2(uuid,bigint) TO eid_worker;
GRANT EXECUTE ON FUNCTION eid_task_cancel_v2(uuid,uuid,text) TO eid_api;
""")


def downgrade():
    raise RuntimeError("Fenced recovery is forward-only; preserve task and attempt history")
