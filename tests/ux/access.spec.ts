import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';

const fixtures=JSON.parse(readFileSync('.local/access-fixtures.json','utf8').replace(/^\uFEFF/,'')) as {
 workspaces:string[];users:Record<string,{username:string;subject:string;actor_id:string;resource_id:string}>;
};
const [workspaceA,workspaceB]=fixtures.workspaces;
let restoreAfterTest:(()=>Promise<void>)|undefined;
test.afterEach(async()=>{const restore=restoreAfterTest;restoreAfterTest=undefined;await restore?.()});
function workerAccess(id:string){
 const python=resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
 const result=spawnSync(python,['-m','scripts.verify_access_delegation',id,'resource:read','stage-check'],{encoding:'utf8',timeout:25000});
 expect(result.status,result.stderr).toBe(0);return JSON.parse(result.stdout);
}
function auditEvidence(id:string){
 const python=resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
 const source=`import json,sys,psycopg
from uuid import UUID
from psycopg.rows import dict_row
from scripts.verify_local_environment import verify_migration_target
url='postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev'
verify_migration_target(url)
identifier=UUID(json.load(sys.stdin)['id'])
with psycopg.connect(url.replace('postgresql+psycopg:','postgresql:'),row_factory=dict_row,connect_timeout=3,options='-c statement_timeout=2000 -c default_transaction_read_only=on') as conn:
    assert conn.execute('SELECT current_database() AS db,current_user AS role').fetchone()=={'db':'eid_local_dev','role':'eid_migrator'}
    row=conn.execute('SELECT workspace_id::text,actor_id::text,target_id::text,action,after_policy,request_id,trace_id FROM access_audit WHERE id=%s',(identifier,)).fetchone()
    assert row is not None
    print(json.dumps(row))
`;
 const result=spawnSync(python,['-c',source],{input:JSON.stringify({id}),encoding:'utf8',timeout:25000});
 expect(result.status,result.stderr).toBe(0);return JSON.parse(result.stdout);
}
async function login(page:Page,role:string,path='/'){
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
async function memberBody(page:Page,bearer:string){
 const response=await page.request.get(`/api/v1/access/workspaces/${workspaceA}/members`,{headers:{Authorization:bearer}});
 expect(response.status()).toBe(200);
 const data=(await response.json()).data;
 const row=data.members.find((m:{identity_id:string})=>m.identity_id===fixtures.users.author.actor_id);
 const keys=['active','roles','project_scope','customer_scope','product_scope','department_scope','owner_scope','approval_states','clearance','valid_from','valid_until'];
 return {...Object.fromEntries(keys.map(k=>[k,row[k]])),expected_epoch:data.policy_epoch};
}
const operations:Record<string,string>={author:'document:edit',expert:'document:review',quality:'quality:review',template_admin:'template:publish',knowledge_admin:'knowledge:manage',approver:'document:approve',system_admin:'membership:manage'};

test('workspace pages render independently and retain a current project absent from the page',async({page})=>{
 await login(page,'author',`/workspaces/${workspaceB}/home`);
 let reads=0;
 await page.route('**/api/v1/access/workspaces*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname!=='/api/v1/access/workspaces')return route.continue();
  reads++;const response=await route.fetch();const body=await response.json();
  if(!url.searchParams.has('after')){body.data.workspaces=body.data.workspaces.filter((p:{workspace_id:string})=>p.workspace_id===workspaceA);body.data.next_cursor=workspaceA}
  await route.fulfill({response,json:body});
 });
 await page.getByRole('button',{name:'刷新可访问项目'}).click();
 await expect(page.getByRole('button',{name:'下一页项目'})).toBeEnabled();
 await expect(page.getByRole('button',{name:'上一页项目'})).toBeDisabled();
 await expect(page.getByRole('button',{name:'上一页项目'})).toHaveAccessibleDescription('第 1 页 · 已是首页');
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceB);
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
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

test('history navigation opens and closes member management without retaining an editor',async({page})=>{
 await login(page,'system_admin');
 await page.evaluate(()=>{history.pushState({},'','/admin/members');dispatchEvent(new PopStateEvent('popstate'))});
 await expect(page.getByRole('table',{name:'项目成员权限'})).toBeVisible();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 await expect(page.locator('.access-editor')).toBeVisible();
 await page.goBack();
 await expect(page).toHaveURL('/');
 await expect(page.locator('.access-admin')).toHaveCount(0);
 await expect(page.locator('.access-editor')).toHaveCount(0);
 await page.goForward();
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
 await expect(page.getByLabel('选择工作区')).toBeVisible();
});

test('root project revocation discovers another real membership before the account poll',async({page,browser})=>{
 const bearer=await login(page,'system_admin');
 const original=await memberBody(page,bearer);
 const context=await browser.newContext();const author=await context.newPage();
 restoreAfterTest=async()=>{
  try{
   const latest=await memberBody(page,bearer);
   const restored=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:{...original,expected_epoch:latest.expected_epoch}});
   expect(restored.status()).toBe(200);
  }finally{await context.close()}
 };
 await author.addInitScript(()=>{
  const native=window.setInterval;
  window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args);
 });
 await login(author,'author');
 await expect(author.getByLabel('选择工作区')).toHaveValue(workspaceA);
 const latest=await memberBody(page,bearer);
 const revoked=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:{...original,active:false,expected_epoch:latest.expected_epoch}});
 expect(revoked.status()).toBe(200);
 await author.getByRole('button',{name:'刷新可访问项目'}).click();
 await expect(author.getByLabel('选择工作区')).toHaveValue(workspaceB);
 await expect(author.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(author.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 await expect(author).toHaveURL('/');
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
 await expect(page.getByLabel('选择工作区')).toBeVisible();
});

