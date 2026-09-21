import {expect,test,type Page,type Request,type Route} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import type {Detail,Item,Page as DiscoveryPage,Receipt,Summary} from '../../edw-web/src/app/discovery-api';
import {evidencePath,guardTimeout,selectedDiscoveryFixture,type DiscoveryFixture,type FixtureLease} from './discovery-fixtures';

let fixture:DiscoveryFixture,lease:FixtureLease;
const bearer=new WeakMap<Page,string>(); // Current page request only; never attach/persist a token.
const discovery=(workspace=fixture.workspaces.a)=>`/api/v1/workspaces/${workspace}/discovery`;
const ids=(keys:string[])=>keys.map(key=>fixture.records[key]).sort().reverse();
const rowIds=(page:Page)=>page.locator('[data-testid="discovery-table"] tbody tr').evaluateAll(rows=>rows.map(row=>row.getAttribute('data-record-id')));
const normalDocuments=()=>['a:document','a:other-owner','a:archived',...Array.from({length:32},(_,i)=>`a:page-${String(i).padStart(2,'0')}`)];
const feedback=(page:Page)=>page.locator('[data-testid="discovery-root"] .discovery-body > p.notice[role="status"]');
function deferred<T>(){let resolve!:(value:T)=>void,reject!:(error:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}

test.describe.configure({mode:'serial',retries:0});
test.beforeAll(async()=>{test.setTimeout(guardTimeout+15000);lease=await selectedDiscoveryFixture();fixture=lease.fixture});
test.beforeEach(async({page,context})=>{
 lease.assertHeld();
 lease.onLost(()=>{void context.close()});
 await context.route('**/*',async route=>{
  lease.assertHeld();const request=route.request(),path=new URL(request.url()).pathname;
  if(path.startsWith('/api/v1/')&&!['GET','HEAD','OPTIONS'].includes(request.method())&&!path.endsWith('/search')){
   const target=/^\/api\/v1\/workspaces\/([^/]+)\/(?:favorites\/([^/]+)|recycle\/([^/]+):restore)$/.exec(path);
   expect(Boolean(target),'Only selected-run collection writes are allowed').toBe(true);
   expect(Object.values(fixture.workspaces)).toContain(target![1]);
   expect(Object.values(fixture.records)).toContain(target![2]??target![3]);
  }
  await route.fallback();
 });
 page.on('request',request=>{const url=new URL(request.url());const value=request.headers().authorization;if(url.origin==='http://localhost:18080'&&url.pathname.startsWith('/api/v1/')&&value?.startsWith('Bearer '))bearer.set(page,value)});
});
test.afterEach(async({page},info)=>{
 lease.assertHeld();
 await info.attach('discovery-run-binding.json',{contentType:'application/json',body:JSON.stringify({run_id:fixture.run_id,definition_sha256:fixture.definition_sha256,boundary:fixture.boundary,runtime:fixture.runtime,usage:fixture.usage,status:info.status,claim:'Execution status only; D12 visual review and complete D01-D12 evidence are parent-owned.'},null,2)});
 bearer.delete(page);
});
test.afterAll(async()=>{test.setTimeout(guardTimeout+15000);if(lease)await lease.release()});

async function authenticate(page:Page){
 const me=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/v1/me'&&response.request().method()==='GET');
 await page.getByRole('button',{name:'登录工作区',exact:true}).click();
 // A fresh context presents the form; refresh uses the real existing Keycloak SSO session.
 const step=await Promise.race([page.locator('#username').waitFor({state:'visible'}).then(()=> 'form'),me.then(()=> 'sso')]);
 if(step==='form'){
  await page.locator('#username').fill(fixture.users.author.username);
  await page.locator('#password').fill('eid-local-access');
  await page.locator('#kc-login').click();
 }
 const response=await me;expect(response.status()).toBe(200);
 expect((await response.json()).data.actor_id).toBe(fixture.users.author.actor_id);
 await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
}
async function login(page:Page){
 lease.assertHeld();await page.goto(`/workspaces/${fixture.workspaces.a}/home`);await authenticate(page);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
 await expect(page.getByTestId('discovery-total')).toContainText('当前授权记录');
}
async function nav(page:Page,view:'home'|'documents'|'references'|'favorites'|'recycle'){
 if(view==='home'||view==='documents')await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:view==='home'?'工作台':'项目文档',exact:false}).click();
 else await page.getByRole('complementary',{name:'项目导航'}).getByRole('button',{name:{references:'▣ 参考资料',favorites:'☆ 我的收藏',recycle:'♲ 回收站'}[view],exact:true}).click();
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view',view);
}
async function search(page:Page,query:string){await page.getByLabel('全局搜索').fill(query);await page.getByLabel('全局搜索').press('Enter')}
async function switchProject(page:Page,workspace:string){
 await page.getByRole('button',{name:'账户与会话',exact:true}).click();
 const picker=page.locator('#workspace-picker');await expect(picker).toBeEnabled();
 // New retained fixture runs can push the selected run beyond the first project page.
 for(let n=0;await picker.locator(`option[value="${workspace}"]`).count()===0;n++){
  expect(n,'Bounded project enumeration').toBeLessThan(100);
  const next=page.getByRole('button',{name:'下一页项目',exact:true});await expect(next).toBeEnabled();
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/access/workspaces'&&new URL(r.url()).searchParams.has('after'));
  await next.click();expect((await response).status()).toBe(200);await expect(picker).toBeEnabled();
 }
 await picker.selectOption(workspace);
 await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-context',new RegExp(`:${workspace}:`));
 await expect(page.getByTestId('discovery-total')).toContainText('当前授权记录');
}
async function signOut(page:Page){
 const details=page.locator('details.workspace-runtime');
 if(await details.count()&&(await details.getAttribute('open'))===null)await details.locator('summary').click();
 await page.getByRole('button',{name:'安全退出',exact:true}).click();
 await expect(page.getByTestId('auth-status')).toHaveText('需要登录');
}
async function apiRead<T>(page:Page,path:string):Promise<T>{
 lease.assertHeld();const authorization=bearer.get(page);expect(Boolean(authorization),'Current browser Bearer must have been captured in memory').toBe(true);
 const response=await page.request.get(path,{headers:{Authorization:authorization!},timeout:10000});
 expect(response.status()).toBe(200);return (await response.json()).data as T;
}
async function apiDetail(page:Page,key:string){return apiRead<Detail>(page,`${discovery()}/${fixture.records[key]}`)}
async function listAction(page:Page,action:()=>Promise<unknown>,workspace=fixture.workspaces.a){
 const response=page.waitForResponse(r=>new URL(r.url()).pathname===discovery(workspace)&&new URL(r.url()).searchParams.get('limit')==='20');
 await action();const received=await response;expect(received.status()).toBe(200);
 const data=(await received.json()).data as DiscoveryPage;
 expect(data.context.actor_id).toBe(fixture.users.author.actor_id);expect(data.context.workspace_id).toBe(workspace);
 await expect(page.getByTestId('discovery-total')).toHaveText(new RegExp(`^共 ${data.total_count} 条当前授权记录`));
 await expect.poll(()=>rowIds(page)).toEqual(data.items.map(item=>item.id));return data;
}
async function assertAllPages(page:Page,first:DiscoveryPage,expected:string[]){
 const seen=first.items.map(item=>item.id);expect(first.total_count).toBe(expected.length);
 let next=first.next_cursor;
 for(let n=0;next;n++){
  expect(n).toBeLessThan(10);
  const result=await listAction(page,()=>page.getByRole('button',{name:'下一页记录'}).click());
  expect(result.total_count).toBe(expected.length);seen.push(...result.items.map(item=>item.id));next=result.next_cursor;
 }
 expect(seen).toEqual(expected);expect(new Set(seen).size).toBe(seen.length);
 await expect(page.getByRole('button',{name:'下一页记录'})).toBeDisabled();
}
async function openRecord(page:Page,key:string,expectDetail=true,fromRecycle=key.includes('recycled')){
 const rid=fixture.records[key];expect(rid).toBeTruthy();
 if(fromRecycle){await nav(page,'recycle');await expect(page.locator(`tr[data-record-id="${rid}"]`)).toBeVisible()}
 else {const [workspace,label]=key.split(':');await search(page,`发现验收 ${fixture.run_id} ${workspace} · ${label}`);await expect(page.locator(`tr[data-record-id="${rid}"]`)).toBeVisible()}
 const response=page.waitForResponse(r=>new URL(r.url()).pathname===`${discovery()}/${rid}`);
 await page.locator(`tr[data-record-id="${rid}"] button`).click();const received=await response;
 if(expectDetail){expect(received.status()).toBe(200);await expect(page.getByTestId('discovery-detail')).toContainText(rid)}
 return received;
}
async function capture(page:Page,name:string){await page.screenshot({path:evidencePath(fixture,`${name}.png`),fullPage:true})}

