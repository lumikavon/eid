import {test,expect,Page,APIResponse} from '@playwright/test';
import {closeSync,existsSync,fsyncSync,mkdirSync,openSync,renameSync,writeFileSync} from 'node:fs';
import {spawn,ChildProcessWithoutNullStreams} from 'node:child_process';
import {Buffer} from 'node:buffer';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import type {Member} from '../../edw-web/src/app/access-api';

type Fixtures={
 workspaces:string[];users:Record<string,{username:string;subject:string;actor_id:string;resource_id:string}>;
};
type MemberBody=Omit<Member,'identity_id'|'display_name'>&{expected_epoch:number[]};
const python=resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const guardTimeout=180000;
let fixtures:Fixtures,workspaceA:string,workspaceB:string,defaultWorkspace:string,remainingWorkspace:string;
let stateDirectory:string,ownerNonce:string,lockProcess:ChildProcessWithoutNullStreams|undefined;
let lockFailure:string|undefined,lockReleasing=false;
let restoreAfterTest:(()=>Promise<void>)|undefined;
// One serial group also skips the rest after any failure; retries must not hide fixture damage.
test.describe.configure({mode:'serial',retries:0});
test.beforeAll(async()=>{
 test.setTimeout(guardTimeout+15000);
 const child=spawn(python,['-m','scripts.verify_access_fixtures','--hold-lock'],{stdio:'pipe'});
 lockProcess=child;
 let stderr='';child.stderr.setEncoding('utf8');child.stderr.on('data',value=>{stderr=(stderr+value).slice(-8000)});
 const result=await new Promise<{fixtures:Fixtures;state_directory:string;nonce:string}>((accept,reject)=>{
  let stdout='';let ready=false;
  const timer=setTimeout(()=>{child.kill();reject(new Error(`Fixture preflight timed out after ${guardTimeout} ms; ${stderr}`))},guardTimeout);
  child.once('error',error=>{clearTimeout(timer);lockFailure=`Fixture lock process error: ${error.message}`;reject(error)});
  child.once('exit',(code,signal)=>{
   if(!lockReleasing)lockFailure=`Fixture lock exited: status=${code}, signal=${signal}; ${stderr}`;
   if(!ready){clearTimeout(timer);reject(new Error(lockFailure||'Fixture lock exited before preflight'))}
  });
  child.stdout.setEncoding('utf8');child.stdout.on('data',value=>{
   if(ready)return;stdout+=value;
   if(stdout.length>65536){clearTimeout(timer);child.kill();reject(new Error('Oversized fixture preflight response'));return}
   if(!stdout.includes('\n'))return;
   clearTimeout(timer);
   try{const parsed=JSON.parse(stdout.slice(0,stdout.indexOf('\n')));ready=true;accept(parsed)}catch(error){child.kill();reject(error)}
  });
 });
 fixtures=result.fixtures;stateDirectory=result.state_directory;ownerNonce=result.nonce;
 [workspaceA,workspaceB]=fixtures.workspaces;
 [defaultWorkspace,remainingWorkspace]=[...fixtures.workspaces].sort();
});
test.beforeEach(()=>{
 requireFixtureLock();
 expect(existsSync(recoveryPath()),'Unresolved fixture restoration blocks further tests').toBe(false);
});
test.afterEach(async()=>{const restore=restoreAfterTest;restoreAfterTest=undefined;await restore?.()});
test.afterAll(async()=>{
 if(!lockProcess)return;
 const child=lockProcess;lockReleasing=true;
 if(child.exitCode===null&&child.signalCode===null){
  await new Promise<void>((accept,reject)=>{
   const timer=setTimeout(()=>{child.kill();reject(new Error('Fixture lock did not release within 5 seconds'))},5000);
   child.once('exit',(code,signal)=>{clearTimeout(timer);if(code===0)accept();else reject(new Error(`Fixture lock release failed: status=${code}, signal=${signal}`))});
   child.stdin.end();
  });
 }
 expect(lockFailure).toBeUndefined();
});
function recoveryPath(){return resolve(stateDirectory,'access-ux-recovery-required.json')}
function requireFixtureLock(){
 expect(lockFailure,'Fixture lock must remain held for every shared-fixture operation').toBeUndefined();
 expect(lockReleasing,'Fixture lock release must not have started').toBe(false);
 expect(lockProcess?.exitCode,'Fixture lock process must still be running').toBeNull();
 expect(lockProcess?.signalCode,'Fixture lock process must not have been signalled').toBeNull();
 expect(lockProcess?.killed,'Fixture lock process must not have been killed').toBe(false);
 expect(lockProcess?.stdin.destroyed,'Fixture lock lifetime pipe must remain open').toBe(false);
 expect(lockProcess?.stdin.writableEnded,'Fixture lock lifetime pipe must not be ending').toBe(false);
}
function durableRecord(path:string,value:object){
 const handle=openSync(path,'wx',0o600);
 try{writeFileSync(handle,JSON.stringify(value,null,2)+'\n');fsyncSync(handle)}finally{closeSync(handle)}
}
function workspaceName(id:string){return `本地权限验收项目 ${id===workspaceA?'A':'B'}`}
function processResult(args:string[],input?:string){
 // Playwright route callbacks share this event loop; a synchronous guard stalls even
 // unrelated browser requests and can make a healthy account poll time out.
 return new Promise<ReturnType<typeof JSON.parse>>((accept,reject)=>{
  const child=spawn(python,args,{stdio:'pipe',windowsHide:true});
  let stdout='',stderr='',outputBytes=0,failure:Error|undefined;
  const stop=(error:Error)=>{
   failure??=error;
   try{if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL')}
   catch{clearTimeout(timer);reject(new Error(`${failure.message}; failed to terminate probe child`))}
   finally{child.stdin.destroy();child.stdout.destroy();child.stderr.destroy()}
  };
  const timer=setTimeout(()=>stop(new Error(`Probe timed out after ${guardTimeout} ms`)),guardTimeout);
  child.once('error',error=>stop(new Error(`Probe process error: ${error.message}`)));
  for(const [stream,name] of [[child.stdout,'stdout'],[child.stderr,'stderr']] as const){
   stream.setEncoding('utf8');
   stream.on('error',()=>stop(new Error(`Probe ${name} stream failed`)));
   stream.on('data',(value:string)=>{
    if(failure)return;
    outputBytes+=Buffer.byteLength(value,'utf8');
    if(outputBytes>65536){stop(new Error('Probe output exceeded 65536 bytes'));return}
    if(name==='stdout')stdout+=value;else stderr=(stderr+value).slice(-8000);
   });
  }
  child.stdin.on('error',()=>stop(new Error('Probe stdin stream failed')));
  child.once('close',(code,signal)=>{
   clearTimeout(timer);
   if(failure){reject(failure);return}
   if(code!==0||signal!==null){reject(new Error(`Probe failed: status=${code}, signal=${signal}; ${stderr}`));return}
   try{accept(JSON.parse(stdout))}catch{reject(new Error('Probe returned invalid JSON'))}
  });
  child.stdin.end(input??'');
 });
}
type WorkerEvidence={reply:{status:string;context?:Record<string,string>};delegation_id:string;operation:string;purpose:string;
 broadcast_started_at:string;broadcast_finished_at:string;expires_at:string};
function utcMicroseconds(value:unknown){
 expect(typeof value,'Delegation evidence must contain a UTC datetime').toBe('string');
 const match=/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,6}))?(?:Z|\+00:00)$/.exec(value as string);
 expect(match,'Delegation timestamps must preserve UTC microsecond precision').toBeTruthy();
 const milliseconds=Date.parse(`${match![1]}Z`);
 expect(Number.isFinite(milliseconds),'Delegation timestamp must be a valid datetime').toBe(true);
 expect(new Date(milliseconds).toISOString().slice(0,19),'Delegation timestamp must not normalize an invalid date').toBe(match![1]);
 return BigInt(milliseconds)*1000n+BigInt((match![2]||'').padEnd(6,'0'));
}
function verifyDelegationEvidence(evidence:WorkerEvidence,id:string,expiresAt:string){
 expect(id,'The original delegation ID must be a UUID').toMatch(/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
 expect(evidence.delegation_id,'Probe evidence must belong to the original delegation').toBe(id);
 expect(evidence.operation).toBe('resource:read');expect(evidence.purpose).toBe('stage-check');
 const expiry=utcMicroseconds(expiresAt);
 expect(utcMicroseconds(evidence.expires_at),'Probe expiry must exactly match the original delegation').toBe(expiry);
 const before=utcMicroseconds(evidence.broadcast_started_at),after=utcMicroseconds(evidence.broadcast_finished_at);
 expect(before,'The database clock must not move backwards during the broadcast').toBeLessThanOrEqual(after);
 expect(after,'The actual Worker reply must arrive before the original delegation expires').toBeLessThan(expiry);
}
async function workerAccess(id:string,expiresAt:string):Promise<WorkerEvidence>{
 const evidence=await processResult(['-m','scripts.verify_access_delegation',id,'resource:read','stage-check','--evidence']);
 verifyDelegationEvidence(evidence,id,expiresAt);return evidence;
}
function auditEvidence(id:string){
 const source=`import json,sys,psycopg
from uuid import UUID
from psycopg.rows import dict_row
from scripts.verify_local_environment import development_database_url, verify_migration_target
identifier=UUID(json.load(sys.stdin)['id'])
url=development_database_url()
verify_migration_target(url)
with psycopg.connect(url.replace('postgresql+psycopg:','postgresql:'),row_factory=dict_row,connect_timeout=3,options='-c statement_timeout=2000 -c default_transaction_read_only=on') as conn:
    assert conn.execute('SELECT current_database() AS db,current_user AS role').fetchone()=={'db':'eid_local_dev','role':'eid_migrator'}
    row=conn.execute('SELECT workspace_id::text,actor_id::text,target_id::text,action,after_policy,request_id,trace_id FROM access_audit WHERE id=%s',(identifier,)).fetchone()
    assert row is not None
    print(json.dumps(row))
`;
 return processResult(['-c',source],JSON.stringify({id}));
}
async function login(page:Page,role:string,path=`/workspaces/${workspaceA}/home`){
 await page.goto(path);
 await page.getByRole('button',{name:'登录工作区',exact:true}).click();
 await page.locator('#username').fill(fixtures.users[role].username);
 await page.locator('#password').fill('eid-local-access');
 const me=page.waitForRequest(r=>r.url().endsWith('/api/v1/me'));
 await page.locator('#kc-login').click();
 const request=await me;
 await expect(page.getByTestId('auth-status')).toHaveText(path==='/'?'已安全登录':/已安全登录|工作区访问被拒绝/);
 return request.headers().authorization;
}
async function openAccount(page:Page,workspace:string){
 await page.getByRole('button',{name:'账户与会话',exact:true}).click();
 await expect(page).toHaveURL(`/workspaces/${workspace}/account`);
 await expect(page.getByLabel('选择工作区')).toBeVisible();
 await expect(page.getByLabel('选择工作区')).toBeEnabled();
}
async function freshRestorationSession(page:Page,workspace:string){
 requireFixtureLock();
 const browser=page.context().browser();expect(browser,'Fixture restoration requires an independent browser context').toBeTruthy();
 const context=await browser!.newContext({baseURL:new URL(page.url()).origin,storageState:{cookies:[],origins:[]}});
 try{
  requireFixtureLock();const freshPage=await context.newPage();requireFixtureLock();
  const bearer=await login(freshPage,'system_admin',`/workspaces/${workspace}/home`);
  requireFixtureLock();expect(bearer,'Restoration requires a newly authenticated administrator').toMatch(/^Bearer \S+$/);
  return {page:freshPage,bearer,close:()=>context.close()};
 }catch(error){await context.close();throw error}
}
async function memberBody(page:Page,bearer:string,workspace=workspaceA):Promise<MemberBody>{
 const response=await page.request.get(`/api/v1/access/workspaces/${workspace}/members`,{headers:{Authorization:bearer},timeout:10000});
 expect(response.status()).toBe(200);
 const data=(await response.json()).data;
 const row=data.members.find((m:{identity_id:string})=>m.identity_id===fixtures.users.author.actor_id);
 expect(row,'The explicitly owned author membership must exist').toBeTruthy();
 return {...policy(row),expected_epoch:data.policy_epoch} as MemberBody;
}
const policyKeys=['active','roles','project_scope','customer_scope','product_scope','department_scope','owner_scope','approval_states','clearance','valid_from','valid_until'];
function policy(value:object){
 const record=value as Record<string,unknown>;
 return Object.fromEntries(policyKeys.map(key=>[key,record[key]]));
}
function comparablePolicy(value:object){
 const result=policy(value);
 for(const key of ['valid_from','valid_until']){
  if(result[key]===null)continue;
  const match=/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,6}))?(?:Z|\+00:00)$/.exec(String(result[key]));
  expect(match,'Fixture policy timestamps must preserve UTC microsecond precision').toBeTruthy();
  result[key]=`${match![1]}.${(match![2]||'').padEnd(6,'0')}Z`;
 }
 return result;
}
function nextBody(body:MemberBody,changes:Partial<MemberBody>):MemberBody{
 return {...body,...changes,expected_epoch:body.expected_epoch.map((value,index)=>value+(index===1?0:1))};
}
async function prepareRestore(page:Page,bearer:string,original:MemberBody,workspace=workspaceA,close?:()=>Promise<void>){
 requireFixtureLock();
 const id=randomUUID();const path=`/api/v1/access/workspaces/${workspace}/members/${fixtures.users.author.actor_id}`;
 type WriteEvidence={kind:'mutation'|'restoration';request_id:string;submitted:MemberBody;expected:MemberBody;
  status:'pending'|'committed'|'rejected'|'unknown';http_status?:number;audit_id?:string;trace_id?:string};
 const snapshot=(body:MemberBody)=>structuredClone({...policy(body),expected_epoch:body.expected_epoch}) as MemberBody;
 original=snapshot(original);
 const writes:WriteEvidence[]=[];const inFlight=new Set<Promise<APIResponse>>();let accepting=true;
 const evidence={schema:'eid-access-ux-recovery-v2',id,nonce:ownerNonce,workspace_id:workspace,
  identity_id:fixtures.users.author.actor_id,original,expected:original,writes,status:'prepared',test:test.info().title};
 const save=()=>{
  const temporary=resolve(stateDirectory,`access-ux-recovery-${id}-${randomUUID()}.tmp`);
  durableRecord(temporary,evidence);renameSync(temporary,recoveryPath());
 };
 // Persist only fixture policy fields; never persist bearer tokens, cookies or passwords.
 durableRecord(recoveryPath(),evidence);
 const dispatch=async(body:MemberBody,requestId:string,send:()=>Promise<APIResponse>,kind:WriteEvidence['kind'])=>{
  requireFixtureLock();
  expect(kind==='restoration'||accepting,'Restoration has fenced further fixture mutations').toBe(true);
  expect(requestId,'Fixture writes require a correlatable request ID').toMatch(/^[0-9a-f-]{36}$/);
  const submitted=snapshot(body);const entry:WriteEvidence={kind,request_id:requestId,submitted,
   expected:nextBody(submitted,{}),status:'pending'};
  writes.push(entry);evidence.expected=entry.expected;save();
  try{
   requireFixtureLock(); // No awaited read or UI route may separate this check from the actual PUT.
   const response=await send();entry.http_status=response.status();
   requireFixtureLock();
   const headers=response.headers();
   expect(headers['x-request-id'],'Only the response to our exact write proves ownership').toBe(requestId);
   const trace=/^00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$/.exec(headers.traceparent||'');
   expect(trace,'Fixture write response must retain its trace ID').toBeTruthy();entry.trace_id=trace![1];
   if(response.status()===200){
    const receipt=(await response.json()).data;
    requireFixtureLock();
    expect(receipt.audit_id,'A successful fixture write needs an audit receipt').toMatch(/^[0-9a-f-]{36}$/);
    entry.audit_id=receipt.audit_id;
    expect(receipt.workspace_epoch,'The receipt must identify the submitted epoch transition').toBe(entry.expected.expected_epoch[0]);
    entry.status='committed';
   }else entry.status=[401,403,409,422].includes(response.status())?'rejected':'unknown';
   save();return response;
  }catch(error){entry.status='unknown';save();throw error}
 };
 const track=(operation:Promise<APIResponse>)=>{
  inFlight.add(operation);const settled=()=>{inFlight.delete(operation)};
  void operation.then(settled,settled);return operation;
 };
 const settledWrites=()=>{
  expect(inFlight.size,'A pending fixture write may still commit; retain recovery evidence').toBe(0);
  expect(writes.some(write=>write.status==='pending'||write.status==='unknown'),
   'Unknown fixture write outcomes require manual recovery').toBe(false);
 };
 restoreAfterTest=async()=>{
  accepting=false; // Installed UI routes and the API wrapper also reject writes that arrive late.
  let session:Awaited<ReturnType<typeof freshRestorationSession>>|undefined;
  try{
   requireFixtureLock();settledWrites();
   session=await freshRestorationSession(page,workspace);
   requireFixtureLock();settledWrites();
   const {page:restorePage,bearer:freshBearer}=session;
   const latest=await memberBody(restorePage,freshBearer,workspace);
   requireFixtureLock();settledWrites();
   const canonical=(value:MemberBody)=>JSON.stringify({...comparablePolicy(value),expected_epoch:value.expected_epoch});
   const committed=writes.filter(write=>write.kind==='mutation'&&write.status==='committed');
   const owned=committed.length?committed[committed.length-1].expected:original;
   expect(canonical(latest),'Only a successfully committed own request permits restoration').toBe(canonical(owned));
   if(canonical(latest)!==canonical(original)){
    const requestId=randomUUID();const data={...original,expected_epoch:latest.expected_epoch};
    requireFixtureLock();
    const restored=await dispatch(data,requestId,()=>restorePage.request.put(path,{
     headers:{Authorization:freshBearer,'X-Request-ID':requestId},data,timeout:10000,maxRetries:0,maxRedirects:0}),'restoration');
    requireFixtureLock();
    expect(restored.status(),'Fixture policy restoration failed').toBe(200);
    const verified=await memberBody(restorePage,freshBearer,workspace);
    requireFixtureLock();settledWrites();
    expect(comparablePolicy(verified),'Every original policy field must be restored').toEqual(comparablePolicy(original));
    expect(verified.expected_epoch).toEqual(nextBody(latest,{}).expected_epoch);
    evidence.status=`restored:${writes[writes.length-1].audit_id}`;
   }else evidence.status='unchanged';
   requireFixtureLock();settledWrites();
   save();
   const archive=resolve(stateDirectory,'access-ux-recovery');mkdirSync(archive,{recursive:true});
   requireFixtureLock();settledWrites();
   renameSync(recoveryPath(),resolve(archive,`${id}.json`));
  }catch(error){evidence.status='recovery-required';save();throw error}
  finally{try{await session?.close()}finally{await close?.()}}
 };
 // The UI supplies its own request ID. Fetch here keeps the server operation tracked even
 // when navigation abandons the browser response. Test delay routes must use fallback().
 await page.route(`**${path}`,async route=>{
  if(route.request().method()!=='PUT')return route.fallback();
  try{
   requireFixtureLock();
   const response=await track(dispatch(route.request().postDataJSON(),route.request().headers()['x-request-id'],
    ()=>route.fetch({timeout:10000,maxRetries:0,maxRedirects:0}),'mutation'));
   await route.fulfill({response});
  }catch{
   // dispatch preserves any possibly submitted write. A request rejected by the lifetime
   // fence never reaches the API; do not throw an unhandled route callback rejection.
   await route.abort('failed').catch(()=>{});
  }
 });
 requireFixtureLock();
 return {put:(body:MemberBody)=>{
  const requestId=randomUUID();const data=snapshot(body);
  return track(dispatch(data,requestId,()=>page.request.put(path,{
   headers:{Authorization:bearer,'X-Request-ID':requestId},data,timeout:10000,maxRetries:0,maxRedirects:0}),'mutation'));
 }};
}
const operations:Record<string,string>={author:'document:edit',expert:'document:review',quality:'quality:review',template_admin:'template:publish',knowledge_admin:'knowledge:manage',approver:'document:approve',system_admin:'membership:manage'};