test('switching context clears protected data and late responses cannot restore an old project',async({page})=>{
 await login(page,'author');
 await page.getByLabel('选择工作区').selectOption(workspaceB);
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 let releaseA=()=>{};let releaseB=()=>{};
 const holdA=new Promise<void>(r=>{releaseA=r});const holdB=new Promise<void>(r=>{releaseB=r});
 await page.route(`**/api/v1/access/workspaces/${workspaceA}`,async route=>{await holdA;await route.continue()});
 await page.route(`**/api/v1/access/workspaces/${workspaceB}`,async route=>{await holdB;await route.continue()});
 try{
  await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceA);
  await expect(page.locator('.access-panel')).toHaveCount(0);
  await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceB);
  await expect(page.locator('.access-panel')).toHaveCount(0);
  await expect(page.locator('.project-card b')).not.toContainText('本地权限验收项目');
  releaseB();await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
  releaseA();await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 }finally{releaseA();releaseB()}
});

test('permission change audit is durable and next use clears the revoked workspace',async({page,browser})=>{
 const adminBearer=await login(page,'system_admin');
 await page.getByLabel('选择工作区').selectOption(workspaceA);
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
 await author.getByLabel('选择工作区').selectOption(workspaceA);
 await expect(author.locator('.project-card b')).toHaveText('本地权限验收项目 A');
 const original=await memberBody(page,adminBearer);
 restoreAfterTest=async()=>{
  try{
   const latest=await memberBody(page,adminBearer);
   const restored=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:adminBearer},data:{...original,expected_epoch:latest.expected_epoch}});
   expect(restored.status()).toBe(200);
  }finally{await authorContext.close()}
 };
 const delegationResponse=await author.request.post(`/api/v1/access/workspaces/${workspaceA}/delegations`,{headers:{Authorization:authorBearer},data:{resource_id:fixtures.users.author.resource_id,operation:'resource:read',purpose:'stage-check'}});
 expect(delegationResponse.status()).toBe(200);
 const delegation=(await delegationResponse.json()).data;
 const initialStage=workerAccess(delegation.delegation_id);
 expect(initialStage.status).toBe('allowed');
 expect(initialStage.context.actor_id).toBe(fixtures.users.author.actor_id);
 expect(initialStage.context.service_id).toBe('eid-worker');
 expect(initialStage.context.trace_id).toBe(delegation.context.trace_id);
 expect(initialStage.context.request_id).toBe(delegation.context.request_id);
 await test.step('revocation clears the workspace on a fresh list without scheduled polling',async()=>{
  const row=page.getByRole('row').filter({hasText:'本地验收 · author'});
  await row.getByRole('button',{name:'编辑权限'}).click();
  await page.getByLabel('允许成员访问').uncheck();
  await page.getByRole('button',{name:'保存权限',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
  const denied=await author.request.get(`/api/v1/access/workspaces/${workspaceA}/resources/${fixtures.users.author.resource_id}`,{headers:{Authorization:authorBearer}});
  expect(denied.status()).toBe(403);
  expect(workerAccess(delegation.delegation_id)).toEqual({status:'denied'});
  await author.getByRole('button',{name:'刷新可访问项目'}).click();
  await expect(author.getByTestId('auth-status')).toHaveText('工作区访问被拒绝');
  await expect(author.locator('.access-panel')).toHaveCount(0);
  await expect(author.locator('.project-card b')).not.toContainText('本地权限验收项目 A');
  await author.screenshot({path:'test-results/access-revoked.png'});
 });
});

