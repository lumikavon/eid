"""Expand durable task observation without pruning task or event history."""
from alembic import op


revision = "0010_task_observation"
down_revision = "0009_fenced_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
ALTER TABLE durable_task DROP CONSTRAINT durable_task_operation_check;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_category_check;
ALTER TABLE durable_task ADD CONSTRAINT durable_task_operation_v3
 CHECK (operation ~ '^[a-z][a-z0-9_]{0,63}$');
ALTER TABLE durable_task ADD CONSTRAINT durable_task_category_v3
 CHECK (category IN ('generation','retrieval','review','parse_ocr','render','integration'));
ALTER TABLE durable_task ADD COLUMN parent_task_id uuid,
 ADD COLUMN event_floor_seq bigint NOT NULL DEFAULT 1
 CHECK (event_floor_seq BETWEEN 1 AND 9007199254740991 AND event_floor_seq<=current_seq),
 ADD CONSTRAINT durable_task_parent_not_self CHECK (parent_task_id IS NULL OR parent_task_id<>id);
CREATE UNIQUE INDEX durable_task_parent_owner_key ON durable_task(id,workspace_id,actor_id);
ALTER TABLE durable_task ADD CONSTRAINT durable_task_parent_owner_fk
 FOREIGN KEY(parent_task_id,workspace_id,actor_id)
 REFERENCES durable_task(id,workspace_id,actor_id);
CREATE INDEX durable_task_parent ON durable_task(parent_task_id,id)
 WHERE parent_task_id IS NOT NULL;

-- Observation provenance is written by the API's server-side binding function.
-- A task may refer to several local resources; every one must remain authorized.
CREATE UNIQUE INDEX access_resource_observation_workspace_key
 ON access_resource(id,workspace_id);
CREATE TABLE task_observation_binding (
 task_id uuid NOT NULL, workspace_id uuid NOT NULL, actor_id uuid NOT NULL,
 resource_id uuid NOT NULL, workspace_epoch bigint NOT NULL CHECK (workspace_epoch>0),
 policy_epoch bigint NOT NULL CHECK (policy_epoch>0),
 resource_epoch bigint NOT NULL CHECK (resource_epoch>0),
 authority text NOT NULL CHECK (authority='local_access_resource'),
 PRIMARY KEY(task_id,resource_id),
 FOREIGN KEY(task_id,workspace_id,actor_id)
  REFERENCES durable_task(id,workspace_id,actor_id),
 FOREIGN KEY(resource_id,workspace_id)
  REFERENCES access_resource(id,workspace_id)
);
CREATE INDEX task_observation_binding_resource ON task_observation_binding(resource_id,task_id);
REVOKE ALL ON task_observation_binding FROM PUBLIC,eid_worker,eid_api;
GRANT SELECT ON task_observation_binding TO eid_api;

ALTER TABLE durable_task DROP CONSTRAINT durable_task_state_stage_v2;
ALTER TABLE durable_task DROP CONSTRAINT durable_task_stage_v2;
ALTER TABLE durable_task ADD CONSTRAINT durable_task_stage_v3 CHECK
 (stage IN ('waiting','inventory','working','retry_wait','done','blocked','failed',
            'cancelled','dead_letter'));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_state_stage_v3 CHECK
 ((state,stage) IN (('QUEUED','waiting'),('RUNNING','inventory'),('RUNNING','working'),
 ('RETRY_WAIT','retry_wait'),('SUCCEEDED','done'),('BLOCKED','blocked'),
 ('FAILED','failed'),('CANCELLED','cancelled'),('DEAD_LETTER','dead_letter')));
ALTER TABLE durable_task ADD CONSTRAINT durable_task_inventory_stage_v3 CHECK
 (state<>'RUNNING' OR (operation='inventory' AND category='integration')=(stage='inventory'));

CREATE TABLE task_notification (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 task_id uuid NOT NULL,
 event_seq bigint NOT NULL,
 event_type text NOT NULL CHECK (event_type IN
  ('task.succeeded','task.blocked','task.failed','task.cancelled','task.dead_letter')),
 state text NOT NULL CHECK (state IN ('SUCCEEDED','BLOCKED','FAILED','CANCELLED','DEAD_LETTER')),
 created_at timestamptz NOT NULL CHECK (isfinite(created_at)),
 read_at timestamptz CHECK (read_at IS NULL OR (isfinite(read_at) AND read_at>=created_at)),
 UNIQUE(task_id,event_seq),
 FOREIGN KEY(task_id,workspace_id,actor_id)
  REFERENCES durable_task(id,workspace_id,actor_id),
 FOREIGN KEY(task_id,event_seq) REFERENCES task_event(task_id,seq)
);
CREATE INDEX task_notification_owner
 ON task_notification(workspace_id,actor_id,created_at DESC,id DESC);