test('workspace pages render independently and retain a current project absent from the page',async({page})=>{
 await login(page,'author',`/workspaces/${remainingWorkspace}/home`);
 await page.getByRole('button',{name:'选择项目',exact:true}).click();
 await expect(page).toHaveURL(`/workspaces/${remainingWorkspace}/account`);
 await expect(page.getByLabel('选择工作区')).toBeEnabled();
 let reads=0;
 await page.route('**/api/v1/access/workspaces*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname!=='/api/v1/access/workspaces')return route.continue();
  reads++;const response=await route.fetch();const body=await response.json();
  if(!url.searchParams.has('after')){body.data.workspaces=body.data.workspaces.filter((p:{workspace_id:string})=>p.workspace_id===defaultWorkspace);body.data.next_cursor=defaultWorkspace}
  await route.fulfill({response,json:body});
 });
 await page.getByRole('button',{name:'刷新可访问项目'}).click();
 await expect(page.getByRole('button',{name:'下一页项目'})).toBeEnabled();
 await expect(page.getByRole('button',{name:'上一页项目'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'上一页项目'})).toHaveAccessibleDescription('第 1 页 · 已是首页');
 await expect(page.getByLabel('选择工作区')).toHaveValue(remainingWorkspace);
 await expect(page.locator('.project-card b')).toHaveText(workspaceName(remainingWorkspace));
 expect(reads).toBe(1);
 await page.getByRole('button',{name:'下一页项目'}).click();
 await expect(page.getByRole('button',{name:'下一页项目'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'下一页项目'})).toHaveAccessibleDescription('第 2 页 · 已是末页');
 await expect(page.getByRole('button',{name:'上一页项目'})).toBeEnabled();
 expect(reads).toBe(2);
 await page.getByRole('button',{name:'上一页项目'}).click();
 await expect(page.getByRole('button',{name:'下一页项目'})).toBeEnabled();
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
});

