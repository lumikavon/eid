import copy
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

from scripts import verify_access_fixtures as verifier
from scripts.seed_access_fixtures import fixture_lock


@pytest.mark.parametrize(("selector", "port"), [(None, 55432), ("seadee-develop", 15432)])
def test_audit_probe_captures_input_before_guard_can_consume_stdin(monkeypatch, capsys, selector, port):
    """Execute the actual embedded Python with a stdin-consuming guard and no I/O."""
    import psycopg
    from scripts import verify_local_environment

    if selector is None:
        monkeypatch.delenv("EID_ENVIRONMENT_CONFIG", raising=False)
    else:
        monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
    text = Path("tests/ux/access.spec.ts").read_text(encoding="utf-8")
    source = text.split("function auditEvidence(id:string){", 1)[1].split("const source=`", 1)[1].split("`;", 1)[0]
    identifier = "d877bbad-044b-4b5f-840a-77b10e378a32"
    monkeypatch.setattr(sys, "stdin", StringIO(json.dumps({"id": identifier})))
    events = []

    def guard(url):
        assert url == f"postgresql+psycopg://eid_migrator:local-migrate-only@localhost:{port}/eid_local_dev"
        events.append("guard")
        # SSH subprocesses may inherit stdin. The audit identifier must already
        # be captured before target verification launches them.
        assert sys.stdin.read() == ""

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, parameters=None):
            if parameters is None:
                return SimpleNamespace(fetchone=lambda: {"db": "eid_local_dev", "role": "eid_migrator"})
            assert "FROM access_audit WHERE id=%s" in statement
            assert str(parameters[0]) == identifier
            events.append("audit")
            return SimpleNamespace(fetchone=lambda: {"audit_id": identifier})

    def connect(url, **options):
        assert events == ["guard"]
        assert url == f"postgresql://eid_migrator:local-migrate-only@localhost:{port}/eid_local_dev"
        assert "default_transaction_read_only=on" in options["options"]
        events.append("connect")
        return Connection()

    monkeypatch.setattr(verify_local_environment, "verify_migration_target", guard)
    monkeypatch.setattr(psycopg, "connect", connect)
    exec(compile(source, "<embedded-audit-probe>", "exec"), {})
    assert events == ["guard", "connect", "audit"]
    assert json.loads(capsys.readouterr().out) == {"audit_id": identifier}


def fixture_documents(nonce="current-owner"):
    def identifier(name):
        return str(uuid5(NAMESPACE_URL, "eid-access-fixture:" + nonce + ":" + name))
    users = {role: {"username": "eid-access-" + role.replace("_", "-"),
                    "subject": str(uuid5(NAMESPACE_URL, "test-subject:" + role)),
                    "actor_id": identifier(role), "resource_id": identifier("resource-" + role)}
             for role in verifier.ROLES}
    manifest = {"fixture": "local-acceptance-only",
                "workspaces": [identifier("workspace-a"), identifier("workspace-b")], "users": users}
    receipts = {user["username"]: {"id": user["subject"], "nonce": nonce}
                for user in users.values()}
    return manifest, receipts


@pytest.fixture
def state(monkeypatch, tmp_path):
    selected = tmp_path / ".local" / "remote" / "seadee-develop"
    selected.mkdir(parents=True)
    manifest, receipts = fixture_documents()
    for filename, value in (("access-fixtures.json", manifest), ("access-fixture-receipts.json", receipts)):
        (selected / filename).write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(verifier, "environment_state_directory", lambda _: selected)
    monkeypatch.setattr(verifier, "_recorded_owner_nonce", lambda: "current-owner")
    monkeypatch.setattr(verifier, "verify_migration_target", lambda _: None)
    return selected


def test_manifest_preserves_seed_order_and_accepts_only_current_receipts():
    manifest, receipts = fixture_documents()
    assert verifier.validate_manifest(manifest, receipts, "current-owner") == manifest
    with pytest.raises(RuntimeError, match="current owner"):
        verifier.validate_manifest(manifest, receipts, "stale-owner")


