"""Expand-only durable inventory tasks; Worker receives function grants, not table access."""
from alembic import op

revision = "0008_durable_submission"
down_revision = "0007_workspace_discovery"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE durable_task (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 delegation_id uuid NOT NULL UNIQUE REFERENCES access_delegation(id),
 operation text NOT NULL DEFAULT 'inventory' CHECK (operation='inventory'),
 category text NOT NULL DEFAULT 'integration' CHECK (category='integration'),
 input jsonb NOT NULL CHECK (jsonb_typeof(input)='object' AND octet_length(input::text)<=4096),
 input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','BLOCKED')),
 stage text NOT NULL DEFAULT 'waiting' CHECK (stage IN ('waiting','inventory','done','blocked')),
 attempt bigint NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 9007199254740991),
 current_seq bigint NOT NULL DEFAULT 1 CHECK (current_seq BETWEEN 1 AND 9007199254740991),
 result_id uuid UNIQUE,
 error_code text CHECK (error_code IN ('AUTHORIZATION_EXPIRED_OR_REVOKED','DEPENDENCY_BLOCKED',
                                      'INVALID_INVENTORY_INPUT')),
 request_id text NOT NULL CHECK (request_id ~ '^[A-Za-z0-9._-]{1,128}$'),
 trace_id text NOT NULL CHECK (trace_id ~ '^[0-9a-f]{32}$' AND trace_id<>repeat('0',32)),
 created_at timestamptz NOT NULL CHECK (isfinite(created_at)),
 updated_at timestamptz NOT NULL CHECK (isfinite(updated_at) AND updated_at>=created_at),
 CHECK ((state='SUCCEEDED')=(result_id IS NOT NULL)),
 CHECK ((state='BLOCKED')=(error_code IS NOT NULL)),
 CHECK ((state,stage) IN (('QUEUED','waiting'),('RUNNING','inventory'),
                        ('SUCCEEDED','done'),('BLOCKED','blocked')))
);
CREATE INDEX durable_task_owner ON durable_task(workspace_id,actor_id,created_at,id);
CREATE INDEX durable_task_state ON durable_task(state,updated_at,id);
CREATE TABLE task_dependency (
 task_id uuid NOT NULL REFERENCES durable_task(id),
 depends_on uuid NOT NULL REFERENCES durable_task(id),
 PRIMARY KEY(task_id,depends_on), CHECK (task_id<>depends_on)
);
CREATE INDEX task_dependency_successors ON task_dependency(depends_on,task_id);
CREATE TABLE task_event (
 event_id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES durable_task(id),
 seq bigint NOT NULL CHECK (seq BETWEEN 1 AND 9007199254740991),
 event_type text NOT NULL CHECK (event_type IN ('task.queued','task.running','task.succeeded','task.blocked')),
 state text NOT NULL CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','BLOCKED')),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(occurred_at)),
 UNIQUE(task_id,seq)
);
CREATE TABLE task_outbox (
 event_id uuid PRIMARY KEY REFERENCES task_event(event_id),
 task_id uuid NOT NULL UNIQUE REFERENCES durable_task(id),
 envelope jsonb NOT NULL CHECK (jsonb_typeof(envelope)='object' AND octet_length(envelope::text)<=8192),
 envelope_hash text NOT NULL CHECK (envelope_hash ~ '^[0-9a-f]{64}$'),
 owner_token uuid, lease_until timestamptz CHECK (isfinite(lease_until)),
 published_at timestamptz CHECK (isfinite(published_at)),
 quarantined_at timestamptz CHECK (isfinite(quarantined_at)),
 available_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(available_at)),
 publish_attempts bigint NOT NULL DEFAULT 0 CHECK (publish_attempts>=0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(created_at)),
 CHECK ((owner_token IS NULL)=(lease_until IS NULL))
);
CREATE INDEX task_outbox_pending ON task_outbox(available_at,created_at,event_id);
CREATE UNIQUE INDEX task_outbox_owner ON task_outbox(owner_token) WHERE owner_token IS NOT NULL;
CREATE TABLE task_inbox (
 consumer text NOT NULL CHECK (consumer='inventory-v1'),
 event_id uuid NOT NULL REFERENCES task_outbox(event_id),
 task_id uuid NOT NULL UNIQUE REFERENCES durable_task(id),
 payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 state text NOT NULL DEFAULT 'received' CHECK (state IN ('received','processed')),
 owner_token uuid NOT NULL, lease_until timestamptz NOT NULL CHECK (isfinite(lease_until)),
 received_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(received_at)),
 processed_at timestamptz CHECK (isfinite(processed_at)),
 PRIMARY KEY(consumer,event_id), CHECK ((state='processed')=(processed_at IS NOT NULL))
);
CREATE INDEX task_inbox_recovery ON task_inbox(lease_until) WHERE state='received';
CREATE TABLE task_attempt (
 task_id uuid NOT NULL REFERENCES durable_task(id),
 attempt bigint NOT NULL CHECK (attempt BETWEEN 1 AND 9007199254740991),
 owner_token uuid NOT NULL UNIQUE,
 state text NOT NULL CHECK (state IN ('RUNNING','ABANDONED','SUCCEEDED','BLOCKED')),
 started_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(started_at)),
 completed_at timestamptz CHECK (isfinite(completed_at)),
 PRIMARY KEY(task_id,attempt), CHECK ((state='RUNNING')=(completed_at IS NULL))
);
CREATE TABLE task_result (
 id uuid PRIMARY KEY, task_id uuid NOT NULL UNIQUE REFERENCES durable_task(id),
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object' AND octet_length(payload::text)<=16384),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(created_at)),
 UNIQUE(id,task_id)
);
ALTER TABLE durable_task ADD CONSTRAINT durable_task_result_binding
 FOREIGN KEY(result_id,id) REFERENCES task_result(id,task_id);