// D02 expected IDs come from the deterministic seed declaration, not the returned count copy.
test('D02 four tabs, AND filters, reference union, pagination and project scope',async({page})=>{
 await login(page);
 await assertAllPages(page,await listAction(page,()=>nav(page,'documents')),ids(normalDocuments()));
 await assertAllPages(page,await listAction(page,()=>page.getByRole('tab',{name:'我创建的',exact:true}).click()),ids(normalDocuments().filter(key=>key!=='a:other-owner')));
 const participating=await listAction(page,()=>page.getByRole('tab',{name:'我参与的',exact:true}).click());expect(participating.items.map(item=>item.id)).toEqual(ids(['a:document','a:other-owner']));expect(participating.total_count).toBe(2);
 await listAction(page,()=>page.getByLabel('文档类型', {exact:true}).selectOption('technical'));
 const intersection=await listAction(page,()=>page.getByLabel('状态',{exact:true}).selectOption('DRAFT'));
 expect(intersection.items.map(item=>item.id)).toEqual(ids(['a:document','a:other-owner']));expect(intersection.total_count).toBe(2);await capture(page,'filtered-collection');
 const none=await listAction(page,()=>page.getByLabel('状态',{exact:true}).selectOption('APPROVED'));expect(none.items).toEqual([]);expect(none.total_count).toBe(0);
 await expect(page.getByLabel('文档类型',{exact:true})).toHaveValue('technical');await expect(page.getByRole('tab',{name:'我参与的',exact:true})).toHaveAttribute('aria-selected','true');
 await listAction(page,()=>page.getByRole('button',{name:'重置筛选',exact:true}).first().click());
 const favorites=await listAction(page,()=>page.getByRole('tab',{name:'我的收藏',exact:true}).click());expect(favorites.total_count).toBe(0);expect(favorites.items).toEqual([]);
 const references=await listAction(page,()=>nav(page,'references'));expect(references.items.map(item=>item.id)).toEqual(ids(['a:knowledge','a:reference']));expect(references.total_count).toBe(2);
 const refIntersection=await listAction(page,()=>page.getByRole('tab',{name:'我参与的',exact:true}).click());expect(refIntersection.items.map(item=>item.id)).toEqual(ids(['a:reference']));
 const knowledge=await listAction(page,()=>page.getByLabel('记录类型',{exact:true}).selectOption('knowledge'));expect(knowledge.total_count).toBe(0);
 await switchProject(page,fixture.workspaces.b);
 const b=await listAction(page,()=>nav(page,'documents'),fixture.workspaces.b);expect(b.items.map(item=>item.id)).toEqual(ids(['b:document']));expect(b.total_count).toBe(1);
});