test('membership conflict discards the stale editor and the next save uses a fresh epoch',async({page})=>{
 const bearer=await login(page,'system_admin');
 await page.getByLabel('选择工作区').selectOption(workspaceA);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 const row=page.getByRole('row').filter({hasText:'本地验收 · author'});
 await row.getByRole('button',{name:'编辑权限'}).click();
 const original=await memberBody(page,bearer);
 await page.clock.install();await page.clock.pauseAt(new Date());
 const concurrent=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:original});
 expect(concurrent.status()).toBe(200);
 let release=()=>{};const hold=new Promise<void>(resolve=>{release=resolve});
 await page.route('**/api/v1/access/workspaces/*/members/*',async route=>{await hold;await route.continue()});
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
 const bearer=await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 restoreAfterTest=async()=>{
  const latest=await memberBody(page,bearer);
  const restored=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:{...original,expected_epoch:latest.expected_epoch}});
  expect(restored.status()).toBe(200);
 };
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 const clearance=original.clearance===1?2:1;
 await page.getByLabel('密级上限').selectOption(String(clearance));
 let release=()=>{};const hold=new Promise<void>(resolve=>{release=resolve});
 const path=`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`;
 let requestId='';
 await page.route(`**${path}`,async route=>{requestId=route.request().headers()['x-request-id'];await hold;await route.continue()});
 const completed=page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='PUT');
 try{
  await page.getByRole('button',{name:'保存权限',exact:true}).click();
  await expect(page.getByLabel('选择工作区')).toBeDisabled();
  await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceB);
  await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 }finally{release()}
 const response=await completed;expect(response.status()).toBe(200);
 const result=(await response.json()).data;
 const audit=auditEvidence(result.audit_id);
 expect(audit).toMatchObject({workspace_id:workspaceA,actor_id:fixtures.users.system_admin.actor_id,target_id:fixtures.users.author.actor_id,action:'membership.change',request_id:requestId,after_policy:{workspace_id:workspaceA,identity_id:fixtures.users.author.actor_id,clearance}});
 expect(audit.trace_id).toMatch(/^[0-9a-f]{32}$/);
 expect((await memberBody(page,bearer)).clearance).toBe(clearance);
 await expect(page).toHaveURL(`/workspaces/${workspaceB}/home`);
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceB);
 await expect(page.locator('.access-editor')).toHaveCount(0);
 await expect(page.getByRole('status').filter({hasText:'权限已保存'})).toHaveCount(0);
 await page.unrouteAll({behavior:'wait'});
});