CREATE TABLE task_receipt (
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
 payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 task_id uuid NOT NULL UNIQUE REFERENCES durable_task(id),
 audit_id uuid NOT NULL UNIQUE REFERENCES access_audit(id),
 PRIMARY KEY(actor_id,workspace_id,idempotency_key)
);
CREATE TABLE task_quarantine (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), consumer text NOT NULL DEFAULT 'inventory-v1',
 event_id uuid, payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 reason text NOT NULL CHECK (reason IN ('INVALID_ENVELOPE','UNSUPPORTED_VERSION','BINDING_MISMATCH',
                                       'STORED_ENVELOPE_HASH_MISMATCH','TERMINAL_INBOX_INCONSISTENT')),
 schema_version text CHECK (length(schema_version)<=32),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(occurred_at)),
 UNIQUE NULLS NOT DISTINCT(event_id,payload_hash,reason)
);
CREATE INDEX task_quarantine_event ON task_quarantine(event_id);
REVOKE ALL ON durable_task,task_dependency,task_event,task_outbox,task_inbox,
 task_attempt,task_result,task_receipt,task_quarantine FROM PUBLIC,eid_worker;
GRANT SELECT ON durable_task,task_dependency,task_receipt,task_result TO eid_api;
GRANT INSERT ON durable_task,task_dependency,task_event,task_outbox,task_receipt TO eid_api;
""")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    # Explicit pg_temp last prevents caller-created temporary objects shadowing tables.
    security = f"SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}, pg_temp"
    op.execute(f"""
CREATE FUNCTION eid_task_quarantine(p_event uuid,p_hash text,p_reason text,p_version text)
RETURNS void LANGUAGE plpgsql {security} AS $$
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 INSERT INTO task_quarantine(event_id,payload_hash,reason,schema_version)
 VALUES(p_event,p_hash,p_reason,left(p_version,32)) ON CONFLICT DO NOTHING;
END $$;

-- Internal only. A terminal blocked predecessor can never satisfy this edge.
-- Only queued work is propagated; no attempt or business execution is created.
CREATE FUNCTION eid_task_block_dependency(p_task uuid) RETURNS boolean
LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task;
BEGIN
 SELECT * INTO task FROM durable_task WHERE id=p_task FOR UPDATE;
 IF NOT FOUND OR task.state<>'QUEUED' THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM task_dependency d JOIN durable_task t ON t.id=d.depends_on
               WHERE d.task_id=task.id AND t.state='BLOCKED') THEN RETURN false; END IF;
 UPDATE durable_task SET state='BLOCKED',stage='blocked',error_code='DEPENDENCY_BLOCKED',
 current_seq=current_seq+1,updated_at=clock_timestamp() WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.blocked','BLOCKED');
 RETURN true;
END $$;