test('D03 search uses POST body, real metadata identity and Back context; unknown route is rejected',async({page})=>{
 await login(page);
 const searches:Request[]=[];page.on('request',request=>{if(new URL(request.url()).pathname.endsWith('/search'))searches.push(request)});
 await search(page,'   ');expect(searches).toHaveLength(0);await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','home');
 await search(page,'page-00');await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-00']}"]`)).toBeVisible();
 expect(searches.at(-1)?.postDataJSON()).toMatchObject({query:'page-00'});expect(new URL(page.url()).search).toBe('');
 await page.locator(`tr[data-record-id="${fixture.records['a:page-00']}"] button`).click();await expect(page.getByTestId('discovery-detail')).toContainText(fixture.records['a:page-00']);
 await expect(page.getByTestId('discovery-detail')).toContainText('仅有元数据；正文、编辑与版本内容尚未开放。');await capture(page,'metadata-detail');
 await page.getByRole('button',{name:'返回记录列表'}).click();await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','search');await expect(page.getByLabel('全局搜索')).toHaveValue('page-00');
 await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-00']}"]`)).toBeVisible();
 // Negative malformed navigation deliberately uses history in this mounted SPA.
 await page.evaluate(path=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))},`/workspaces/${fixture.workspaces.a}/unknown`);
 await expect(page.getByRole('alert')).toHaveText('项目或资源地址无效');await expect(page.getByTestId('discovery-detail')).toHaveCount(0);
});

type RaceScenario='newer-search'|'project-switch'|'back'|'logout'|'epoch'|'late-failure';
type RaceEvent={sequence:number;at:number;event:string;requestId:string|null;requests:number;fetchState:'missing'|'pending'|'resolved'|'rejected';signalPresent:boolean;aborted:boolean|null};
type RaceProbeOptions={scenario:RaceScenario;workspace:string;targetWorkspace:string;binding:string};

// Runs in the application document. All ordering is from this browser realm,
// before React's handlers, never from Node's later route callback or wall clock.
function observeDiscoveryRace({scenario,workspace,targetWorkspace,binding}:RaceProbeOptions){
 const nativeFetch=window.fetch.bind(window);
 let sequence=0,requests=0;
 let held:{requestId:string|null;state:'pending'|'resolved'|'rejected';signal:AbortSignal|null}|undefined;
 const record=(event:string)=>{
  const snapshot:RaceEvent=Object.freeze({sequence:++sequence,at:performance.now(),event,requestId:held?.requestId??null,requests,fetchState:held?.state??'missing',signalPresent:Boolean(held?.signal),aborted:held?.signal?.aborted??null});
  // The binding sends the immutable snapshot to Node synchronously, before a
  // logout handler can destroy this document. A missing delivery fails the test.
  void (Reflect.get(window,binding) as (value:RaceEvent)=>Promise<void>)(snapshot);
 };
 window.fetch=async(input,init)=>{
  const request=input instanceof Request?input:undefined;
  const url=new URL(request?.url??String(input),location.href);
  const sameOrigin=url.origin===location.origin;
  const method=init?.method??request?.method??'GET';
  let isA=false;
  if(sameOrigin&&url.pathname===`/api/v1/workspaces/${workspace}/search`&&method==='POST'&&typeof init?.body==='string')isA=JSON.parse(init.body).query==='page-00';
  if(isA){
   requests++;held={requestId:new Headers(init?.headers??request?.headers).get('X-Request-ID'),state:'pending',signal:init?.signal??request?.signal??null};
   held.signal?.addEventListener('abort',()=>record('A-aborted'),{once:true});record('A-started');
  }
  try{
   const response=await nativeFetch(input,init);
   if(isA){held!.state='resolved';record('A-resolved')}
   if(scenario==='epoch'&&sameOrigin&&url.pathname===`/api/v1/access/workspaces/${workspace}`&&response.body){
    // boundedJson consumes the real reader. Observe its final chunk before the
    // account payload returns to the application, without cloning/changing it.
    const body=response.body,getReader=body.getReader.bind(body);
    body.getReader=(()=>{
     const reader=getReader(),read=reader.read.bind(reader);
     reader.read=async()=>{const chunk=await read();if(chunk.done&&held)record('epoch-body-delivered');return chunk};
     return reader;
    }) as typeof body.getReader;
   }
   return response;
  }catch(error){if(isA){held!.state='rejected';record('A-rejected')}throw error}
 };
 window.addEventListener('keydown',event=>{
  if((scenario==='newer-search'||scenario==='late-failure')&&event.key==='Enter'&&event.target instanceof HTMLInputElement&&event.target.id==='globalSearch'&&event.target.value==='page-01')record('search-enter');
 },true);
 window.addEventListener('click',event=>{
  const button=event.target instanceof Element?event.target.closest('button'):null;
  if(scenario==='project-switch'&&button?.getAttribute('aria-label')==='账户与会话')record('project-account-click');
  if(scenario==='logout'&&button?.textContent?.trim()==='安全退出')record('logout-click');
 },true);
 window.addEventListener('change',event=>{
  if(scenario==='project-switch'&&event.target instanceof HTMLSelectElement&&event.target.id==='workspace-picker'&&event.target.value===targetWorkspace)record('project-selected');
 },true);
 window.addEventListener('popstate',()=>{if(scenario==='back'&&location.pathname===`/workspaces/${workspace}/documents`)record('back-popstate')},true);
}
async function raceProbe(page:Page,scenario:RaceScenario){
 const events:RaceEvent[]=[],binding=`discoveryRace_${randomUUID().replaceAll('-','')}`;
 await page.exposeBinding(binding,({frame},event:RaceEvent)=>{expect(frame).toBe(page.mainFrame());events.push(Object.freeze(event))});
 await page.evaluate(observeDiscoveryRace,{scenario,workspace:fixture.workspaces.a,targetWorkspace:fixture.workspaces.b,binding});
 const transitionName={ 'newer-search':'search-enter','late-failure':'search-enter','project-switch':'project-account-click',back:'back-popstate',logout:'logout-click',epoch:'epoch-body-delivered'}[scenario];
 return {events,assertTransition:async(request:Request)=>{
  await expect.poll(()=>events.filter(event=>event.event===transitionName).length,'Exactly one actual browser transition must be observed').toBe(1);
  const transition=events.find(event=>event.event===transitionName)!;
  expect(transition,'A must still be pending at the actual transition event').toMatchObject({requests:1,requestId:request.headers()['x-request-id'],fetchState:'pending',signalPresent:true,aborted:false});
  const started=events.find(event=>event.event==='A-started');expect(started).toBeTruthy();expect(started!.sequence).toBeLessThan(transition.sequence);expect(started!.at).toBeLessThanOrEqual(transition.at);
  expect(events.filter(event=>['A-aborted','A-resolved','A-rejected'].includes(event.event)&&event.sequence<transition.sequence),'No A terminal/abort may precede the actual transition').toEqual([]);
  if(scenario==='project-switch'){
   await expect.poll(()=>events.filter(event=>event.event==='project-selected').length).toBe(1);
   expect(events.find(event=>event.event==='project-selected')!.sequence).toBeGreaterThan(transition.sequence);
  }
  return transition;
 }};
}