@pytest.mark.parametrize("mutation", [
    lambda m, r: m.update(fixture="production"),
    lambda m, r: m.update(extra=True),
    lambda m, r: m["workspaces"].reverse(),
    lambda m, r: m["users"].pop("approver"),
    lambda m, r: m["users"].update(unknown={}),
    lambda m, r: m["users"]["author"].update(extra="secret"),
    lambda m, r: m["users"]["author"].update(username="other-user"),
    lambda m, r: m["users"]["author"].update(subject="invalid"),
    lambda m, r: m["users"]["author"].update(subject=m["users"]["expert"]["subject"]),
    lambda m, r: m["users"]["author"].update(actor_id=m["users"]["expert"]["actor_id"]),
    lambda m, r: m["users"]["author"].update(resource_id=m["users"]["expert"]["resource_id"]),
    lambda m, r: r["eid-access-author"].update(nonce="stale-owner"),
    lambda m, r: r["eid-access-author"].update(id=m["users"]["expert"]["subject"]),
    lambda m, r: r["eid-access-author"].update(extra=True),
    lambda m, r: r.pop("eid-access-author"),
    lambda m, r: r.update(unknown={}),
])
def test_stale_or_malformed_fixture_evidence_is_rejected_without_repair(mutation):
    manifest, receipts = fixture_documents()
    mutation(manifest, receipts)
    before = copy.deepcopy((manifest, receipts))
    with pytest.raises(RuntimeError):
        verifier.validate_manifest(manifest, receipts, "current-owner")
    assert (manifest, receipts) == before


def test_preflight_is_readonly_and_runs_full_target_guard(state, monkeypatch):
    before = {path.name: path.read_bytes() for path in state.iterdir()}
    calls = []
    monkeypatch.setattr(verifier, "verify_migration_target", calls.append)
    result = verifier.preflight(state)
    assert result["state_directory"] == str(state.resolve())
    assert result["fixtures"] == fixture_documents()[0]
    assert calls == [verifier.development_database_url()]
    assert {path.name: path.read_bytes() for path in state.iterdir()} == before


def test_remote_missing_manifest_never_uses_existing_legacy_local_manifest(state, monkeypatch):
    (state / "access-fixtures.json").unlink()
    local = state.parent.parent / "access-fixtures.json"
    local.write_text(json.dumps(fixture_documents()[0]))
    monkeypatch.setattr(verifier, "verify_migration_target", lambda _: pytest.fail("no service calls"))
    with pytest.raises(RuntimeError, match="Missing or linked fixture evidence"):
        verifier.preflight()


def test_explicit_legacy_state_requires_the_same_manifest_contract(state, monkeypatch):
    local = state.parent.parent
    for name in ("access-fixtures.json", "access-fixture-receipts.json"):
        (local / name).write_bytes((state / name).read_bytes())
    monkeypatch.setattr(verifier, "environment_state_directory", lambda _: local)
    assert verifier.preflight()["state_directory"] == str(local.resolve())


@pytest.mark.parametrize("selector", ["", " ", "unknown", "../other/environment.yaml"])
def test_invalid_environment_selector_fails_before_any_local_fallback(monkeypatch, selector):
    monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", selector)
    monkeypatch.setattr(verifier, "_recorded_owner_nonce", lambda: pytest.fail("no owner fallback"))
    with pytest.raises(RuntimeError, match="远端环境选择无效"):
        verifier.preflight()


def test_pending_restoration_blocks_preflight_before_guard(state, monkeypatch):
    (state / verifier.RECOVERY_MARKER).write_text("incomplete recovery evidence")
    monkeypatch.setattr(verifier, "verify_migration_target", lambda _: pytest.fail("no service calls"))
    with pytest.raises(RuntimeError, match="Unresolved UX fixture recovery"):
        verifier.preflight()


@pytest.mark.parametrize("drift", ["owner", "selector", "manifest", "receipt", "state"])
def test_preflight_rejects_changes_during_target_verification(state, monkeypatch, drift):
    def guard(_):
        if drift == "owner":
            monkeypatch.setattr(verifier, "_recorded_owner_nonce", lambda: "changed")
        elif drift == "selector":
            monkeypatch.setenv("EID_ENVIRONMENT_CONFIG", "changed")
        elif drift == "state":
            monkeypatch.setattr(verifier, "environment_state_directory", lambda _: state.parent)
        else:
            filename = "access-fixtures.json" if drift == "manifest" else "access-fixture-receipts.json"
            (state / filename).write_text("{}")
    monkeypatch.setattr(verifier, "verify_migration_target", guard)
    with pytest.raises(RuntimeError, match="changed"):
        verifier.preflight()