CREATE FUNCTION eid_task_relay_claim(p_owner uuid) RETURNS jsonb
LANGUAGE plpgsql {security} AS $$
DECLARE chosen task_outbox; blocked_id uuid; propagated integer;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 -- Bound each scan transaction, including deep chains/fanout. Later polls resume
 -- from durable state. Each iteration can see the previous propagation's write.
 FOR propagated IN 1..64 LOOP
  SELECT t.id INTO blocked_id FROM durable_task t
  WHERE t.state='QUEUED' AND EXISTS(
   SELECT 1 FROM task_dependency d JOIN durable_task predecessor ON predecessor.id=d.depends_on
   WHERE d.task_id=t.id AND predecessor.state='BLOCKED')
  ORDER BY t.created_at,t.id FOR UPDATE OF t SKIP LOCKED LIMIT 1;
  EXIT WHEN NOT FOUND;
  PERFORM eid_task_block_dependency(blocked_id);
 END LOOP;
 SELECT o.* INTO chosen FROM task_outbox o
 -- A confirm is a transport receipt, not business completion. Recover even a
 -- confirmed message lost to a broker delivery limit or a crashed consumer.
 WHERE o.available_at<=clock_timestamp()
 AND o.quarantined_at IS NULL
 AND (o.lease_until IS NULL OR o.lease_until<=clock_timestamp())
 AND EXISTS(SELECT 1 FROM durable_task t WHERE t.id=o.task_id AND t.state IN ('QUEUED','RUNNING'))
 AND NOT EXISTS(SELECT 1 FROM task_inbox i WHERE i.event_id=o.event_id
                AND (i.state='processed' OR i.lease_until>clock_timestamp()))
 AND NOT EXISTS(SELECT 1 FROM task_dependency d JOIN durable_task t ON t.id=d.depends_on
                WHERE d.task_id=o.task_id AND t.state<>'SUCCEEDED')
 ORDER BY o.available_at,o.created_at,o.event_id FOR UPDATE OF o SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE task_outbox SET owner_token=p_owner,lease_until=clock_timestamp()+interval '30 seconds',
 available_at=clock_timestamp()+interval '30 seconds',
 publish_attempts=publish_attempts+1 WHERE event_id=chosen.event_id;
 RETURN jsonb_build_object('event_id',chosen.event_id,'task_id',chosen.task_id,
                           'envelope',chosen.envelope,'envelope_hash',chosen.envelope_hash);
END $$;

CREATE FUNCTION eid_task_relay_confirm(p_event uuid,p_owner uuid,p_envelope jsonb,p_hash text)
RETURNS boolean
LANGUAGE plpgsql {security} AS $$
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 UPDATE task_outbox SET published_at=coalesce(published_at,clock_timestamp()),
 available_at=clock_timestamp()+interval '30 seconds',owner_token=NULL,lease_until=NULL
 WHERE event_id=p_event AND owner_token=p_owner AND lease_until>clock_timestamp()
 AND quarantined_at IS NULL AND envelope::text=p_envelope::text AND envelope_hash=p_hash;
 RETURN FOUND;
END $$;

-- A relay can inspect an invalid stored JSON object without trusting its event_id.
-- The database event ID, current lease, stored body, and claimed hash fence stale
-- owners and repaired rows. The diagnostic fingerprint hashes stored JSONB text,
-- not wire JSON.
CREATE FUNCTION eid_task_relay_quarantine(p_owner uuid,p_event uuid,p_envelope jsonb,
                                          p_hash text,p_reason text,p_version text) RETURNS boolean
LANGUAGE plpgsql {security} AS $$
DECLARE chosen task_outbox;
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 IF p_owner IS NULL OR p_event IS NULL OR p_envelope IS NULL OR p_hash IS NULL
 OR jsonb_typeof(p_envelope)<>'object'
 OR p_reason IS NULL OR p_reason NOT IN ('INVALID_ENVELOPE','UNSUPPORTED_VERSION',
                                        'BINDING_MISMATCH','STORED_ENVELOPE_HASH_MISMATCH')
 OR (p_version IS NOT NULL AND p_version !~ '^[0-9.]{{1,32}}$')
 THEN RAISE EXCEPTION 'Invalid relay quarantine request'; END IF;
 SELECT * INTO chosen FROM task_outbox
 WHERE event_id=p_event AND owner_token=p_owner AND lease_until>clock_timestamp()
 AND quarantined_at IS NULL AND envelope::text=p_envelope::text AND envelope_hash=p_hash
 FOR UPDATE;
 IF NOT FOUND THEN RETURN false; END IF;
 -- This fingerprint identifies the persisted body, independent of caller data.
 INSERT INTO task_quarantine(event_id,payload_hash,reason,schema_version)
 VALUES(chosen.event_id,encode(sha256(convert_to(chosen.envelope::text,'UTF8')),'hex'),
        p_reason,p_version) ON CONFLICT DO NOTHING;
 UPDATE task_outbox SET quarantined_at=clock_timestamp(),owner_token=NULL,lease_until=NULL
 WHERE event_id=chosen.event_id AND owner_token=p_owner;
 RETURN FOUND;