async function delayedSearch(page:Page,lateFailure=false){
 const captured=deferred<Request>(),release=deferred<void>(),completed=deferred<void>(),terminal=deferred<string>();
 let heldRequest:Request|undefined;
 const terminalListener=(request:Request)=>{if(request===heldRequest){const failure=request.failure();terminal.resolve(failure?(failure.errorText==='net::ERR_ABORTED'?'cancelled':'failed'):'finished')}};
 page.on('requestfinished',terminalListener);page.on('requestfailed',terminalListener);
 const handler=async(route:Route)=>{
  if(route.request().postDataJSON().query!=='page-00'){await route.fallback();return}
  try{
   heldRequest=route.request();const actual=await route.fetch({timeout:6000});expect(actual.status()).toBe(200);
   const body=(await actual.json()).data as DiscoveryPage;expect(body.items.map(item=>item.id)).toEqual([fixture.records['a:page-00']]);
   captured.resolve(heldRequest);await release.promise;lease.assertHeld();
   try{if(lateFailure)await route.fulfill({status:503,json:{error:{code:'POLICY_UNAVAILABLE'}}});else await route.fulfill({response:actual})}
   catch(error){if(heldRequest.failure()?.errorText!=='net::ERR_ABORTED')throw error}
   completed.resolve();
  }catch(error){captured.reject(error);completed.reject(error)}
 };
 await page.route(`**/api/v1/workspaces/${fixture.workspaces.a}/search`,handler);
 return {captured:captured.promise,finish:async()=>{
  release.resolve();await completed.promise;const result=await terminal.promise;
  page.off('requestfinished',terminalListener);page.off('requestfailed',terminalListener);await page.unroute(`**/api/v1/workspaces/${fixture.workspaces.a}/search`,handler);return result;
 }};
}
for(const scenario of ['newer-search','project-switch','back','logout','epoch','late-failure'] as const){
 test(`D05 controlled response delay: ${scenario} rejects stale A after current context wins`,async({page})=>{
  await login(page);await nav(page,'documents');
  if(scenario==='epoch'){
   // Start the held poll on the final route: navigating from documents to
   // search would supersede that poll with a second account-load generation.
   const account=page.waitForResponse(response=>new URL(response.url()).pathname===`/api/v1/access/workspaces/${fixture.workspaces.a}`);
   await search(page,'page-02');expect((await account).status()).toBe(200);
   await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-02']}"]`)).toBeVisible();
   await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
  }
  const mounted=randomUUID();await page.evaluate(value=>{Object.assign(window,{discoveryDocumentMarker:value})},mounted);
  const probe=await raceProbe(page,scenario);
  const epochGate=deferred<void>(),epochArrived=deferred<void>();
  const previous=await page.getByTestId('discovery-root').getAttribute('data-context');
  if(scenario==='epoch'){
   // Hold the real periodic account response first, so A is still pending
   // when the explicit negative epoch transition arrives (A's deadline is 8 s).
   await page.route(`**/api/v1/access/workspaces/${fixture.workspaces.a}`,async route=>{
    const response=await route.fetch({timeout:10000});expect(response.status()).toBe(200);const body=await response.json();
    epochArrived.resolve();await epochGate.promise;
    body.data.policy_epoch=body.data.policy_epoch.map((n:number)=>n+1);await route.fulfill({response,json:body});
   });
   await epochArrived.promise;
  }
  const held=await delayedSearch(page,scenario==='late-failure');await search(page,'page-00');const request=await held.captured;
  if(scenario==='newer-search'||scenario==='late-failure'){
   await search(page,'page-01');await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-01']}"]`)).toBeVisible();
  }else if(scenario==='project-switch')await switchProject(page,fixture.workspaces.b);
  else if(scenario==='back'){
   const documents=await listAction(page,()=>page.goBack()),expected=ids(normalDocuments());
   expect(documents.items.map(item=>item.id)).toEqual(expected.slice(0,20));expect(documents.total_count).toBe(expected.length);
   await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','documents');await expect(page).toHaveURL(new RegExp('/documents$'));
  }
  else if(scenario==='logout')await signOut(page);
  else {
   // Negative epoch transition only: current account endpoint reports a new context.
   // No real policy mutation and no fabricated discovery business success.
   epochGate.resolve();
   await expect(page.getByTestId('discovery-root')).not.toHaveAttribute('data-context',previous!,{timeout:22000});
   await expect(page.getByLabel('全局搜索')).toHaveValue('');
  }
  const transition=await probe.assertTransition(request);
  const terminal=await held.finish();expect(['finished','cancelled']).toContain(terminal);
  if(terminal==='cancelled'){
   await expect.poll(()=>probe.events.filter(event=>event.event==='A-aborted').length).toBe(1);
   expect(probe.events.find(event=>event.event==='A-aborted')!.sequence).toBeGreaterThan(transition.sequence);
  }
  if(scenario!=='logout')expect(await page.evaluate(()=>Reflect.get(window,'discoveryDocumentMarker'))).toBe(mounted);
  if(scenario==='newer-search'||scenario==='late-failure'){
   await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-01']}"]`)).toBeVisible();await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-00']}"]`)).toHaveCount(0);await expect(page.getByTestId('discovery-state')).toHaveCount(0);
  }else if(scenario==='project-switch'){await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-context',new RegExp(`:${fixture.workspaces.b}:`));await expect(page.locator(`tr[data-record-id="${fixture.records['a:page-00']}"]`)).toHaveCount(0)}
  else if(scenario==='back'){
   const expected=ids(normalDocuments());
   await expect(page.getByTestId('discovery-root')).toHaveAttribute('data-view','documents');await expect(page).toHaveURL(new RegExp('/documents$'));
   await expect.poll(()=>rowIds(page)).toEqual(expected.slice(0,20));await expect(page.getByTestId('discovery-total')).toHaveText(`共 ${expected.length} 条当前授权记录 · 不含回收站记录`);
   await expect(page.getByTestId('discovery-state')).toHaveCount(0);await expect(page.getByRole('alert')).toHaveCount(0);
  }
  else {await expect(page.getByTestId('discovery-table')).toHaveCount(0);await expect(page.getByTestId('discovery-detail')).toHaveCount(0);await expect(page.getByTestId('discovery-command')).toHaveCount(0)}
  await test.info().attach(`D05-${scenario}.json`,{contentType:'application/json',body:JSON.stringify({scenario,transition,browser_events:probe.events,A_terminal:terminal,project_switch_boundary:scenario==='project-switch'?'A pending at account navigation; picker change follows discovery unmount/cancellation':undefined,negative_injection:scenario==='epoch'||scenario==='late-failure'})});
 });
}