test('invalid member validity is an input error and preserves the editable form',async({page})=>{
 const bearer=await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 await page.getByLabel('生效时间（含时区）',{exact:true}).fill('2026-09-14T00:00:00');
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'输入格式无效'})).toBeVisible();
 await expect(page.locator('.access-editor')).toBeVisible();
 expect(await memberBody(page,bearer)).toEqual(original);
});

test('member editor persists authority fields and complete scope values with an audit',async({page})=>{
 const bearer=await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
 const original=await memberBody(page,bearer);
 restoreAfterTest=async()=>{
  const latest=await memberBody(page,bearer);
  const restored=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:{...original,expected_epoch:latest.expected_epoch}});
  expect(restored.status()).toBe(200);
 };
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 expect(original.roles).toEqual(['author']);
 await page.getByRole('checkbox',{name:'作者',exact:true}).uncheck();
 await page.getByRole('checkbox',{name:'专家',exact:true}).check();
 const owner=original.owner_scope==='self'?'any':'self';
 await page.getByLabel('所有者范围').selectOption(owner);
 const approved=!original.approval_states.includes('approved');
 await page.getByRole('checkbox',{name:'已批准',exact:true}).setChecked(approved);
 const approval_states=approved?[...original.approval_states,'approved']:original.approval_states.filter((value:string)=>value!=='approved');
 const scopes:Record<string,string[]>={};
 for(const [key,label] of [['project_scope','项目范围'],['customer_scope','客户范围'],['product_scope','产品范围'],['department_scope','部门范围']]){
  const added=`ui-save-${key}`;scopes[key]=[...original[key],added];
  await page.getByRole('button',{name:`添加${label}`,exact:true}).click();
  await page.getByLabel(`${label}第${scopes[key].length}项`,{exact:true}).fill(added);
 }
 const valid_from=new Date(new Date(original.valid_from).getTime()+1000).toISOString();
 const valid_until=new Date(Date.now()+86400000).toISOString();
 await page.getByLabel('生效时间（含时区）',{exact:true}).fill(valid_from);
 await page.getByLabel('失效时间（可留空）',{exact:true}).fill(valid_until);
 const path=`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`;
 const completed=page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='PUT');
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 const response=await completed;expect(response.status()).toBe(200);
 const saved=(await response.json()).data;
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
 const persisted=await memberBody(page,bearer);
 const expected={roles:['expert'],owner_scope:owner,approval_states,...scopes};
 expect(persisted).toMatchObject(expected);
 expect(new Date(persisted.valid_from).getTime()).toBe(new Date(valid_from).getTime());
 expect(new Date(persisted.valid_until).getTime()).toBe(new Date(valid_until).getTime());
 const audit=auditEvidence(saved.audit_id);
 expect(audit).toMatchObject({workspace_id:workspaceA,actor_id:fixtures.users.system_admin.actor_id,target_id:fixtures.users.author.actor_id,action:'membership.change',request_id:response.request().headers()['x-request-id'],after_policy:expected});
 expect(new Date(audit.after_policy.valid_from).getTime()).toBe(new Date(valid_from).getTime());
 expect(new Date(audit.after_policy.valid_until).getTime()).toBe(new Date(valid_until).getTime());
});

test('member pagination follows the server cursor and supports returning to the first page',async({page})=>{
 await login(page,'system_admin');await page.getByLabel('选择工作区').selectOption(workspaceA);
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
 let reads=0;
 await page.route('**/api/v1/me',async route=>{
  const response=await route.fetch();const body=await response.json();reads++;
  body.data.workspace_id=reads===1?workspaceA:workspaceB;
  await route.fulfill({response,json:body});
 });
 await page.route(`**/api/v1/access/workspaces/${workspaceA}`,route=>route.fulfill({status:403,json:{error:{message:'denied'}}}));
 await login(page,'author');
 await expect(page.locator('.project-card b')).toHaveText('本地权限验收项目 B');
 expect(reads).toBe(2);
});