END $$;

CREATE FUNCTION eid_task_claim(p_event uuid,p_envelope jsonb,p_hash text,p_owner uuid)
RETURNS text LANGUAGE plpgsql {security} AS $$
DECLARE outbox task_outbox; task durable_task; inbox task_inbox; has_inbox boolean;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT * INTO outbox FROM task_outbox WHERE event_id=p_event;
 -- JSONB equality treats 1 and 1.0 as equal although their wire hashes differ.
 -- Compare JSONB's stable text as well, before attributing corruption to storage.
 IF NOT FOUND OR outbox.envelope::text IS DISTINCT FROM p_envelope::text THEN
  PERFORM eid_task_quarantine(p_event,p_hash,'BINDING_MISMATCH',p_envelope->>'message_schema_version');
  RETURN 'quarantined';
 END IF;
 IF outbox.envelope_hash IS DISTINCT FROM p_hash THEN
  -- Only the exact stored body can establish stored corruption. An unrelated
  -- broker payload must never suppress this event's legitimate delivery.
  PERFORM eid_task_quarantine(p_event,p_hash,'STORED_ENVELOPE_HASH_MISMATCH',
                              p_envelope->>'message_schema_version');
  UPDATE task_outbox SET quarantined_at=coalesce(quarantined_at,clock_timestamp())
  WHERE event_id=p_event AND envelope::text=p_envelope::text AND envelope_hash=outbox.envelope_hash;
  RETURN 'quarantined';
 END IF;
 SELECT * INTO task FROM durable_task WHERE id=outbox.task_id FOR UPDATE;
 IF outbox.envelope->>'source' IS DISTINCT FROM 'eid-api'
 OR outbox.envelope->>'message_schema_version' IS DISTINCT FROM '1.0'
 OR outbox.envelope->>'event_type' IS DISTINCT FROM 'task.inventory.requested'
 OR outbox.envelope->>'category' IS DISTINCT FROM 'integration'
 OR outbox.envelope->>'event_id' IS DISTINCT FROM p_event::text
 OR outbox.envelope->>'task_id' IS DISTINCT FROM task.id::text
 OR outbox.envelope->>'aggregate_id' IS DISTINCT FROM task.id::text
 OR outbox.envelope->>'aggregate_version' IS DISTINCT FROM '1'
 OR outbox.envelope->>'input_ref' IS DISTINCT FROM task.id::text
 OR outbox.envelope->>'actor_id' IS DISTINCT FROM task.actor_id::text
 OR outbox.envelope->>'workspace_id' IS DISTINCT FROM task.workspace_id::text
 OR outbox.envelope->>'delegation_id' IS DISTINCT FROM task.delegation_id::text
 OR outbox.envelope->>'input_hash' IS DISTINCT FROM task.input_hash
 OR outbox.envelope->>'request_id' IS DISTINCT FROM task.request_id
 OR outbox.envelope->>'trace_id' IS DISTINCT FROM task.trace_id THEN
  PERFORM eid_task_quarantine(p_event,p_hash,'BINDING_MISMATCH',p_envelope->>'message_schema_version');
  RETURN 'quarantined';
 END IF;
 -- A delivery can arrive before the relay's next scan. Apply the same terminal
 -- dependency rule while holding this task's lock, before any execution claim.
 IF eid_task_block_dependency(task.id) THEN
  SELECT * INTO task FROM durable_task WHERE id=task.id;
 END IF;
 SELECT * INTO inbox FROM task_inbox WHERE consumer='inventory-v1' AND event_id=p_event FOR UPDATE;
 has_inbox:=FOUND;
 IF has_inbox THEN
  IF inbox.payload_hash<>p_hash THEN
   PERFORM eid_task_quarantine(p_event,p_hash,'BINDING_MISMATCH','1.0'); RETURN 'quarantined';
  END IF;
  IF inbox.state='processed' THEN RETURN 'processed'; END IF;
 END IF;
 IF task.state='BLOCKED' AND task.error_code='DEPENDENCY_BLOCKED'
 AND task.attempt=0 AND NOT has_inbox THEN
  INSERT INTO task_inbox(consumer,event_id,task_id,payload_hash,owner_token,lease_until,
                         state,processed_at)
  VALUES('inventory-v1',p_event,task.id,p_hash,p_owner,clock_timestamp(),
         'processed',clock_timestamp());
  RETURN 'processed';
 END IF;
 IF task.state NOT IN ('QUEUED','RUNNING') THEN
  -- Do not invent a completion receipt for a terminal task whose atomic Inbox
  -- record is absent or unfinished. Preserve the result and an inspectable fault.
  PERFORM eid_task_quarantine(p_event,p_hash,'TERMINAL_INBOX_INCONSISTENT','1.0');
  RETURN 'quarantined';
 END IF;
 IF has_inbox AND inbox.lease_until>clock_timestamp() THEN RETURN 'busy'; END IF;
 IF EXISTS(SELECT 1 FROM task_dependency d JOIN durable_task t ON t.id=d.depends_on
           WHERE d.task_id=task.id AND t.state<>'SUCCEEDED') THEN RETURN 'busy'; END IF;
 INSERT INTO task_inbox(consumer,event_id,task_id,payload_hash,owner_token,lease_until)
 VALUES('inventory-v1',p_event,task.id,p_hash,p_owner,clock_timestamp()+interval '30 seconds')
 ON CONFLICT(consumer,event_id) DO UPDATE
 SET owner_token=p_owner,lease_until=clock_timestamp()+interval '30 seconds';
 UPDATE task_attempt SET state='ABANDONED',completed_at=clock_timestamp()
 WHERE task_id=task.id AND state='RUNNING';
 UPDATE durable_task SET state='RUNNING',stage='inventory',attempt=attempt+1,
 current_seq=current_seq+1,updated_at=clock_timestamp() WHERE id=task.id RETURNING * INTO task;
 INSERT INTO task_attempt(task_id,attempt,owner_token,state) VALUES(task.id,task.attempt,p_owner,'RUNNING');
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,'task.running','RUNNING');
 RETURN 'claimed';