for(const state of ['loading','empty','empty-filtered','unavailable','timeout','offline','authentication','workspace-forbidden','resource-forbidden'] as const){
 test(`D06 ${state}: persistent distinct state and explicit recovery (faults labelled)`,async({page,context})=>{
  await login(page);let release:(()=>void)|undefined;
  if(state==='empty'){
   // Original access projects contain unregistered policy resources, no discovery rows.
   // Read only; the request guard forbids collection writes outside this new run.
   const empty=fixture.accessWorkspaces[0];expect(empty).toBeTruthy();
   const actual=await apiRead<DiscoveryPage>(page,`${discovery(empty)}?kind=document&limit=20`);expect(actual.total_count).toBe(0);expect(actual.items).toEqual([]);
   await switchProject(page,empty);await nav(page,'documents');await expect(page.getByTestId('discovery-state')).toHaveAttribute('data-state','empty');
  }
  else if(state==='empty-filtered'){await nav(page,'documents');await listAction(page,()=>page.getByLabel('文档类型',{exact:true}).selectOption('proposal'));await expect(page.getByTestId('discovery-state')).toHaveAttribute('data-state','empty-filtered');await expect(page.getByLabel('文档类型',{exact:true})).toHaveValue('proposal')}
  else if(state==='offline'){await nav(page,'documents');await context.setOffline(true);expect(await page.evaluate(()=>navigator.onLine)).toBe(false);await expect(page.getByTestId('discovery-state')).toHaveAttribute('data-state','offline');await expect(page.getByTestId('discovery-table')).toHaveCount(0);await capture(page,'offline-error');await context.setOffline(false);await nav(page,'home');await nav(page,'documents');await expect(page.getByTestId('discovery-table')).toBeVisible()}
  else if(state==='resource-forbidden'){
   await page.route(`**${discovery()}/${fixture.records['a:document']}`,route=>route.fulfill({status:403,json:{error:{code:'FORBIDDEN'}}}));
   const denied=await openRecord(page,'a:document',false);expect(denied.status()).toBe(403);await expect(page.getByTestId('discovery-state')).toHaveAttribute('data-state','forbidden');await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');await expect(page.getByTestId('discovery-detail')).toHaveCount(0);await capture(page,'resource-denial');
  }else{
   const arrived=deferred<void>(),gate=deferred<void>();release=()=>gate.resolve();
   await page.route(url=>url.pathname===discovery()&&url.searchParams.get('limit')==='20',async route=>{
    arrived.resolve();
    if(state==='loading'||state==='timeout'){await gate.promise;try{await route.abort('failed')}catch(error){if(!route.request().failure())throw error}}
    else await route.fulfill({status:state==='authentication'?401:state==='workspace-forbidden'?403:503,json:{error:{code:state==='authentication'?'AUTHENTICATION':state==='workspace-forbidden'?'WORKSPACE_FORBIDDEN':'POLICY_UNAVAILABLE'}}});
   });
   // A fatal denial can remove discovery-root before a view locator is observed.
   await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name:'项目文档',exact:false}).click();await arrived.promise;
   if(state==='authentication'){await expect(page.getByTestId('auth-status')).toHaveText('认证失败');await expect(page.getByRole('button',{name:'登录工作区',exact:true})).toBeVisible();await expect(page.getByTestId('discovery-root')).toHaveCount(0)}
   else if(state==='workspace-forbidden'){await expect(page.getByTestId('auth-status')).toHaveText('工作区访问被拒绝');await expect(page.getByTestId('discovery-root')).toHaveCount(0)}
   else {await expect(page.getByTestId('discovery-state')).toHaveAttribute('data-state',state,{timeout:12000});await expect(page.getByTestId('discovery-table')).toHaveCount(0)}
   await capture(page,`read-${state}`);release();await page.unrouteAll({behavior:'wait'});
   if(state==='authentication'){await authenticate(page);if(!page.url().includes(fixture.workspaces.a))await switchProject(page,fixture.workspaces.a);await expect(page.getByTestId('discovery-table')).toBeVisible()}
   else if(state!=='workspace-forbidden'){await page.getByRole('button',{name:'重新读取',exact:true}).click();await expect(page.getByTestId('discovery-table')).toBeVisible()}
  }
  await test.info().attach(`D06-${state}.json`,{contentType:'application/json',body:JSON.stringify({state,source:['empty','empty-filtered'].includes(state)?'actual newly seeded API collection':state==='offline'?'browser network offline':'explicit negative transport/context injection',no_business_success_mock:true})});
 });
}