test('account navigation opens and closes member management without retaining an editor',async({page})=>{
 await login(page,'system_admin');
 await openAccount(page,workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await expect(page.getByRole('table',{name:'项目成员权限'})).toBeVisible();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 await expect(page.locator('.access-editor')).toBeVisible();
 await page.goBack();
 await expect(page).toHaveURL(`/workspaces/${workspaceA}/home`);
 await expect(page.locator('.access-admin')).toHaveCount(0);
 await expect(page.locator('.access-editor')).toHaveCount(0);
 await page.goForward();
 await expect(page).toHaveURL(`/workspaces/${workspaceA}/account`);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await expect(page.getByRole('table',{name:'项目成员权限'})).toBeVisible();
 await expect(page.locator('.access-editor')).toHaveCount(0);
});

test('invalid callback navigation with an existing session offers fresh authentication',async({page})=>{
 await login(page,'author');
 await page.evaluate(()=>{history.pushState({},'','/auth/callback?code=invalid&state=invalid');dispatchEvent(new PopStateEvent('popstate'))});
 await expect(page.getByTestId('auth-status')).toHaveText('认证失败');
 await expect(page.locator('.access-panel')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'重试账户加载'})).toHaveCount(0);
 await page.getByRole('button',{name:'登录工作区',exact:true}).click();
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page).toHaveURL(`/workspaces/${workspaceA}/home`);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
});