def test_duplicate_json_fields_are_not_silently_accepted(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text('{"fixture":"wrong","fixture":"local-acceptance-only"}')
    with pytest.raises(RuntimeError, match="Duplicate"):
        verifier.read_document(path)


def test_helper_holds_seed_lock_until_parent_pipe_closes_without_external_calls(tmp_path):
    # The child replaces only the preflight in this isolated protocol test; production
    # main has no bypass selector. No live service or project receipt is involved.
    source = """import sys
from pathlib import Path
from scripts import verify_access_fixtures as module
state=Path(sys.argv[1])
module.environment_state_directory=lambda _:state
module.preflight=lambda _: {'status':'test-only'}
sys.argv=['verify_access_fixtures','--hold-lock']
module.main()
"""
    child = subprocess.Popen([sys.executable, "-c", source, str(tmp_path)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    lines = queue.Queue()
    thread = threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True)
    thread.start()
    try:
        assert json.loads(lines.get(timeout=15)) == {"status": "test-only"}
        with pytest.raises(RuntimeError, match="Another local fixture seed"):
            with fixture_lock(tmp_path / "access-fixtures.lock"):
                pytest.fail("lock must remain held")
        child.stdin.close()
        assert child.wait(timeout=10) == 0, child.stderr.read()
        with fixture_lock(tmp_path / "access-fixtures.lock"):
            pass
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


UX_HELPER_HARNESS = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const {randomUUID}=require('node:crypto');
const ts=require('./edw-web/node_modules/typescript');
const {expect}=require('@playwright/test');
const hooks={};const test=()=>{};
test.describe={configure:options=>{assert.equal(options.mode,'serial');assert.equal(options.retries,0)}};
for(const name of ['beforeAll','beforeEach','afterEach','afterAll'])test[name]=fn=>{hooks[name]=fn};
test.info=()=>({title:'isolated restoration test'});test.setTimeout=()=>{};
	const accessSpec=fs.readFileSync('tests/ux/access.spec.ts','utf8');
	const source=process.env.EID_TEST_TREAT_503_REJECTED?
	 accessSpec.replace('[401,403,409,422].includes(response.status())','[401,403,409,422,503].includes(response.status())'):
	 accessSpec;
	if(process.env.EID_TEST_TREAT_503_REJECTED)assert.notEqual(source,accessSpec,'The in-memory 503 mutation must apply');
	const compiled=ts.transpileModule(source,{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}
}).outputText;
const isolatedChildren={...require('node:child_process'),
 spawn:()=>{throw Error('Unexpected process launch in isolated TS helper regression')},
 spawnSync:()=>{throw Error('No service, audit or broker processes in offline tests')}};
const sandbox={module:{exports:{}},exports:{},process,console,performance,setTimeout,clearTimeout,structuredClone,URL,
 require:name=>name==='@playwright/test'?{test,expect}:name==='node:child_process'?isolatedChildren:require(name)};
vm.runInNewContext(compiled+`
module.exports={prepareRestore,nextBody,policy,processResult,workerAccess,auditEvidence,verifyDelegationEvidence,restore:()=>restoreAfterTest(),
authenticate:callback=>{login=callback},
lock:()=>lockProcess,lockFailure:()=>lockFailure,loseLock:()=>{lockFailure='Fixture lock lost during await'},
configure:directory=>{stateDirectory=directory;ownerNonce='owner';workspaceA='owned-workspace';
fixtures={users:{author:{actor_id:'owned-author'}}};lockFailure=undefined;lockReleasing=false;
lockProcess={exitCode:null,signalCode:null,killed:false,stdin:{destroyed:false,writableEnded:false}}}};`,sandbox);
const helpers=sandbox.module.exports;
const original={active:true,roles:['author'],project_scope:['fixture-a','fixture-b'],
 customer_scope:['fixture-customer'],product_scope:['fixture-product'],department_scope:['test'],
 owner_scope:'self',approval_states:['draft'],clearance:1,valid_from:'2026-09-01T00:00:00.123456+00:00',
 valid_until:null,expected_epoch:[20,4,20]};
const memberPath='/api/v1/access/workspaces/owned-workspace/members/owned-author';
const defer=()=>{let resolve;const promise=new Promise(accept=>{resolve=accept});return {promise,resolve}};
const plain=value=>JSON.parse(JSON.stringify(value));
const marker=directory=>path.join(directory,'access-ux-recovery-required.json');
const restorationBrowser=(page,{request=page.request,authenticate=async()=>{},onClose=()=>{}}={})=>{
 const state={created:0,closed:0,logins:0};const freshPage={request};
 const context={newPage:async()=>freshPage,close:async()=>{state.closed++;onClose()}};
 page.url=()=> 'http://localhost:18080/admin/members';
 page.context=()=>({browser:()=>({newContext:async options=>{
  assert.deepEqual(plain(options),{baseURL:'http://localhost:18080',storageState:{cookies:[],origins:[]}});
  state.created++;return context;
 }})});
 // Replace only the browser login in this isolated VM; execute the actual context provider.
 helpers.authenticate(async(receivedPage,role,destination)=>{
  assert.equal(receivedPage,freshPage);assert.notEqual(receivedPage,page);
  assert.equal(role,'system_admin');assert.equal(destination,'/workspaces/owned-workspace/home');
  state.logins++;await authenticate();return 'Bearer fresh-administrator-never-persist';
 });
 return state;
};
"""


def run_ux_helpers(source, tmp_path, timeout=40, treat_503_as_rejected=False, require_success=True):
    node = shutil.which("node")
    assert node, "Node is required for the focused UX restoration safety check"
    environment = os.environ.copy()
    if treat_503_as_rejected:
        environment["EID_TEST_TREAT_503_REJECTED"] = "1"
    result = subprocess.run([node, "-e", UX_HELPER_HARNESS + source, str(tmp_path), sys.executable],
                            capture_output=True, text=True, timeout=timeout, cwd=verifier.ROOT,
                            env=environment)
    if require_success:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_ux_restoration_checks_complete_policy_and_epoch_before_any_overwrite(tmp_path):
    """Execute actual TS helpers/routes against memory replies; never a browser or API."""
    source = r"""
(async()=>{
	const scenarios=['restored-api','restored-ui','unchanged','rejected-api','rejected-ui',
	 'foreign-same-value-api','foreign-same-value-ui','pending-api','pending-ui',
	 'unknown-api','unknown-ui','http503-api','http503-ui','second-write-rejected','concurrent-policy','concurrent-epoch',
 'restore-conflict','incomplete-restore','microsecond-drift','wrong-request-id','wrong-audit','wrong-epoch',
 'lock-during-get','lock-during-unchanged-get','lock-during-postread','late-ui','late-api'];
for(const scenario of scenarios){
 const directory=path.join(process.argv[1],scenario);fs.mkdirSync(directory);helpers.configure(directory);
	 let current=structuredClone(original),puts=0,gets=0,closed=0,uiHandler,aborted=0,lateCommit;
 const sent=defer(),release=defer();
 const send=async(url,{data,headers})=>{
   puts++;assert.equal(url,'/api/v1/access/workspaces/owned-workspace/members/owned-author');
   const requestId=headers['X-Request-ID']||headers['x-request-id'];assert.ok(requestId);
   let status=200;
   if(puts===1&&scenario.startsWith('foreign-same-value'))current=plain(helpers.nextBody(original,{active:false}));
	   if((puts===1&&scenario.startsWith('rejected'))||
	    (puts===2&&['restore-conflict','second-write-rejected'].includes(scenario))||
	    JSON.stringify(data.expected_epoch)!==JSON.stringify(current.expected_epoch))status=409;
	   if(puts===1&&scenario.startsWith('http503')){
	    status=503;lateCommit=()=>{current=plain(helpers.nextBody(data,{}))};
	   }
   if(puts===1&&scenario.startsWith('pending')){sent.resolve();await release.promise}
   if(status===200){
    current=plain(helpers.nextBody(data,{}));
    if(puts===2&&scenario==='incomplete-restore')current.customer_scope=['unexpected'];
   }
   if(puts===1&&scenario.startsWith('unknown'))throw Error('Response lost after server commit');
   return {status:()=>status,headers:()=>({
    'x-request-id':scenario==='wrong-request-id'?randomUUID():requestId,
    traceparent:'00-'+'a'.repeat(32)+'-'+'b'.repeat(16)+'-01'}),
    json:async()=>({data:{audit_id:scenario==='wrong-audit'?'invalid':randomUUID(),
     workspace_epoch:current.expected_epoch[0]+(scenario==='wrong-epoch'?1:0)}})};
 };
 const page={route:async(pattern,handler)=>{assert.equal(pattern,'**'+memberPath);uiHandler=handler},request:{
  get:async()=>{
   gets++;
   if(['lock-during-get','lock-during-unchanged-get'].includes(scenario)||
     (scenario==='lock-during-postread'&&gets===2)){
    // Lose the process while memberBody awaits the response, not before restoration starts.
    await Promise.resolve();helpers.loseLock();
   }
   return {status:()=>200,json:async()=>({data:{members:[{...helpers.policy(current),identity_id:'owned-author'}],policy_epoch:current.expected_epoch}})};
  },put:send
 }};
 const browserState=restorationBrowser(page);
 const mutation=await helpers.prepareRestore(page,'secret-bearer-never-persist',structuredClone(original),'owned-workspace',async()=>{closed++});
 const ui=async(body)=>{
  const headers={'x-request-id':randomUUID()};
  await uiHandler({request:()=>({method:()=>'PUT',postDataJSON:()=>body,headers:()=>headers}),
   fetch:async options=>{assert.equal(options.timeout,10000);assert.equal(options.maxRetries,0);assert.equal(options.maxRedirects,0);return send(memberPath,{data:body,headers})},
   fulfill:async()=>{},abort:async()=>{aborted++},fallback:async()=>assert.fail('Unexpected fallback')});
 };
 const unchanged=['unchanged','lock-during-unchanged-get','late-ui','late-api'].includes(scenario);
 let pending;
	 if(!unchanged){
	  const operation=scenario.endsWith('-ui')?ui({...original,active:false}):mutation.put({...original,active:false});
	  if(scenario.startsWith('pending')){pending=operation;await sent.promise}
	  else if(['unknown-api','wrong-request-id','wrong-audit','wrong-epoch'].includes(scenario))await assert.rejects(operation);
	  else{
	   const response=await operation;
	   if(scenario==='http503-api')assert.equal(response.status(),503);
	  }
	 }
	 if(scenario.startsWith('http503'))assert.deepEqual(plain(current),plain(original),
	  'The original state is still visible before an unknown 503 outcome is recovered');
 const before=fs.readFileSync(marker(directory),'utf8');assert.ok(!before.includes('secret-bearer'));
 assert.equal(JSON.parse(before).original.valid_from,original.valid_from);
 if(scenario==='second-write-rejected')await mutation.put({...current,roles:['expert']});
 if(scenario==='concurrent-policy')current.customer_scope=['another-operator'];
 if(scenario==='concurrent-epoch')current.expected_epoch=[22,4,22];
 if(scenario==='microsecond-drift')current.valid_from='2026-09-01T00:00:00.123457+00:00';
	 const failed=!['restored-api','restored-ui','unchanged','rejected-api','rejected-ui','second-write-rejected','late-ui','late-api'].includes(scenario);
 const beforeRestore=puts;
 if(failed){
  await assert.rejects(helpers.restore());assert.ok(fs.existsSync(marker(directory)));
	  assert.equal(JSON.parse(fs.readFileSync(marker(directory),'utf8')).status,'recovery-required');
	  assert.equal(puts,beforeRestore+(['restore-conflict','incomplete-restore','lock-during-postread'].includes(scenario)?1:0));
	  assert.throws(hooks.beforeEach); // A restarted/shared-fixture test cannot continue.
	  if(scenario.startsWith('http503')){
	   assert.equal(puts,beforeRestore,'An unknown HTTP response must not trigger a restoration request');
	   lateCommit();
	   assert.equal(current.active,false,'The failed 503 response may still commit after recovery has failed');
	   assert.equal(JSON.parse(fs.readFileSync(marker(directory),'utf8')).status,'recovery-required');
	   assert.throws(hooks.beforeEach,'Late commit must remain blocked by recovery evidence');
	  }
  if(pending){
   assert.equal(gets,0,'An unresolved write must not be declared unchanged by an original read');
   assert.equal(current.active,true);release.resolve();await pending;
   assert.equal(current.active,false,'The held request really commits after restoration failed');
   assert.ok(fs.existsSync(marker(directory)),'Late completion cannot archive recovery evidence');
  }
 }else{
  await helpers.restore();assert.equal(fs.existsSync(marker(directory)),false);hooks.beforeEach();
  assert.equal(fs.readdirSync(path.join(directory,'access-ux-recovery')).length,1);
  assert.equal(current.valid_from,original.valid_from);
  if(scenario==='late-ui'){await ui({...original,active:false});assert.equal(aborted,1);assert.equal(puts,0)}
  if(scenario==='late-api'){await assert.rejects(mutation.put({...original,active:false}));assert.equal(puts,0)}
 }
 assert.equal(closed,1);
 assert.equal(browserState.closed,browserState.created,'Fresh restoration contexts must always close');
 const stored=fs.existsSync(marker(directory))?fs.readFileSync(marker(directory),'utf8'):
  fs.readFileSync(path.join(directory,'access-ux-recovery',fs.readdirSync(path.join(directory,'access-ux-recovery'))[0]),'utf8');
 assert.ok(!stored.includes('secret-bearer'));
 assert.ok(!stored.includes('fresh-administrator'));
 for(const write of JSON.parse(stored).writes){
  assert.match(write.request_id,/^[0-9a-f-]{36}$/);
  assert.equal(write.submitted.valid_from,original.valid_from);
  if(write.status==='committed'){assert.match(write.audit_id,/^[0-9a-f-]{36}$/);assert.match(write.trace_id,/^[0-9a-f]{32}$/)}
 }
}
console.log(scenarios.length+' restoration scenarios passed; no real API requests');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = run_ux_helpers(source, tmp_path)
    assert "27 restoration scenarios passed" in result.stdout
    mutation_directory = tmp_path / "503-known-rejected-mutant"
    mutation_directory.mkdir()
    mutated = run_ux_helpers(source, mutation_directory, treat_503_as_rejected=True, require_success=False)
    assert mutated.returncode != 0
    assert "Missing expected rejection" in mutated.stderr


def test_ux_restoration_reauthenticates_without_reusing_an_expired_admin_token(tmp_path):
    source = r"""
(async()=>{
for(const scenario of ['expired-original','login-failed','lock-during-login']){
 const directory=path.join(process.argv[1],scenario);fs.mkdirSync(directory);helpers.configure(directory);
 let current=structuredClone(original),oldExpired=false,puts=0,gets=0,staleAttempts=0,closed=0;
 const oldBearer='Bearer expired-original-never-persist',freshBearer='Bearer fresh-administrator-never-persist';
 const authorize=headers=>{
  if(headers.Authorization===oldBearer){if(oldExpired){staleAttempts++;return false}return true}
  assert.equal(headers.Authorization,freshBearer);return true;
 };
 const request={
  get:async(_,options)=>{
   gets++;const authorized=authorize(options.headers);
   return {status:()=>authorized?200:401,json:async()=>({data:{members:[{...helpers.policy(current),identity_id:'owned-author'}],policy_epoch:current.expected_epoch}})};
  },
  put:async(url,{data,headers})=>{
   assert.equal(url,memberPath);puts++;
   const authorized=authorize(headers);if(authorized)current=plain(helpers.nextBody(data,{}));
   return {status:()=>authorized?200:401,headers:()=>({'x-request-id':headers['X-Request-ID'],
    traceparent:'00-'+'a'.repeat(32)+'-'+'b'.repeat(16)+'-01'}),
    json:async()=>({data:{audit_id:randomUUID(),workspace_epoch:current.expected_epoch[0]}})};
  }
 };
 const page={route:async()=>{},request};
 const browserState=restorationBrowser(page,{authenticate:async()=>{
  await Promise.resolve();assert.equal(oldExpired,true,'Fresh authentication must happen at restoration time');
  if(scenario==='login-failed')throw Error('Administrator login unavailable');
  if(scenario==='lock-during-login')helpers.loseLock();
 }});
 const mutation=await helpers.prepareRestore(page,oldBearer,original,'owned-workspace',async()=>{closed++});
 assert.equal((await mutation.put({...original,active:false})).status(),200);oldExpired=true;
 // The same server stub explicitly rejects the expired original credential.
 assert.equal((await request.get('',{headers:{Authorization:oldBearer}})).status(),401);
 const previousGets=gets,previousStaleAttempts=staleAttempts;
 if(scenario==='expired-original'){
  await helpers.restore();assert.equal(puts,2);assert.equal(gets-previousGets,2);
  assert.equal(current.active,true);assert.equal(fs.existsSync(marker(directory)),false);hooks.beforeEach();
  const archives=fs.readdirSync(path.join(directory,'access-ux-recovery'));assert.equal(archives.length,1);
  const stored=fs.readFileSync(path.join(directory,'access-ux-recovery',archives[0]),'utf8');
  assert.ok(!stored.includes(oldBearer));assert.ok(!stored.includes(freshBearer));
 }else{
  await assert.rejects(helpers.restore(),scenario==='login-failed'?/login unavailable/:/Fixture lock/);
  assert.equal(puts,1,'No restoration PUT after failed login or lost lock');assert.equal(gets,previousGets);
  assert.equal(current.active,false);assert.ok(fs.existsSync(marker(directory)));assert.throws(hooks.beforeEach);
  const stored=fs.readFileSync(marker(directory),'utf8');assert.equal(JSON.parse(stored).status,'recovery-required');
  assert.ok(!stored.includes(oldBearer));assert.ok(!stored.includes(freshBearer));
 }
 assert.equal(staleAttempts,previousStaleAttempts,'Restoration must never attempt the original bearer');
 assert.deepEqual(browserState,{created:1,closed:1,logins:1});assert.equal(closed,1);
}
console.log('Fresh isolated administrator recovery passed; expired credentials never reused');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    assert "Fresh isolated administrator recovery passed" in run_ux_helpers(source, tmp_path).stdout


def test_ux_worker_deadline_uses_exact_database_clock_evidence_not_command_finish(tmp_path):
    source = r"""
(async()=>{
const {EventEmitter}=require('node:events');const {PassThrough}=require('node:stream');
const id='d877bbad-044b-4b5f-840a-77b10e378a32',expires='2026-09-17T12:05:00.123456Z';
const valid={reply:{status:'denied'},delegation_id:id,operation:'resource:read',purpose:'stage-check',
 broadcast_started_at:'2026-09-17T12:04:59.123456+00:00',
 broadcast_finished_at:'2026-09-17T12:05:00.123455+00:00',expires_at:'2026-09-17T12:05:00.123456+00:00'};
let current=valid,calls=0;
isolatedChildren.spawn=(command,args,options)=>{
 calls++;assert.deepEqual([...args],['-m','scripts.verify_access_delegation',id,'resource:read','stage-check','--evidence']);
 assert.equal(options.windowsHide,true);assert.equal(options.stdio,'pipe');
 const child=Object.assign(new EventEmitter(),{stdin:new PassThrough(),stdout:new PassThrough(),stderr:new PassThrough()});
 queueMicrotask(()=>{child.stdout.end(JSON.stringify(current));child.stderr.end();child.emit('close',0,null)});
 return child;
};
sandbox.setTimeout=(callback,delay)=>{assert.equal(delay,180000,'Do not increase the bounded guard budget');return setTimeout(callback,delay)};
// Command return is deliberately after the five-minute deadline: the postguard took time.
sandbox.performance={now:()=>350000};
sandbox.Date=class extends Date{static now(){return Date.parse('2026-09-17T12:05:50.123456Z')}};
assert.ok(sandbox.Date.now()>Date.parse(expires));assert.ok(sandbox.performance.now()>300000);
assert.deepEqual(plain(await helpers.workerAccess(id,expires)),valid);
current={...valid,reply:{status:'allowed',context:{actor_id:'owned-author'}}};
assert.equal((await helpers.workerAccess(id,expires)).reply.status,'allowed');
for(const change of [
 {broadcast_finished_at:expires},
 {broadcast_finished_at:'2026-09-17T12:05:00.123457Z'},
 {broadcast_started_at:'2026-09-17T12:05:00.123456Z'},
 {expires_at:'2026-09-17T12:05:00.123457Z'},
 {expires_at:'2026-09-17T12:05:00.123455Z'},
 {delegation_id:randomUUID()}, {delegation_id:'not-a-uuid'},
 {operation:'document:edit'}, {purpose:'other'},
 {broadcast_started_at:'2026-09-17T12:04:59'},
 {broadcast_finished_at:'2026-09-17T12:05:00.1234557Z'},
 {broadcast_finished_at:'2026-02-30T12:05:00Z'},
 {broadcast_finished_at:'invalid'},
]){
 current={...valid,...change};await assert.rejects(helpers.workerAccess(id,expires));
}
assert.throws(()=>helpers.verifyDelegationEvidence({...valid,delegation_id:'invalid'},'invalid',expires));
assert.equal(calls,15);
console.log('Postguard delay accepted; expired or mismatched actual broadcast evidence rejected');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    assert "Postguard delay accepted" in run_ux_helpers(source, tmp_path).stdout


def test_ux_async_probe_is_bounded_and_reaps_failed_temp_children(tmp_path):
    """Launch only local Node snippets, never the requested Python guard or live services."""
    source = r"""
(async()=>{
 const native=require('node:child_process');
 const cases=[
  ['valid',`let input='';process.stdin.on('data',chunk=>input+=chunk);
    process.stdin.on('end',()=>setTimeout(()=>process.stdout.write(JSON.stringify({received:JSON.parse(input)})),100));`],
  ['invalid-json',`process.stdout.write('{invalid');`],
  ['nonzero',`process.stderr.write('controlled failure');process.stdout.write('{}');process.exitCode=9;`],
  ['signal',`setInterval(()=>{},1000);`],
  ['timeout',`setInterval(()=>{},1000);`],
  ['stdout-cap',`process.stdout.write('x'.repeat(65537));setInterval(()=>{},1000);`],
  ['stderr-cap',`process.stderr.write('x'.repeat(65537));setInterval(()=>{},1000);`],
  ['combined-cap',`process.stdout.write('x'.repeat(40000));process.stderr.write('x'.repeat(30000));setInterval(()=>{},1000);`],
  ['utf8-cap',`process.stdout.write('界'.repeat(22000));setInterval(()=>{},1000);`],
  ['spawn-error',''],['spawn-throw','']
 ];
 const errors={'invalid-json':/invalid JSON/,nonzero:/status=9/,signal:/signal=SIGTERM/,
  timeout:/timed out after 180000 ms/,'spawn-error':/process error/,'spawn-throw':/controlled spawn failure/};
 for(const [scenario,code] of cases){
  let child,ticks=0,closed=false;const ticker=setInterval(()=>ticks++,10);
  sandbox.setTimeout=(callback,delay)=>{
   assert.equal(delay,180000,'The production timeout must stay at 180 seconds');
   return setTimeout(callback,scenario==='timeout'?150:10000);
  };
  isolatedChildren.spawn=(command,args,options)=>{
   assert.equal(command,path.resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python'));
   assert.deepEqual([...args],['isolated-probe']);assert.equal(options.stdio,'pipe');assert.equal(options.windowsHide,true);
   if(scenario==='spawn-throw')throw Error('controlled spawn failure');
   child=scenario==='spawn-error'?native.spawn(path.join(process.argv[1],'missing-probe'),[],options):
    native.spawn(process.execPath,['-e',code],options);
   child.once('close',()=>{closed=true});
   if(scenario==='signal')setTimeout(()=>child.kill('SIGTERM'),100);
   return child;
  };
  try{
   const result=helpers.processResult(['isolated-probe'],JSON.stringify({id:'temp-only'}));
   assert.equal(typeof result.then,'function');
   if(scenario==='valid'){
    assert.deepEqual(plain(await result),{received:{id:'temp-only'}});
    assert.ok(ticks>=2,'The event loop must keep running while the child works');
   }else await assert.rejects(result,errors[scenario]||/output exceeded 65536 bytes/);
   if(child){
    assert.equal(closed,true,'The helper must wait for child close, including on failure');
    assert.ok(child.exitCode!==null||child.signalCode!==null);
    assert.ok(child.stdin.destroyed&&child.stdout.destroyed&&child.stderr.destroyed);
    if(scenario==='timeout'||scenario.endsWith('-cap'))assert.equal(child.killed,true);
   }
  }finally{
   clearInterval(ticker);
   if(child&&child.exitCode===null&&child.signalCode===null){
    const closed=new Promise(resolve=>child.once('close',resolve));child.kill('SIGKILL');await closed;
   }
  }
 }
 console.log('11 async subprocess scenarios passed; temp-only children closed');
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    assert "11 async subprocess scenarios passed" in run_ux_helpers(source, tmp_path).stdout


def test_registered_ux_hooks_reject_real_lock_child_loss_after_preflight_ready(tmp_path):
    """Run registered beforeAll/Each/afterEach with a real temp-only lock child."""
    source = r"""
(async()=>{
 const native=require('node:child_process');const {once}=require('node:events');
 let child,puts=0,gets=0,uiHandler;
 const childSource=`import sys,json
from pathlib import Path
from scripts import verify_access_fixtures as module
state=Path(sys.argv[1])
module.environment_state_directory=lambda _:state
module.preflight=lambda _: {'fixtures': {'workspaces':['owned-workspace','second-workspace'], 'users':{'author':{'actor_id':'owned-author'}}}, 'state_directory':str(state), 'nonce':'owner'}
sys.argv=['verify_access_fixtures','--hold-lock']
module.main()
`;
 isolatedChildren.spawn=(command,args,options)=>{
  assert.deepEqual([...args],['-m','scripts.verify_access_fixtures','--hold-lock']);
  assert.equal(child,undefined,'Only the explicitly isolated child may start');
  child=native.spawn(process.argv[2],['-c',childSource,process.argv[1]],{...options,windowsHide:true});return child;
 };
 try{
  // This executes the real readiness parser and lifetime error/exit subscriptions.
  await hooks.beforeAll();hooks.beforeEach();
  assert.equal(helpers.lock(),child);assert.equal(helpers.lockFailure(),undefined);
  const page={route:async(_,handler)=>{uiHandler=handler},request:{
   put:async()=>{puts++;assert.fail('No API write may follow lock loss')},
   get:async()=>{gets++;assert.fail('Restoration must reject before reading after known lock loss')}
  }};
  const mutation=await helpers.prepareRestore(page,'secret-bearer-never-persist',original);
  const exited=once(child,'exit');child.kill();await exited;
  // Explicitly covers the consumer exit callback: removing it must fail this assertion,
  // even though exitCode/signalCode checks independently provide another fail-closed guard.
  assert.match(helpers.lockFailure(),/Fixture lock exited/);
  assert.throws(hooks.beforeEach,/Fixture lock/);
  await assert.rejects(mutation.put({...original,active:false}),/Fixture lock/);
  let aborted=0;
  await uiHandler({request:()=>({method:()=>'PUT'}),fetch:async()=>{puts++;assert.fail('No UI API write')},
   abort:async()=>{aborted++}});
  assert.equal(aborted,1);
  await assert.rejects(hooks.afterEach(),/Fixture lock/);
  await assert.rejects(hooks.afterAll());
  assert.equal(puts,0);assert.equal(gets,0);assert.ok(fs.existsSync(marker(process.argv[1])));
  const evidence=fs.readFileSync(marker(process.argv[1]),'utf8');
  assert.equal(JSON.parse(evidence).status,'recovery-required');assert.ok(!evidence.includes('secret-bearer'));
  assert.equal(fs.existsSync(path.join(process.argv[1],'access-ux-recovery')),false);
  console.log('Real registered hooks rejected lost temp child; no API or browser calls');
 }finally{
  if(child&&child.exitCode===null&&child.signalCode===null){const exited=once(child,'exit');child.kill();await exited}
 }
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    assert "Real registered hooks rejected lost temp child" in run_ux_helpers(source, tmp_path).stdout