async function confirmCommand(page:Page,action:string){lease.assertHeld();await page.getByTestId('discovery-detail').getByRole('button',{name:action,exact:true}).click();await expect(page.getByTestId('discovery-command')).toHaveAttribute('data-state','confirm');await page.getByRole('button',{name:'确认操作',exact:true}).click()}
async function refreshAndReauthenticate(page:Page){
 await page.reload();await expect(page.getByTestId('auth-status')).toHaveText('需要登录');await authenticate(page);
 if(!page.url().includes(fixture.workspaces.a))await switchProject(page,fixture.workspaces.a);
}

test('D07 real favorite commit, PKCE refresh, and lost response replay retain identical key/body',async({page})=>{
 await login(page);const initialFavorites=await listAction(page,()=>nav(page,'favorites'));expect(initialFavorites).toMatchObject({total_count:0,items:[]});await openRecord(page,'a:document');const initial=await apiDetail(page,'a:document');expect(initial.item.favorite).toBe(false);expect(initial.item.favorite_revision).toBe(0);
 const path=`/api/v1/workspaces/${fixture.workspaces.a}/favorites/${fixture.records['a:document']}`;
 const acknowledged=page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='PUT');
 await confirmCommand(page,'添加收藏');const response=await acknowledged;expect(response.status()).toBe(200);const receipt=(await response.json()).data as Receipt;
 expect(receipt).toMatchObject({action:'favorite.set',resource_id:initial.item.id,replayed:false,current:{favorite:true,favorite_revision:1}});expect(receipt.operation_id).toMatch(/^[0-9a-f-]{36}$/);
 await expect(feedback(page)).toContainText(receipt.operation_id);expect((await apiDetail(page,'a:document')).item.favorite).toBe(true);
 const expectedFavorite=[fixture.records['a:document']];
 const sideFavorites=await listAction(page,()=>nav(page,'favorites'));expect(sideFavorites.items.map(item=>item.id)).toEqual(expectedFavorite);expect(sideFavorites.total_count).toBe(1);
 const documents=await listAction(page,()=>nav(page,'documents'));const favoriteTab=await listAction(page,()=>page.getByRole('tab',{name:'我的收藏',exact:true}).click());expect(favoriteTab.items.map(item=>item.id)).toEqual(expectedFavorite);expect(favoriteTab.total_count).toBe(1);expect(documents.total_count).toBeGreaterThan(0);await capture(page,'favorite-confirmed');
 await refreshAndReauthenticate(page);await openRecord(page,'a:document');await expect(page.getByTestId('discovery-detail').getByRole('button',{name:'取消收藏',exact:true})).toBeEnabled();
 const commands:{key:string;body:unknown;receipt:Receipt}[]=[];const first=deferred<void>(),second=deferred<void>();
 await page.route(`**${path}`,async route=>{
  lease.assertHeld();const key=route.request().headers()['idempotency-key'];expect(key).toMatch(/^[0-9a-f-]{36}$/);
  const body=route.request().postDataJSON();const actual=await route.fetch({timeout:10000});expect(actual.status()).toBe(200);const current=(await actual.json()).data as Receipt;
  commands.push({key,body,receipt:current});
  if(commands.length===1){expect(current.replayed).toBe(false);await route.abort('failed');first.resolve()}
  else {expect(commands).toHaveLength(2);await route.fulfill({response:actual});second.resolve()}
 });
 await confirmCommand(page,'取消收藏');await first.promise;await expect(page.getByTestId('discovery-command')).toHaveAttribute('data-state','unknown');
 // The server really committed before its response was hidden from the application.
 const committed=await apiDetail(page,'a:document');expect(committed.item).toMatchObject({favorite:false,favorite_revision:2});
 await page.getByRole('button',{name:'核对原操作',exact:true}).click();await second.promise;
 expect(commands).toHaveLength(2);expect(commands[1].key).toBe(commands[0].key);expect(commands[1].body).toEqual(commands[0].body);expect(commands[0].body).toEqual({favorite:false,expected_revision:1});
 expect(commands[1].receipt).toMatchObject({operation_id:commands[0].receipt.operation_id,replayed:true,current:{favorite:false,favorite_revision:2}});
 await expect(feedback(page)).toContainText('已核对原操作');await expect(page.getByTestId('discovery-detail').getByRole('button',{name:'添加收藏',exact:true})).toBeEnabled();
 expect((await apiDetail(page,'a:document')).item).toEqual(committed.item);
 const removedSideFavorites=await listAction(page,()=>nav(page,'favorites'));expect(removedSideFavorites).toMatchObject({total_count:0,items:[]});
 await listAction(page,()=>nav(page,'documents'));const removedTabFavorites=await listAction(page,()=>page.getByRole('tab',{name:'我的收藏',exact:true}).click());expect(removedTabFavorites).toMatchObject({total_count:0,items:[]});
 await test.info().attach('D07-receipts.json',{contentType:'application/json',body:JSON.stringify({first:receipt,unknown_outcome:commands},null,2)});
});