test('uppercase UUID deep links resolve to the same authorized resource',async({page})=>{
 await login(page,'author',`/workspaces/${workspaceA.toUpperCase()}/resources/${fixtures.users.author.resource_id.toUpperCase()}`);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.locator('.access-panel')).toContainText('本地授权验收资源 · author');
 await expect(page.getByLabel('选择工作区')).toHaveValue(workspaceA);
});

test('two default project races remain retryable without signing out',async({page})=>{
 await page.clock.install();
 await login(page,'author');
 await expect(page.getByRole('button',{name:'刷新可访问项目'})).toBeEnabled();
 let reads=0;let denying=true;
 await page.route('**/api/v1/me',async route=>{
  const response=await route.fetch();const body=await response.json();reads++;
  if(denying)body.data.workspace_id=reads===1?workspaceA:workspaceB;
  await route.fulfill({response,json:body});
 });
 await page.route('**/api/v1/access/workspaces/*',route=>denying
  ?route.fulfill({status:403,json:{error:{message:'denied'}}}):route.continue());
 await page.clock.fastForward(15000);
 await expect(page.getByTestId('auth-status')).toHaveText('账户服务暂时不可用');
 await expect(page.locator('.access-panel')).toHaveCount(0);
 expect(reads).toBe(2);
 denying=false;
 await page.getByRole('button',{name:'重试账户加载'}).click();
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await expect(page.getByLabel('选择工作区')).toBeVisible();
 expect(reads).toBe(3);
});

test('save denial clears the member table before the delayed account refresh completes',async({page})=>{
 await login(page,'system_admin',`/workspaces/${workspaceA}/home`);
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
 await login(page,'system_admin');
 await page.getByRole('button',{name:'成员与权限',exact:true}).click();
 await page.getByRole('row').filter({hasText:'本地验收 · author'}).getByRole('button',{name:'编辑权限'}).click();
 await page.getByRole('button',{name:'保存权限',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'权限已保存，审计编号'})).toBeVisible();
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
 await page.route('**/api/v1/me',route=>route.fulfill({status:403,json:{error:{message:'denied'}}}));
 await page.clock.fastForward(15000);
 await expect(page.getByTestId('auth-status')).toHaveText('工作区访问被拒绝');
 await page.unroute('**/api/v1/me');
 await page.evaluate(id=>{history.pushState({},'',`/workspaces/${id}/home`);dispatchEvent(new PopStateEvent('popstate'))},workspaceA);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
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
 await expect(page.getByLabel('选择工作区')).toBeVisible();
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
 await expect(page.getByLabel('选择工作区')).toBeVisible();
 await expect(page.getByRole('alert')).toHaveCount(0);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
});

test('a fresh project list replaces an outdated role epoch without waiting for a poll',async({page,browser})=>{
 const bearer=await login(page,'system_admin');const original=await memberBody(page,bearer);
 const context=await browser.newContext();const author=await context.newPage();
 restoreAfterTest=()=>context.close();
 await author.addInitScript(()=>{const native=window.setInterval;window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>native(timeout===15000?()=>{}:handler,timeout,...args)});
 await login(author,'author',`/workspaces/${workspaceA}/home`);
 await expect(author.locator('.access-panel')).toContainText('作者');
 restoreAfterTest=async()=>{
  try{const latest=await memberBody(page,bearer);const restored=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:{...original,expected_epoch:latest.expected_epoch}});expect(restored.status()).toBe(200)}finally{await context.close()}
 };
 const changed=await page.request.put(`/api/v1/access/workspaces/${workspaceA}/members/${fixtures.users.author.actor_id}`,{headers:{Authorization:bearer},data:{...original,roles:['expert']}});
 expect(changed.status()).toBe(200);
 await author.getByRole('button',{name:'刷新可访问项目'}).click();
 await expect(author.locator('.access-panel')).toContainText('专家');
 await expect(author.locator('.access-panel')).not.toContainText('作者');
 await expect(author.locator('.project-card b')).toHaveText('本地权限验收项目 A');
});