test('root project revocation discovers another real membership before the account poll',async({page,browser})=>{
 const bearer=await login(page,'system_admin');
 const original=await memberBody(page,bearer,defaultWorkspace);
 const context=await browser.newContext();const author=await context.newPage();
 const mutation=await prepareRestore(page,bearer,original,defaultWorkspace,()=>context.close());
 await author.addInitScript(()=>{
  const native=window.setInterval;
  window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args);
 });
 const revoked=await mutation.put({...original,active:false});
 expect(revoked.status()).toBe(200);
 await login(author,'author','/');
 await expect(author.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(author.locator('.project-card b')).toHaveText(workspaceName(remainingWorkspace));
 await expect(author).toHaveURL(`/workspaces/${remainingWorkspace}/home`);
});

test('development StrictMode consumes one callback and preserves the resource destination before polling',async({page})=>{
 const {createServer}=await import('../../edw-web/node_modules/vite/dist/node/index.js');
 const server=await createServer({root:resolve('edw-web'),logLevel:'silent',server:{host:'127.0.0.1',port:0}});
 await server.listen();
 try{
  const origin=server.resolvedUrls!.local[0];
  const destination=`/workspaces/${workspaceB}/resources/${fixtures.users.author.resource_id}`;
  const current={workspace_id:workspaceB,name:'StrictMode project',slug:'strictmode',actor_id:fixtures.users.author.actor_id,display_name:'StrictMode member',department:'Test',roles:['author'],clearance:1,policy_epoch:[1,1,1],operations:['workspace:read']};
  let exchanges=0;let readiness=0;let release=()=>{};const hold=new Promise<void>(resolve=>{release=resolve});
  await page.addInitScript(({destination})=>{
   sessionStorage.setItem('oidc.tx',JSON.stringify({state:'strictmode-state',verifier:'test-verifier',returnTo:destination}));
   const native=window.setInterval;window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args);
  },{destination});
  await page.route('**/realms/eid-local/protocol/openid-connect/token',async route=>{exchanges++;await hold;await route.fulfill({json:{access_token:'strictmode-test-only'}})});
  await page.route('**/health/ready',route=>{readiness++;return route.fulfill({json:{status:'ready'}})});
  await page.route('**/api/v1/**',route=>{
   const path=new URL(route.request().url()).pathname;
   const data=path.endsWith('/me')?{...current,subject:'test',workspace_name:current.name,workspace_slug:current.slug}:
    path.endsWith('/workspaces')?{workspaces:[current],next_cursor:null}:
    path.includes('/resources/')?{id:fixtures.users.author.resource_id,title:'StrictMode resource',kind:'test'}:current;
   return route.fulfill({json:{data}});
  });
  await page.goto(new URL('/auth/callback?code=test-code&state=strictmode-state',origin).href);
  try{await expect.poll(()=>readiness).toBeGreaterThanOrEqual(2)}finally{release()}
  await expect(page).toHaveURL(new URL(destination,origin).href);
  await expect(page.locator('.access-panel')).toContainText('StrictMode resource');
  expect(exchanges).toBe(1);
 }finally{await server.close()}
});
for(const [role,operation] of Object.entries(operations)){
 test(`actual ${role} identity is constrained by the current role and resource scope`,async({page})=>{
  const bearer=await login(page,role);
  const workspace=await page.request.get(`/api/v1/access/workspaces/${workspaceA}`,{headers:{Authorization:bearer}});
  expect(workspace.status()).toBe(200);const current=(await workspace.json()).data;
  expect(current.roles).toEqual([role]);expect(current.operations).toContain(operation);
  const own=await page.request.get(`/api/v1/access/workspaces/${workspaceA}/resources/${fixtures.users[role].resource_id}`,{headers:{Authorization:bearer}});
  expect(own.status()).toBe(200);
  const deniedOperation=role==='approver'?'document:edit':'document:approve';
  const denied=await page.request.post(`/api/v1/access/workspaces/${workspaceA}/delegations`,{headers:{Authorization:bearer},data:{resource_id:fixtures.users[role].resource_id,operation:deniedOperation,purpose:'acceptance'}});
  expect(denied.status()).toBe(403);
  const forged=await page.request.post(`/api/v1/access/workspaces/${workspaceA}/delegations`,{headers:{Authorization:bearer},data:{operation:'resource:read',purpose:'acceptance',actor_id:fixtures.users.system_admin.actor_id,scope:'*'}});
  expect(forged.status()).toBe(422);
  const unbound=await page.request.post(`/api/v1/access/workspaces/${workspaceA}/delegations`,{headers:{Authorization:bearer},data:{operation:'resource:read',purpose:'acceptance'}});
  expect(unbound.status()).toBe(403);
  expect(await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}))).toEqual({local:[],session:[]});
 });
}