function immutableItem(item:Item){const copy={...item} as Partial<Item>;delete copy.visibility;delete copy.revision;delete copy.updated_at;return copy}
test('D08 real UI restore preserves ARCHIVED metadata and denies wrong owner/type over real HTTP',async({page})=>{
 await login(page);const before=await apiDetail(page,'a:recycled');expect(before.item).toMatchObject({visibility:'recycled',revision:1,lifecycle:'ARCHIVED'});expect(before.actions.restore).toBe(true);
 const originalAccess=await apiRead<Record<string,unknown>>(page,`/api/v1/access/workspaces/${fixture.workspaces.a}/resources/${before.item.id}`);
 await openRecord(page,'a:recycled');const path=`/api/v1/workspaces/${fixture.workspaces.a}/recycle/${before.item.id}:restore`;
 const response=page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='POST');await confirmCommand(page,'恢复列表可见性');const received=await response;expect(received.status()).toBe(200);const receipt=(await received.json()).data as Receipt;
 expect(receipt).toMatchObject({action:'restore_visibility',resource_id:before.item.id,replayed:false,current:{visibility:'visible',revision:2,lifecycle:'ARCHIVED'}});await expect(feedback(page)).toContainText(receipt.operation_id);
 const after=await apiDetail(page,'a:recycled');expect(after.item).toMatchObject({visibility:'visible',revision:2,lifecycle:'ARCHIVED'});expect(immutableItem(after.item)).toEqual(immutableItem(before.item));expect(after.actions.restore).toBe(false);
 expect(await apiRead(page,`/api/v1/access/workspaces/${fixture.workspaces.a}/resources/${before.item.id}`)).toEqual(originalAccess);await capture(page,'restore-confirmed');
 const recycle=await apiRead<DiscoveryPage>(page,`${discovery()}?visibility=recycled&limit=50`);expect(recycle.items.map(item=>item.id)).not.toContain(before.item.id);
 const visible=await apiRead<DiscoveryPage>(page,`${discovery()}?visibility=visible&kind=document&limit=50`);expect(visible.items.map(item=>item.id)).toContain(before.item.id);
 await refreshAndReauthenticate(page);await openRecord(page,'a:recycled',true,false);
 await expect(page.getByTestId('discovery-detail')).toContainText('已归档（只读）');
 await expect(page.getByTestId('discovery-detail').getByRole('button',{name:'恢复列表可见性'})).toHaveCount(0);
 const denials=[];
 for(const key of ['a:recycled-other-owner','a:recycled-knowledge']){
  const unchanged=await apiDetail(page,key);expect(unchanged.actions.restore).toBe(false);
  await openRecord(page,key);await expect(page.getByRole('button',{name:'恢复列表可见性',exact:true})).toBeDisabled();
  lease.assertHeld();const authorization=bearer.get(page);expect(Boolean(authorization)).toBe(true);
  const response=await page.request.post(`/api/v1/workspaces/${fixture.workspaces.a}/recycle/${fixture.records[key]}:restore`,{headers:{Authorization:authorization!,'Idempotency-Key':randomUUID()},data:{expected_revision:unchanged.item.revision,policy_version:fixture.policy_version},timeout:10000});
  expect(response.status()).toBe(403);expect((await apiDetail(page,key)).item).toEqual(unchanged.item);denials.push({key,status:response.status()});
 }
 await capture(page,'restore-denial');
 await test.info().attach('D08-receipt-and-denials.json',{contentType:'application/json',body:JSON.stringify({before,after,receipt,denials,coverage_boundary:'Missing/production/expired policy and full DB immutability are separately owned by real PostgreSQL tests; this browser run does not alter policies.'},null,2)});
});