END $$;

-- Internal only. The definer holds the workspace lock before reading current facts.
-- This predicate is inventory:read from access.policy, including the stored capability.
CREATE FUNCTION eid_inventory_allowed(p_task durable_task,p_now timestamptz) RETURNS boolean
LANGUAGE sql {security} AS $$
 SELECT EXISTS(SELECT 1 FROM access_current_facts f JOIN access_delegation d
 ON d.actor_id=f.actor_id AND d.workspace_id=f.workspace_id
 WHERE f.actor_id=p_task.actor_id AND f.workspace_id=p_task.workspace_id
 AND d.id=p_task.delegation_id AND d.active AND d.service_id='eid-worker'
 AND d.resource_id IS NULL AND d.operation='inventory:read' AND d.purpose='task:'||p_task.id::text
 AND d.request_id=p_task.request_id AND d.trace_id=p_task.trace_id
 AND d.expires_at>p_now AND d.issued_epoch=f.workspace_epoch
 AND f.identity_active AND f.membership_active AND cardinality(f.roles)>0
 AND f.roles <@ ARRAY['author','expert','quality','template_admin','knowledge_admin','approver','system_admin']::text[]
 AND f.approval_states <@ ARRAY['draft','in_review','approved','rejected']::text[]
 AND f.valid_from<=p_now AND (f.valid_until IS NULL OR f.valid_until>p_now)
 AND f.classification BETWEEN 0 AND f.clearance AND f.clearance BETWEEN 0 AND 3
 AND f.policy_epoch>0 AND f.workspace_epoch>0
 AND (f.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
 AND (f.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
 AND (f.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
 AND (f.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope)))
$$;

CREATE FUNCTION eid_task_finish_inventory(p_event uuid,p_owner uuid) RETURNS text
LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; inbox task_inbox; facts access_current_facts;
        v_result_id uuid; result_payload jsonb; items jsonb; outcome text; now_at timestamptz;
        item_limit integer; failure_code text:='AUTHORIZATION_EXPIRED_OR_REVOKED';
BEGIN
 IF session_user<>'eid_worker' THEN RAISE EXCEPTION 'Worker identity required'; END IF;
 SELECT t.* INTO task FROM durable_task t JOIN task_outbox o ON o.task_id=t.id WHERE o.event_id=p_event;
 IF NOT FOUND THEN RAISE EXCEPTION 'Unknown event'; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=task.id FOR UPDATE;
 SELECT * INTO inbox FROM task_inbox WHERE consumer='inventory-v1' AND event_id=p_event FOR UPDATE;
 IF NOT FOUND OR inbox.owner_token IS DISTINCT FROM p_owner OR inbox.lease_until<=clock_timestamp()
 OR inbox.state<>'received' OR task.state<>'RUNNING' THEN RETURN 'lost'; END IF;
 now_at:=clock_timestamp();
 outcome:='BLOCKED';
 IF eid_inventory_allowed(task,now_at) THEN
  -- Validate before casting: malformed/missing/string/boolean/oversized input is
  -- deterministic poison, while an expired execution lease remains recoverable.
  IF task.input->>'operation' IS DISTINCT FROM 'inventory'
  OR jsonb_typeof(task.input->'input') IS DISTINCT FROM 'object'
  OR jsonb_typeof(task.input->'input'->'limit') IS DISTINCT FROM 'number'
  OR (task.input->'input'->>'limit') !~ '^([1-9]|[1-4][0-9]|50)$' THEN
   failure_code:='INVALID_INVENTORY_INPUT';
  ELSE
  SELECT * INTO facts FROM access_current_facts
   WHERE actor_id=task.actor_id AND workspace_id=task.workspace_id;
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
  -- Expiration is checked again after the bounded projection, before acceptance.
  IF eid_inventory_allowed(task,clock_timestamp()) THEN
   v_result_id:=gen_random_uuid();
   result_payload:=jsonb_build_object('result_id',v_result_id,'task_id',task.id,
      'workspace_id',task.workspace_id,'measured_at',now_at,
      'scope','first_authorized_visible_records','limit',item_limit,'items',items,
      'policy_epoch',jsonb_build_array(facts.workspace_epoch,facts.policy_epoch,facts.workspace_epoch));
   INSERT INTO task_result(id,task_id,payload) VALUES(v_result_id,task.id,result_payload);
   outcome:='SUCCEEDED';
  END IF;
  END IF;
 END IF;
 IF inbox.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'Inventory lease expired'; END IF;
 UPDATE durable_task SET state=outcome,stage=CASE WHEN outcome='SUCCEEDED' THEN 'done' ELSE 'blocked' END,
 result_id=v_result_id,
 error_code=CASE WHEN outcome='BLOCKED' THEN failure_code END,
 current_seq=current_seq+1,updated_at=clock_timestamp() WHERE id=task.id RETURNING * INTO task;
 UPDATE task_attempt SET state=outcome,completed_at=clock_timestamp()
 WHERE task_id=task.id AND attempt=task.attempt AND owner_token=p_owner AND state='RUNNING';
 IF NOT FOUND THEN RAISE EXCEPTION 'Attempt ownership mismatch'; END IF;
 INSERT INTO task_event(event_id,task_id,seq,event_type,state)
 VALUES(gen_random_uuid(),task.id,task.current_seq,
        CASE WHEN outcome='SUCCEEDED' THEN 'task.succeeded' ELSE 'task.blocked' END,outcome);
 UPDATE task_inbox SET state='processed',processed_at=clock_timestamp()
 WHERE consumer='inventory-v1' AND event_id=p_event AND owner_token=p_owner;
 -- Successor Outboxes already exist atomically with their submissions. Their
 -- eligibility is evaluated from committed dependencies by relay, never cached.
 -- No successor intent can become visible before this completion commits.
 RETURN outcome;
END $$;

REVOKE ALL ON FUNCTION eid_task_quarantine(uuid,text,text,text),eid_task_block_dependency(uuid),
 eid_task_relay_claim(uuid),
 eid_task_relay_confirm(uuid,uuid,jsonb,text),eid_task_relay_quarantine(uuid,uuid,jsonb,text,text,text),
 eid_task_claim(uuid,jsonb,text,uuid),
 eid_inventory_allowed(durable_task,timestamptz),eid_task_finish_inventory(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_task_quarantine(uuid,text,text,text),eid_task_relay_claim(uuid),
 eid_task_relay_confirm(uuid,uuid,jsonb,text),eid_task_relay_quarantine(uuid,uuid,jsonb,text,text,text),
 eid_task_claim(uuid,jsonb,text,uuid),
 eid_task_finish_inventory(uuid,uuid) TO eid_worker;
""")


def downgrade():
    raise RuntimeError("Task migration is forward-only; preserve tasks, receipts and delivery history")