test('workspace picker changes the actual context and a later refresh retains selection',async({page})=>{
 await login(page,'author');
 await openAccount(page,workspaceA);
 await page.getByLabel('选择工作区').selectOption(workspaceB);
 await expect(page).toHaveURL(`/workspaces/${workspaceB}/home`);
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 await page.clock.install();await page.clock.fastForward(15000);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 await page.screenshot({path:'test-results/access-workspace-b.png'});
});

test('an unauthorized resource deep link remains denied after real reauthentication',async({page})=>{
 await login(page,'author',`/workspaces/${workspaceA}/resources/${fixtures.users.expert.resource_id}`);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.getByRole('alert')).toContainText('当前权限不允许此访问');
 await expect(page.getByRole('button',{name:'返回项目首页'})).toBeVisible();
 await page.screenshot({path:'test-results/access-forbidden.png'});
 await page.getByRole('button',{name:'返回项目首页'}).click();
 await expect(page).toHaveURL(`/workspaces/${workspaceA}/home`);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
});

test('switching context clears protected data and late responses cannot restore an old project',async({page})=>{
 await page.clock.install();
 await login(page,'author');
 await openAccount(page,workspaceA);
 await page.getByLabel('选择工作区').selectOption(workspaceB);
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 const discovery=page.getByTestId('discovery-root');
 const contextB=new RegExp(`^${fixtures.users.author.actor_id}:${workspaceB}:`);
 await expect(discovery).toHaveAttribute('data-context',contextB);
 await expect(page.getByTestId('discovery-total')).toBeVisible();
 await expect(page.getByTestId('discovery-storage')).toContainText('字节');
 await page.clock.pauseAt(await page.evaluate(()=>Date.now()+1000));
 let releaseA=()=>{};let releaseB=()=>{};
 let observeA=()=>{};let observeB=()=>{};
 const requestedA=new Promise<void>(r=>{observeA=r});const requestedB=new Promise<void>(r=>{observeB=r});
 const holdA=new Promise<void>(r=>{releaseA=r});const holdB=new Promise<void>(r=>{releaseB=r});
 await page.route(`**/api/v1/access/workspaces/${workspaceA}`,async route=>{observeA();await holdA;await route.continue()});
 await page.route(`**/api/v1/access/workspaces/${workspaceB}`,async route=>{observeB();await holdB;await route.continue()});
 const expectCleared=async()=>{
  await expect(discovery).toHaveCount(0);
  await expect(page.getByTestId('discovery-total')).toHaveCount(0);
  await expect(page.getByTestId('discovery-storage')).toHaveCount(0);
  await expect(page.locator('.project-card b')).toHaveText('等待身份映射');
  await expect(page.locator('#globalSearch')).toBeDisabled();
 };
 try{
  await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceA);
  await requestedA;await expectCleared();
  await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceB);
  await requestedB;await expectCleared();
  releaseB();await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
  await expect(discovery).toHaveAttribute('data-context',contextB);
  // Drain React Query's zero-delay notifications without reaching A's timeout or a poll.
  await expect.poll(async()=>{await page.clock.runFor(1);return page.getByTestId('discovery-total').isVisible()}).toBe(true);
  await expect(page.getByTestId('discovery-total')).toBeVisible();
  const lateA=page.waitForResponse(response=>new URL(response.url()).pathname===`/api/v1/access/workspaces/${workspaceA}`);
  releaseA();const lateResponse=await lateA;
  expect(lateResponse.status()).toBe(200);expect(await lateResponse.finished()).toBeNull();
  await page.clock.runFor(1);
  await expect(page).toHaveURL(`/workspaces/${workspaceB}/home`);
  await expect(discovery).toHaveAttribute('data-context',contextB);
  await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 }finally{releaseA();releaseB()}
});