CREATE INDEX task_notification_owner_unread
 ON task_notification(workspace_id,actor_id,created_at DESC,id DESC)
 WHERE read_at IS NULL;
REVOKE ALL ON task_notification FROM PUBLIC,eid_worker,eid_api;
GRANT SELECT ON task_notification,task_event TO eid_api;
""")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    security = f"SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}, pg_temp"
    op.execute(f"""
-- Internal SQL decision is required because mark-read is SECURITY DEFINER.
-- It must independently reject revoked or incomplete resource bindings.
CREATE FUNCTION eid_task_observation_allowed_v1(p_task uuid,p_actor uuid)
RETURNS boolean LANGUAGE sql {security} AS $$
 SELECT EXISTS (
  SELECT 1 FROM durable_task t JOIN access_current_facts f
   ON f.actor_id=t.actor_id AND f.workspace_id=t.workspace_id
  WHERE t.id=p_task AND t.actor_id=p_actor
   AND f.identity_active AND f.membership_active
   AND cardinality(f.roles)>0
   AND f.roles <@ ARRAY['author','expert','quality','template_admin',
     'knowledge_admin','approver','system_admin']::text[]
   AND f.approval_states <@ ARRAY['draft','in_review','approved','rejected']::text[]
   AND f.valid_from<=clock_timestamp()
   AND (f.valid_until IS NULL OR f.valid_until>clock_timestamp())
   AND f.classification BETWEEN 0 AND f.clearance AND f.clearance BETWEEN 0 AND 3
   AND f.policy_epoch>0 AND f.workspace_epoch>0
   AND (f.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
   AND (f.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
   AND (f.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
   AND (f.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope))
   AND ((t.operation='inventory' AND t.category='integration') OR
    (EXISTS (SELECT 1 FROM task_observation_binding b WHERE b.task_id=t.id)
     AND NOT EXISTS (
      SELECT 1 FROM task_observation_binding b
      LEFT JOIN access_resource r ON r.id=b.resource_id AND r.workspace_id=b.workspace_id
      LEFT JOIN discovery_record d ON d.resource_id=r.id
      WHERE b.task_id=t.id AND (b.workspace_id IS DISTINCT FROM t.workspace_id
       OR b.actor_id IS DISTINCT FROM t.actor_id
       OR b.authority IS DISTINCT FROM 'local_access_resource'
       OR b.workspace_epoch IS DISTINCT FROM f.workspace_epoch
       OR b.policy_epoch IS DISTINCT FROM f.policy_epoch
       OR r.id IS NULL OR d.resource_id IS NULL OR d.kind IS DISTINCT FROM r.kind
       OR d.visibility IS DISTINCT FROM 'visible'
       OR b.resource_epoch IS DISTINCT FROM r.policy_epoch
       OR r.valid_from>clock_timestamp()
       OR (r.valid_until IS NOT NULL AND r.valid_until<=clock_timestamp())
       OR r.classification NOT BETWEEN 0 AND f.clearance
       OR (r.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope)) IS NOT TRUE
       OR (r.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope)) IS NOT TRUE
       OR (r.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope)) IS NOT TRUE
       OR (r.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope)) IS NOT TRUE
       OR (f.owner_scope='any' OR r.owner_id=f.actor_id) IS NOT TRUE
       OR (r.approval_state=ANY(f.approval_states)) IS NOT TRUE))))
 )
$$;
REVOKE ALL ON FUNCTION eid_task_observation_allowed_v1(uuid,uuid)
 FROM PUBLIC,eid_api,eid_worker;