test('D10 truthful home regions, actual todo and reference collections',async({page})=>{
 await login(page);const summary=await apiRead<Summary>(page,`${discovery()}/summary`);
 await expect(page.getByTestId('discovery-kpis').locator('.kpi')).toHaveCount(4);
 await expect(page.getByTestId('discovery-home-cards').locator('.mini-card')).toHaveCount(4);await expect(page.getByRole('tab')).toHaveCount(4);
 for(const panel of summary.future_panels){expect(panel.value).toBeNull();expect(panel.reason.length).toBeGreaterThan(0);expect(panel.owner.length).toBeGreaterThan(0)}
 await expect(page.getByTestId('discovery-kpis')).toContainText('未采集');await expect(page.getByTestId('discovery-kpis')).toContainText('未评估');
 await expect(page.getByTestId('discovery-storage')).toContainText('数据库持久元数据与标题的实际字节');
 await expect(page.getByTestId('discovery-kpis').locator('.kpi').first().locator('strong')).toHaveText(String(summary.week_new_documents.value));await capture(page,'homepage');
 const todo=await listAction(page,()=>page.getByTestId('discovery-home-cards').getByRole('button',{name:'更多 ›',exact:true}).first().click());
 const expected=['a:document',...Array.from({length:32},(_,i)=>`a:page-${String(i).padStart(2,'0')}`).filter(key=>!['a:page-01','a:page-02'].includes(key))];
 await assertAllPages(page,todo,ids(expected));await expect(page).toHaveURL(/collection=todo/);
 const references=await listAction(page,()=>nav(page,'references'));expect(references.items.map(item=>item.id)).toEqual(ids(['a:knowledge','a:reference']));
});

type Timing={label:string;started_at:string;finished_at:string;duration_ms:number;outcome:'completed'|'error'};
function percentile(values:number[],fraction:number){const sorted=[...values].sort((a,b)=>a-b);return sorted.length?sorted[Math.ceil(sorted.length*fraction)-1]:null}
test('D12 actual completed UI/API timing windows, fonts, screenshots and keyboard operation',async({page,browser})=>{
 test.setTimeout(150000);await login(page);const samples:Timing[]=[];
 const measure=async(label:string,action:()=>Promise<unknown>)=>{
  const started_at=new Date().toISOString(),start=performance.now();let outcome:Timing['outcome']='error';
  try{await action();outcome='completed'}finally{samples.push({label,started_at,finished_at:new Date().toISOString(),duration_ms:performance.now()-start,outcome})}
 };
 try{
  for(let n=0;n<3;n++){
   await measure('list-ui',()=>listAction(page,()=>nav(page,'documents')));
   await measure('tab-ui',()=>listAction(page,()=>page.getByRole('tab',{name:'我参与的',exact:true}).click()));
   await measure('home-ui',async()=>{
    const response=page.waitForResponse(r=>new URL(r.url()).pathname===`${discovery()}/summary`);
    await nav(page,'home');expect((await response).status()).toBe(200);
    await expect(page.getByTestId('discovery-total')).toContainText('当前授权记录');
    await expect(page.locator('[data-testid="discovery-state"][data-state="loading"]')).toHaveCount(0);
    await expect(page.getByTestId('discovery-kpis').locator('.kpi').first().locator('strong')).not.toHaveText('—');
   });
   await measure('home-summary-api',()=>apiRead<Summary>(page,`${discovery()}/summary`));
   await measure('list-api',()=>apiRead<DiscoveryPage>(page,`${discovery()}?kind=document&limit=20`));
  }
  await capture(page,'D12-home');await nav(page,'documents');
  await page.getByRole('tab',{name:'最近文档',exact:true}).focus();await page.keyboard.press('End');await expect(page.getByRole('tab',{name:'我的收藏',exact:true})).toBeFocused();await expect(page.getByRole('tab',{name:'我的收藏',exact:true})).toHaveAttribute('aria-selected','true');
  await page.keyboard.press('Home');await expect(page.getByRole('tab',{name:'最近文档',exact:true})).toBeFocused();await expect(page.getByTestId('discovery-table')).toBeVisible();
  const row=page.getByTestId('discovery-table').locator('tbody tr').first();const id=await row.getAttribute('data-record-id');await row.getByRole('button').focus();await page.keyboard.press('Enter');await expect(page.getByTestId('discovery-detail')).toContainText(id!);await capture(page,'D12-keyboard-detail');
 }finally{
  const fonts=await page.evaluate(async()=>{await document.fonts.ready;return {userAgent:navigator.userAgent,devicePixelRatio,body:getComputedStyle(document.body).fontFamily,heading:getComputedStyle(document.querySelector('h1,h2')??document.body).fontFamily,fontStatus:document.fonts.status,loadedFaces:Array.from(document.fonts).map(font=>({family:font.family,status:font.status,weight:font.weight}))}});
  const labels=[...new Set(samples.map(sample=>sample.label))];const summary=labels.map(label=>{const values=samples.filter(sample=>sample.label===label);return {label,sample_count:values.length,errors:values.filter(sample=>sample.outcome==='error').length,p50_ms:percentile(values.map(sample=>sample.duration_ms),.5),p95_ms:percentile(values.map(sample=>sample.duration_ms),.95)}});
  await test.info().attach('D12-development-baseline.json',{contentType:'application/json',body:JSON.stringify({run_id:fixture.run_id,definition_sha256:fixture.definition_sha256,runtime:fixture.runtime,boundary:fixture.boundary,browser:browser.version(),channel:'chrome',viewport:page.viewportSize(),fonts,samples,summary,percentile_definition:'nearest rank ceil(p*n), includes every terminal attempt including errors',claim:'Development baseline only. B/R/S visual assessment requires parent review of the screenshots; not production NFR or Story completion.'},null,2)});
 }
});