test('permission change audit is durable and next use clears the revoked workspace',async({page,browser})=>{
 test.setTimeout(2*guardTimeout+60000);
 const adminBearer=await login(page,'system_admin');
 await openAccount(page,workspaceA);
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceA);
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 A');
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await expect(page.getByRole('table',{name:'项目成员权限'})).toBeVisible();
 await page.screenshot({path:'test-results/access-members.png'});
 const authorContext=await browser.newContext();const author=await authorContext.newPage();
 restoreAfterTest=()=>authorContext.close();
 await author.addInitScript(()=>{
  const native=window.setInterval;
  window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args);
 });
 const authorBearer=await login(author,'author');
 await openAccount(author,workspaceA);
 await expect(author.getByLabel('选择工作区')).toHaveValue(workspaceA);
 await expect(author.locator('.project-card b')).toHaveText('本地权限验收项目 A');
 const original=await memberBody(page,adminBearer);
 await prepareRestore(page,adminBearer,original,workspaceA,()=>authorContext.close());
 const delegationClockStart=performance.now();
 const delegationResponse=await author.request.post(`/api/v1/access/workspaces/${workspaceA}/delegations`,{headers:{Authorization:authorBearer},data:{resource_id:fixtures.users.author.resource_id,operation:'resource:read',purpose:'stage-check'}});
 expect(delegationResponse.status()).toBe(200);
 const delegation=(await delegationResponse.json()).data;
 const serverDateUpper=Date.parse(delegationResponse.headers().date)+1000;
 utcMicroseconds(delegation.expires_at);
 expect(Number.isFinite(serverDateUpper)).toBe(true);
 const recordDelegationTiming=async(stage:string,evidence?:WorkerEvidence)=>test.info().attach(`delegation-${stage}.json`,{
  contentType:'application/json',body:JSON.stringify({delegation_id:delegation.delegation_id,
   expires_at:delegation.expires_at,issued_server_date:delegationResponse.headers().date,
   elapsed_ms:performance.now()-delegationClockStart,probe_evidence:evidence,
   conservative_server_time_ms:serverDateUpper+performance.now()-delegationClockStart})});
 // Monotonic command timing is diagnostic; only the governed database clock brackets
 // the actual reply. The post-broadcast isolation guard can finish after expiry.
 await recordDelegationTiming('issued');
 let initialStage:WorkerEvidence|undefined;
 try{initialStage=await workerAccess(delegation.delegation_id,delegation.expires_at)}finally{await recordDelegationTiming('initial-probe-finished',initialStage)}
 expect(initialStage.reply.status).toBe('allowed');
 expect(initialStage.reply.context!.actor_id).toBe(fixtures.users.author.actor_id);
 expect(initialStage.reply.context!.service_id).toBe('eid-worker');
 expect(initialStage.reply.context!.trace_id).toBe(delegation.context.trace_id);
 expect(initialStage.reply.context!.request_id).toBe(delegation.context.request_id);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceA);
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 A');
 await expect(page.getByRole('table',{name:'项目成员权限'})).toBeVisible();
 await test.step('revocation clears the workspace on a fresh list without scheduled polling',async()=>{
  const row=page.getByRole('row').filter({hasText:'本地验收 · author'});
  await row.getByRole('button',{name:'编辑权限'}).click();
  await page.getByLabel('允许成员访问').uncheck();
  await page.getByRole('button',{name:'保存权限',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
  const denied=await author.request.get(`/api/v1/access/workspaces/${workspaceA}/resources/${fixtures.users.author.resource_id}`,{headers:{Authorization:authorBearer}});
  expect(denied.status()).toBe(403);
  await author.getByRole('button',{name:'刷新可访问项目'}).click();
  await expect(author.getByTestId('auth-status')).toHaveText('工作区访问被拒绝');
  await expect(author.locator('.access-panel')).toHaveCount(0);
  await expect(author.locator('.project-card b')).not.toContainText('本地权限验收项目 A');
  await author.screenshot({path:'test-results/access-revoked.png'});
  let revokedStage:WorkerEvidence|undefined;
  try{revokedStage=await workerAccess(delegation.delegation_id,delegation.expires_at)}finally{await recordDelegationTiming('revoked-probe-finished',revokedStage)}
  // Observe an in-TTL denial after the real revoke. Worker denial also covers faults,
  // so this does not claim a specific denial reason from that combined response.
  expect(revokedStage.reply).toEqual({status:'denied'});
 });
});

test('membership conflict discards the stale editor and the next save uses a fresh epoch',async({page})=>{
 const bearer=await login(page,'system_admin');
 await openAccount(page,workspaceA);
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 const row=page.getByRole('row').filter({hasText:'本地验收 · author'});
 await row.getByRole('button',{name:'编辑权限'}).click();
 const original=await memberBody(page,bearer);
 const mutation=await prepareRestore(page,bearer,original);
 await page.clock.install();await page.clock.pauseAt(new Date());
 const concurrent=await mutation.put(original);
 expect(concurrent.status()).toBe(200);
 let release=()=>{};const hold=new Promise<void>(resolve=>{release=resolve});
 await page.route('**/api/v1/access/workspaces/*/members/*',async route=>{await hold;await route.fallback()});
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 try{await expect(page.getByLabel('选择工作区')).toBeDisabled()}finally{release()}
 await expect(page.getByRole('status').filter({hasText:'权限已变化'})).toBeVisible();
 await expect(page.locator('.access-editor')).toHaveCount(0);
 await row.getByRole('button',{name:'编辑权限'}).click();
 await page.setViewportSize({width:1920,height:2200});
 await page.locator('.access-editor').screenshot({path:'test-results/access-editor.png'});
 await page.setViewportSize({width:1920,height:1080});
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
});

test('empty membership response has a persistent explanation',async({page})=>{
 await login(page,'system_admin');
 await openAccount(page,workspaceA);
 await page.route('**/api/v1/access/workspaces/*/members',async route=>{
  const response=await route.fetch();const body=await response.json();
  body.data.members=[];body.data.next_cursor=null;
  await route.fulfill({response,json:body});
 });
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'当前没有可显示的成员'})).toBeVisible();
 await expect(page.locator('#member-page-state')).toHaveText('第 1 页 · 已是首页 · 已是末页');
 for(const name of ['上一页成员','下一页成员']){
  const button=page.getByRole('button',{name});
  await expect(button).toBeDisabled();
  await expect(button).toHaveAccessibleDescription('第 1 页 · 已是首页 · 已是末页');
  await expect(button).toHaveCSS('cursor','not-allowed');
 }
 await page.screenshot({path:'test-results/access-members-empty.png'});
});

test('history navigation during member save preserves its original audit and cannot refill the destination',async({page})=>{
 test.setTimeout(guardTimeout+60000);
 const bearer=await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 await prepareRestore(page,bearer,original);
 await openAccount(page,workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 const clearance=original.clearance===1?2:1;
 await page.getByLabel('密级上限').selectOption(String(clearance));
 let release=()=>{};const hold=new Promise<void>(resolve=>{release=resolve});
 const path=`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`;
 let requestId='';
 await page.route(`**${path}`,async route=>{requestId=route.request().headers()['x-request-id'];await hold;await route.fallback()});
 const completed=page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='PUT');
 try{
  await page.getByRole('button',{name:'保存权限',exact:true}).click();
  await expect(page.getByLabel('选择工作区')).toBeDisabled();
  await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceB);
  await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 }finally{release()}
 const response=await completed;expect(response.status()).toBe(200);
 const result=(await response.json()).data;
 const audit=await auditEvidence(result.audit_id);
 expect(audit).toMatchObject({workspace_id:workspaceA,actor_id:fixtures.users.system_admin.actor_id,target_id:fixtures.users.author.actor_id,action:'membership.change',request_id:requestId,after_policy:{workspace_id:workspaceA,identity_id:fixtures.users.author.actor_id,clearance}});
 expect(audit.trace_id).toMatch(/^[0-9a-f]{32}$/);
 expect((await memberBody(page,bearer)).clearance).toBe(clearance);
 await expect(page).toHaveURL(`/workspaces/${workspaceB}/home`);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
 await expect(page.locator('.access-editor')).toHaveCount(0);
 await expect(page.getByRole('status').filter({hasText:'权限已保存'})).toHaveCount(0);
 await page.unrouteAll({behavior:'wait'});
});

test('invalid member validity is an input error and preserves the editable form',async({page})=>{
 const bearer=await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 // Even a validation regression must retain the original policy and block later fixture tests.
 await prepareRestore(page,bearer,original);
 await openAccount(page,workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 await page.getByLabel('生效时间（含时区）',{exact:true}).fill('2026-09-14T00:00:00');
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'输入格式无效'})).toBeVisible();
 await expect(page.locator('.access-editor')).toBeVisible();
 expect(await memberBody(page,bearer)).toEqual(original);
});