-- Only a trusted API handler may bind local records. External ACLs require a
-- separate authoritative proof path and have no binding entry point here.
CREATE FUNCTION eid_task_bind_observation_v1(p_task uuid,p_actor uuid,p_resources uuid[])
RETURNS boolean LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; facts access_current_facts; requested integer; accepted integer;
BEGIN
 IF session_user<>'eid_api' OR p_task IS NULL OR p_actor IS NULL
 OR p_resources IS NULL OR array_position(p_resources,NULL) IS NOT NULL
 OR cardinality(p_resources) NOT BETWEEN 1 AND 32
 THEN RAISE EXCEPTION 'Invalid task observation binding'; END IF;
 SELECT * INTO task FROM durable_task WHERE id=p_task;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=task.workspace_id FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=p_task FOR UPDATE;
 IF task.actor_id IS DISTINCT FROM p_actor OR task.state<>'QUEUED'
 OR task.current_seq<>1 OR (task.operation='inventory' AND task.category='integration')
 OR EXISTS(SELECT 1 FROM task_observation_binding WHERE task_id=p_task)
 THEN RETURN false; END IF;
 SELECT * INTO facts FROM access_current_facts
 WHERE actor_id=p_actor AND workspace_id=task.workspace_id;
 IF facts.actor_id IS NULL OR facts.identity_active IS NOT TRUE
 OR facts.membership_active IS NOT TRUE OR cardinality(facts.roles)=0
 OR (facts.roles <@ ARRAY['author','expert','quality','template_admin',
     'knowledge_admin','approver','system_admin']::text[]) IS NOT TRUE
 OR (facts.approval_states <@ ARRAY['draft','in_review','approved','rejected']::text[]) IS NOT TRUE
 OR (facts.classification BETWEEN 0 AND facts.clearance) IS NOT TRUE
 OR (facts.clearance BETWEEN 0 AND 3) IS NOT TRUE
 OR facts.policy_epoch<=0 OR facts.workspace_epoch<=0
 OR (facts.project_id=ANY(facts.project_scope) OR '*'=ANY(facts.project_scope)) IS NOT TRUE
 OR (facts.customer_id=ANY(facts.customer_scope) OR '*'=ANY(facts.customer_scope)) IS NOT TRUE
 OR (facts.product_id=ANY(facts.product_scope) OR '*'=ANY(facts.product_scope)) IS NOT TRUE
 OR (facts.department=ANY(facts.department_scope) OR '*'=ANY(facts.department_scope)) IS NOT TRUE
 OR facts.valid_from>clock_timestamp()
 OR (facts.valid_until IS NOT NULL AND facts.valid_until<=clock_timestamp())
 THEN RETURN false; END IF;
 SELECT count(*),count(DISTINCT id) INTO requested,accepted
 FROM unnest(p_resources) AS requested_id(id);
 IF requested<>accepted THEN RETURN false; END IF;
 PERFORM 1 FROM access_resource r JOIN discovery_record d ON d.resource_id=r.id
 WHERE r.id=ANY(p_resources) AND r.workspace_id=task.workspace_id
 FOR SHARE OF r,d;
 SELECT count(*) INTO accepted FROM access_resource r
 JOIN discovery_record d ON d.resource_id=r.id AND d.kind=r.kind AND d.visibility='visible'
 WHERE r.id=ANY(p_resources) AND r.workspace_id=task.workspace_id
 AND r.valid_from<=clock_timestamp()
 AND (r.valid_until IS NULL OR r.valid_until>clock_timestamp())
 AND r.classification BETWEEN 0 AND facts.clearance AND r.policy_epoch>0
 AND (r.project_id=ANY(facts.project_scope) OR '*'=ANY(facts.project_scope))
 AND (r.customer_id=ANY(facts.customer_scope) OR '*'=ANY(facts.customer_scope))
 AND (r.product_id=ANY(facts.product_scope) OR '*'=ANY(facts.product_scope))
 AND (r.department=ANY(facts.department_scope) OR '*'=ANY(facts.department_scope))
 AND (facts.owner_scope='any' OR r.owner_id=facts.actor_id)
 AND r.approval_state=ANY(facts.approval_states);
 IF requested<>accepted THEN RETURN false; END IF;
 INSERT INTO task_observation_binding(task_id,workspace_id,actor_id,resource_id,
  workspace_epoch,policy_epoch,resource_epoch,authority)
 SELECT task.id,task.workspace_id,task.actor_id,r.id,facts.workspace_epoch,
  facts.policy_epoch,r.policy_epoch,'local_access_resource'
 FROM access_resource r WHERE r.id=ANY(p_resources) AND r.workspace_id=task.workspace_id;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION eid_task_bind_observation_v1(uuid,uuid,uuid[]) FROM PUBLIC,eid_worker;
GRANT EXECUTE ON FUNCTION eid_task_bind_observation_v1(uuid,uuid,uuid[]) TO eid_api;