test('member editor persists authority fields and complete scope values with an audit',async({page})=>{
 test.setTimeout(guardTimeout+60000);
 const bearer=await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 await prepareRestore(page,bearer,original);
 await openAccount(page,workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 expect(original.roles).toEqual(['author']);
 await page.getByRole('checkbox',{name:'作者',exact:true}).uncheck();
 await page.getByRole('checkbox',{name:'专家',exact:true}).check();
 const owner:MemberBody['owner_scope']=original.owner_scope==='self'?'any':'self';
 await page.getByLabel('所有者范围').selectOption(owner);
 const approved=!original.approval_states.includes('approved');
 await page.getByRole('checkbox',{name:'已批准',exact:true}).setChecked(approved);
 const approval_states=approved?[...original.approval_states,'approved']:original.approval_states.filter((value:string)=>value!=='approved');
 const scopes:Record<string,string[]>={};
 for(const [key,label] of [['project_scope','项目范围'],['customer_scope','客户范围'],['product_scope','产品范围'],['department_scope','部门范围']]){
  const added=`ui-save-${key}`;scopes[key]=[...original[key as 'project_scope'],added];
  await page.getByRole('button',{name:`添加${label}`,exact:true}).click();
  await page.getByLabel(`${label}第${scopes[key].length}项`,{exact:true}).fill(added);
 }
 const valid_from=new Date(new Date(original.valid_from).getTime()+1000).toISOString();
 const valid_until=new Date(Date.now()+86400000).toISOString();
 await page.getByLabel('生效时间（含时区）',{exact:true}).fill(valid_from);
 await page.getByLabel('失效时间（可留空）',{exact:true}).fill(valid_until);
 const path=`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`;
 const completed=page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='PUT');
 const expected={roles:['expert'],owner_scope:owner,approval_states,...scopes};
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 const response=await completed;expect(response.status()).toBe(200);
 const saved=(await response.json()).data;
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
 const persisted=await memberBody(page,bearer);
 expect(persisted).toMatchObject(expected);
 expect(new Date(persisted.valid_from).getTime()).toBe(new Date(valid_from).getTime());
 expect(new Date(persisted.valid_until).getTime()).toBe(new Date(valid_until).getTime());
 const audit=await auditEvidence(saved.audit_id);
 expect(audit).toMatchObject({workspace_id:workspaceA,actor_id:fixtures.users.system_admin.actor_id,target_id:fixtures.users.author.actor_id,action:'membership.change',request_id:response.request().headers()['x-request-id'],after_policy:expected});
 expect(new Date(audit.after_policy.valid_from).getTime()).toBe(new Date(valid_from).getTime());
 expect(new Date(audit.after_policy.valid_until).getTime()).toBe(new Date(valid_until).getTime());
});

test('member pagination follows the server cursor and supports returning to the first page',async({page})=>{
 await login(page,'system_admin');await openAccount(page,workspaceA);await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceA);
 let first='';
 await page.route('**/api/v1/access/workspaces/*/members*',async route=>{
  const response=await route.fetch();const body=await response.json();
  if(!new URL(route.request().url()).searchParams.has('after')){
   first=body.data.members[0].display_name;
   body.data.next_cursor=body.data.members[0].identity_id;body.data.members=body.data.members.slice(0,1);
  }
  await route.fulfill({response,json:body});
 });
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await expect(page.getByRole('button',{name:'下一页成员'})).toBeEnabled();
 await expect(page.getByRole('button',{name:'上一页成员'})).toHaveAccessibleDescription('第 1 页 · 已是首页');
 await page.getByRole('button',{name:'下一页成员'}).click();
 await expect(page.getByRole('button',{name:'上一页成员'})).toBeEnabled();
 await expect(page.getByRole('button',{name:'下一页成员'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'下一页成员'})).toHaveAccessibleDescription('第 2 页 · 已是末页');
 await expect(page.getByRole('table')).not.toContainText(first);
 await page.getByRole('button',{name:'上一页成员'}).click();
 await expect(page.getByRole('table')).toContainText(first);
});

test('malformed resource address stops instead of retrying an invalid request',async({page})=>{
 await login(page,'author');let requests=0;
 await page.route('**/api/v1/access/workspaces/*/resources/*',route=>{requests++;return route.continue()});
 await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/resources/not-a-uuid`);dispatchEvent(new PopStateEvent('popstate'))},workspaceA);
 await expect(page.getByRole('alert')).toHaveText('项目或资源地址无效');
 await page.clock.install();await page.clock.fastForward(30000);
 expect(requests).toBe(0);await expect(page.locator('.access-panel')).toHaveCount(0);
});

test('a default workspace revoked between reads resolves another current project once',async({page})=>{
 await page.addInitScript(()=>{const native=window.setInterval;window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args)});
 const readPaths:string[]=[];
 await page.route('**/api/v1/me',async route=>{
  readPaths.push(new URL(page.url()).pathname);
  const response=await route.fetch();const body=await response.json();
  body.data.workspace_id=readPaths.length===1?defaultWorkspace:remainingWorkspace;
  await route.fulfill({response,json:body});
 });
 await page.route(`**/api/v1/access/workspaces/${defaultWorkspace}`,route=>route.fulfill({status:403,json:{error:{message:'denied'}}}));
 await login(page,'author','/');
 await expect(page).toHaveURL(`/workspaces/${remainingWorkspace}/home`);
 // Two root reads resolve the race; entering the explicit project reloads its account.
 await expect.poll(()=>readPaths).toEqual(['/','/',`/workspaces/${remainingWorkspace}/home`]);
 await expect(page.locator('.project-card b')).toHaveText(workspaceName(remainingWorkspace));
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
});

test('uppercase UUID deep links resolve to the same authorized resource',async({page})=>{
 await login(page,'author',`/workspaces/${workspaceA.toUpperCase()}/resources/${fixtures.users.author.resource_id.toUpperCase()}`);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.locator('.access-panel')).toContainText('本地授权验收资源 · author');
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceA);
});

test('two default project races remain retryable without signing out',async({page})=>{
 await page.addInitScript(()=>{const native=window.setInterval;window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args)});
 const bearer=await login(page,'author',`/workspaces/${defaultWorkspace}/home`);
 const readPaths:string[]=[];const authorizations:string[]=[];let denying=true;
 await page.route('**/api/v1/me',async route=>{
  readPaths.push(new URL(page.url()).pathname);authorizations.push(route.request().headers().authorization);
  const response=await route.fetch();const body=await response.json();
  if(denying)body.data.workspace_id=readPaths.length===1?defaultWorkspace:remainingWorkspace;
  await route.fulfill({response,json:body});
 });
 await page.route('**/api/v1/access/workspaces/*',route=>denying
  ?route.fulfill({status:403,json:{error:{message:'denied'}}}):route.continue());
 // Keep the document (and its module-only token) while re-entering default selection.
 await page.evaluate(()=>{history.pushState({},'','/');dispatchEvent(new PopStateEvent('popstate'))});
 await expect(page.getByTestId('auth-status')).toHaveText('账户服务暂时不可用');
 await expect(page.getByTestId('discovery-root')).toHaveCount(0);
 expect(readPaths).toEqual(['/','/']);
 expect(authorizations).toEqual([bearer,bearer]);
 denying=false;
 await page.getByRole('button',{name:'重试账户加载'}).click();
 await expect(page).toHaveURL(/\/workspaces\/[0-9a-f-]{36}\/home$/);
 await expect.poll(()=>readPaths).toEqual(['/','/','/',new URL(page.url()).pathname]);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
 expect(authorizations).toEqual([bearer,bearer,bearer,bearer]);
});

test('save denial clears the member table before the delayed account refresh completes',async({page})=>{
 await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 await openAccount(page,workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 let release=()=>{};const hold=new Promise<void>(resolve=>{release=resolve});let reads=0;
 await page.route('**/api/v1/me',async route=>{reads++;await hold;await route.continue()});
 await page.route('**/api/v1/access/workspaces/*/members/*',route=>route.fulfill({status:403,json:{error:{message:'denied'}}}));
 try{
  await page.getByRole('button',{name:'保存权限',exact:true}).click();
  await expect.poll(()=>reads).toBeGreaterThan(0);
  await expect(page.getByRole('alert')).toContainText('当前权限不允许此访问');
  await expect(page.getByRole('table',{name:'项目成员权限'})).toHaveCount(0);
  await expect(page.locator('.access-editor')).toHaveCount(0);
 }finally{release()}
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
});

test('account denial discards the saved audit receipt before subsequent navigation recovery',async({page})=>{
 await page.clock.install();
 const bearer=await login(page,'system_admin');
 await expect(page).toHaveURL(`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 await prepareRestore(page,bearer,original);
 await openAccount(page,workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await page.route('**/api/v1/me',route=>route.fulfill({status:403,json:{error:{message:'denied'}}}));
 await page.clock.fastForward(15000);
 await expect(page.getByTestId('auth-status')).toHaveText('工作区访问被拒绝');
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toHaveCount(0);
 await page.unroute('**/api/v1/me');
 await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceB);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page).toHaveURL(`/workspaces/${workspaceB}/home`);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toHaveCount(0);
});

test('a cached resource denied on refetch clears its display without an automatic request loop',async({page})=>{
 await login(page,'author',`/workspaces/${workspaceA}/resources/${fixtures.users.author.resource_id}`);
 await expect(page.locator('.access-panel')).toContainText('本地授权验收资源 · author');
 let deniedRequests=0;
 await page.route('**/api/v1/access/workspaces/*/resources/*',route=>{
  deniedRequests++;return route.fulfill({status:403,json:{error:{message:'denied'}}});
 });
 await page.evaluate(()=>{
  window.dispatchEvent(new Event('offline'));
  window.dispatchEvent(new Event('online'));
 });
 await expect.poll(()=>deniedRequests,{message:'Reconnect must reach the protected-resource handler'}).toBeGreaterThan(0);
 await expect(page.getByRole('alert')).toContainText('当前权限不允许此访问');
 await expect(page.locator('.access-panel')).not.toContainText('本地授权验收资源 · author');
 await page.waitForTimeout(1000);
 expect(deniedRequests).toBe(1);
 await page.getByRole('button',{name:'重新读取权限'}).click();
 await expect.poll(()=>deniedRequests).toBe(2);
 await page.getByRole('button',{name:'返回项目首页'}).click();
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
});

test('unsupported route suffixes never request protected data',async({page})=>{
 await login(page,'author');let requests=0;
 await page.route('**/api/v1/access/**',route=>{requests++;return route.continue()});
 for(const path of [`/workspaces/${workspaceA}/home/unknown`,`/workspaces/${workspaceA}/resources/${fixtures.users.author.resource_id}/unknown`]){
  await page.evaluate(path=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))},path);
  await expect(page.getByRole('alert')).toHaveText('项目或资源地址无效');
  await expect(page.locator('.access-panel')).toHaveCount(0);
 }
 expect(requests).toBe(0);
});

test('scope editor retains commas and individual multiline values when editing',async({page})=>{
 await login(page,'system_admin');
 await openAccount(page,workspaceA);
 await page.route('**/api/v1/access/workspaces/*/members',async route=>{
  const response=await route.fetch();const body=await response.json();
  body.data.members[0].customer_scope=['customer-a,inc','line one\nline two'];
  await route.fulfill({response,json:body});
 });
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('button',{name:'编辑权限'}).first().click();
 await expect(page.getByLabel('客户范围第1项',{exact:true})).toHaveValue('customer-a,inc');
 await expect(page.getByLabel('客户范围第2项',{exact:true})).toHaveValue('line one\nline two');
 await page.getByLabel('客户范围第1项',{exact:true}).fill('customer-b,inc');
 let submitted:unknown;
 await page.route('**/api/v1/access/workspaces/*/members/*',async route=>{
  submitted=route.request().postDataJSON().customer_scope;
  await route.fulfill({status:409,json:{error:{message:'test conflict'}}});
 });
 const refreshed=page.waitForResponse(response=>/\/members$/.test(new URL(response.url()).pathname));
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'权限已变化'})).toBeVisible();
 expect(submitted).toEqual(['customer-b,inc','line one\nline two']);
 await refreshed;await expect(page.getByRole('table',{name:'项目成员权限'})).toBeVisible();
 await page.unrouteAll({behavior:'wait'});
});

test('a role without member management can return from a denied admin deep link',async({page})=>{
 await login(page,'author','/admin/members');
 await expect(page.getByRole('alert')).toContainText('当前权限不允许此访问');
 await page.getByRole('button',{name:'返回项目首页'}).click();
 await expect(page).toHaveURL(`/workspaces/${workspaceA}/home`);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
 await expect(page.getByRole('alert')).toHaveCount(0);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
});

test('a fresh project list replaces an outdated role epoch without waiting for a poll',async({page,browser})=>{
 const bearer=await login(page,'system_admin');const original=await memberBody(page,bearer);
 const context=await browser.newContext();const author=await context.newPage();
 restoreAfterTest=()=>context.close();
 await author.addInitScript(()=>{const native=window.setInterval;window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args)});
 await login(author,'author',`/workspaces/${workspaceA}/home`);
 await openAccount(author,workspaceA);
 await expect(author.locator('.access-panel')).toContainText('作者');
 const mutation=await prepareRestore(page,bearer,original,workspaceA,()=>context.close());
 const changed=await mutation.put({...original,roles:['expert']});
 expect(changed.status()).toBe(200);
 await author.getByRole('button',{name:'刷新可访问项目'}).click();
 await expect(author.locator('.access-panel')).toContainText('专家');
 await expect(author.locator('.access-panel')).not.toContainText('作者');
 await expect(author.locator('.project-card b')).toHaveText('本地权限验收项目 A');
});