CREATE FUNCTION eid_task_notification_v1() RETURNS trigger
LANGUAGE plpgsql {security} AS $$
DECLARE owner_task durable_task;
BEGIN
 IF NEW.event_type NOT IN ('task.succeeded','task.blocked','task.failed',
  'task.cancelled','task.dead_letter') THEN RETURN NEW; END IF;
 SELECT * INTO owner_task FROM durable_task WHERE id=NEW.task_id;
 IF NOT FOUND OR owner_task.current_seq<>NEW.seq OR owner_task.state<>NEW.state
 THEN RAISE EXCEPTION 'Task notification binding mismatch'; END IF;
 INSERT INTO task_notification(workspace_id,actor_id,task_id,event_seq,event_type,state,created_at)
 VALUES(owner_task.workspace_id,owner_task.actor_id,NEW.task_id,NEW.seq,
        NEW.event_type,NEW.state,NEW.occurred_at);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION eid_task_notification_v1() FROM PUBLIC,eid_api,eid_worker;
CREATE TRIGGER task_event_notify AFTER INSERT ON task_event
 FOR EACH ROW EXECUTE FUNCTION eid_task_notification_v1();

CREATE FUNCTION eid_notification_mark_read_v1(p_notification uuid,p_actor uuid)
RETURNS boolean LANGUAGE plpgsql {security} AS $$
DECLARE target task_notification; target_workspace uuid; now_at timestamptz;
BEGIN
 IF session_user<>'eid_api' OR p_notification IS NULL OR p_actor IS NULL
 THEN RAISE EXCEPTION 'Invalid API notification context'; END IF;
 SELECT workspace_id INTO target_workspace FROM task_notification
 WHERE id=p_notification AND actor_id=p_actor;
 IF NOT FOUND THEN RETURN false; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=target_workspace FOR SHARE;
 SELECT * INTO target FROM task_notification WHERE id=p_notification FOR UPDATE;
 IF NOT FOUND OR target.actor_id<>p_actor OR target.workspace_id<>target_workspace
 THEN RETURN false; END IF;
 now_at:=clock_timestamp();
 IF eid_task_observation_allowed_v1(target.task_id,p_actor) IS NOT TRUE
 THEN RETURN false; END IF;
 UPDATE task_notification SET read_at=coalesce(read_at,now_at) WHERE id=target.id;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION eid_notification_mark_read_v1(uuid,uuid) FROM PUBLIC,eid_worker;
GRANT EXECUTE ON FUNCTION eid_notification_mark_read_v1(uuid,uuid) TO eid_api;

-- The 0009 cancellation entry point predates external-effect states. Fence the
-- decision under the task lock before invoking it, and remove direct API access
-- to the older entry point so a concurrent effect cannot be falsely cancelled.
CREATE FUNCTION eid_task_cancel_observed_v1(p_task uuid,p_actor uuid,p_request_id text)
RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE task durable_task; workspace uuid;
BEGIN
 IF session_user<>'eid_api' OR p_task IS NULL OR p_actor IS NULL
 OR p_request_id IS NULL OR p_request_id !~ '^[A-Za-z0-9._-]{{1,128}}$'
 THEN RAISE EXCEPTION 'Invalid API cancellation context'; END IF;
 SELECT workspace_id INTO workspace FROM durable_task WHERE id=p_task;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','not_found'); END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=workspace FOR SHARE;
 SELECT * INTO task FROM durable_task WHERE id=p_task FOR UPDATE;
 IF NOT FOUND OR task.workspace_id<>workspace OR task.actor_id<>p_actor
 THEN RETURN jsonb_build_object('status','not_found'); END IF;
 IF task.operation<>'inventory' OR task.category<>'integration'
 OR task.external_effect_state<>'none'
 THEN RETURN jsonb_build_object('status','action_unavailable'); END IF;
 RETURN eid_task_cancel_v2(p_task,p_actor,p_request_id);
END $$;
REVOKE ALL ON FUNCTION eid_task_cancel_observed_v1(uuid,uuid,text) FROM PUBLIC,eid_worker;
GRANT EXECUTE ON FUNCTION eid_task_cancel_observed_v1(uuid,uuid,text) TO eid_api;
REVOKE EXECUTE ON FUNCTION eid_task_cancel_v2(uuid,uuid,text) FROM eid_api;
""")
    # Existing terminal events remain history. This adds one durable notification
    # per actual terminal transition without changing any old task/event row.
    op.execute("""
INSERT INTO task_notification(workspace_id,actor_id,task_id,event_seq,event_type,state,created_at)
SELECT t.workspace_id,t.actor_id,e.task_id,e.seq,e.event_type,e.state,e.occurred_at
FROM task_event e JOIN durable_task t ON t.id=e.task_id
WHERE e.event_type IN ('task.succeeded','task.blocked','task.failed',
 'task.cancelled','task.dead_letter')
ON CONFLICT(task_id,event_seq) DO NOTHING;
""")


def downgrade():
    raise RuntimeError("Task observation is forward-only; preserve events and notifications")
