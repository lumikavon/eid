import {afterAll,beforeAll,expect,test} from 'vitest';
import {chromium,type Browser,type Page} from '@playwright/test';
import {build} from 'vite';
import react from '@vitejs/plugin-react';
import type {} from './App.session.interaction-harness';

let browser:Browser;
let bundle:string;

beforeAll(async()=>{
 const root=decodeURIComponent(new URL('../../',import.meta.url).pathname).replace(/^\/(?=[A-Za-z]:\/)/,'');
 const built=await build({configFile:false,root,logLevel:'error',define:{'process.env.NODE_ENV':'"test"'},plugins:[react(),{
  name:'app-session-local-observation',enforce:'pre',
  resolveId(source,importer){
   if(source.endsWith('/auth/oidc'))return '\0session-test-oidc';
   if(importer?.endsWith('/src/app/App.tsx')){
    if(source==='./api')return '\0session-test-account-observer';
    if(source==='./access-api')return '\0session-test-workspace-observer';
   }
  },
  load(id){
   // Explicit test double: clear the memory token without replacing the document.
   // This isolates App's late callback handling; it is not OIDC acceptance evidence.
   if(id==='\0session-test-oidc')return 'let value="session-test-token";export const token=()=>value;export const clearSession=()=>{value=null};export const logout=clearSession;export const beginLogin=async()=>{};export const finishLogin=async()=>"/";';
   const stage=id==='\0session-test-account-observer'?'account':id==='\0session-test-workspace-observer'?'workspace':null;
   if(stage){
    const path=JSON.stringify(`${root}src/app/${stage==='account'?'api':'access-api'}.ts`);
    const name=stage==='account'?'getMe':'getWorkspace';
    // Delegate to the actual read client, observing fulfillment/rejection after
    // response parsing. No App guard or state update is replaced by this wrapper.
    return `export * from ${path};import {${name} as read} from ${path};export async function ${name}(...args){try{const value=await read(...args);window.appSessionTest.observeRead("${stage}","success");return value}catch(error){window.appSessionTest.observeRead("${stage}","failure");throw error}}`;
   }
  },
 }],build:{write:false,minify:false,lib:{entry:`${root}src/app/App.session.interaction-harness.tsx`,formats:['iife'],name:'AppSessionInteraction'}}});
 const output=Array.isArray(built)?built[0]:built;
 if(!('output' in output))throw new Error('Expected an in-memory browser bundle');
 bundle=output.output.filter(output=>output.type==='chunk').map(output=>output.code).join('\n');
 browser=await chromium.launch({headless:true,proxy:{server:'http://127.0.0.1:9'},args:['--proxy-bypass-list=<-loopback>','--disable-background-networking']});
},30_000);
afterAll(async()=>{await browser?.close()});

async function mount(){
 const page=await browser.newPage({serviceWorkers:'block'});page.setDefaultTimeout(3_000);
 const unexpected:string[]=[];const pageErrors:string[]=[];
 page.on('pageerror',error=>pageErrors.push(error.message));
 await page.route('**/*',route=>{
  if(route.request().isNavigationRequest()&&route.request().url()==='https://app-session.invalid/')return route.fulfill({contentType:'text/html',body:'<!doctype html><div id="root"></div>'});
  unexpected.push(route.request().url());return route.abort();
 });
 await page.goto('https://app-session.invalid/');
 await page.clock.install();
 await page.addScriptTag({content:bundle});
 await page.evaluate(()=>window.appSessionTest.mount());
 await page.getByRole('button',{name:'退出后不可恢复的记录',exact:true}).waitFor();
 await page.getByText('账户与运行状态',{exact:true}).click();
 expect(await page.getByTestId('auth-status').textContent()).toBe('已安全登录');
 expect(await page.locator('.uinfo b').textContent()).toBe('迟到回调测试作者');
 expect(await page.locator('.project-card-copy b').textContent()).toBe('迟到回调测试项目');
 await page.clock.pauseAt(await page.evaluate(()=>Date.now()+1000));
 return {page,unexpected,pageErrors};
}

async function expectCleared(page:Page){
 expect(await page.getByTestId('auth-status').textContent()).toBe('正在安全退出');
 expect(await page.locator('.uinfo b').textContent()).toBe('未登录');
 expect(await page.locator('.project-card-copy b').textContent()).toBe('等待身份映射');
 expect(await page.getByRole('textbox',{name:'全局搜索',exact:true}).isDisabled()).toBe(true);
 expect(await page.getByRole('button',{name:'登录工作区',exact:true}).isVisible()).toBe(true);
 expect(await page.getByRole('button',{name:'安全退出',exact:true}).count()).toBe(0);
 for(const id of ['discovery-root','discovery-total','discovery-table','discovery-storage'])expect(await page.getByTestId(id).count()).toBe(0);
 expect(await page.getByRole('alert').count()).toBe(0);
 expect(await page.evaluate(()=>window.appSessionTest.snapshot())).toMatchObject({hasToken:false,controlledQueries:0,unexpected:[]});
}

test.each([
 {stage:'account',outcome:'success'},
 {stage:'workspace',outcome:'success'},
 {stage:'account',outcome:'failure'},
] as const)('logout suppresses a confirmed late $stage $outcome in the same document',async({stage,outcome})=>{
 const {page,unexpected,pageErrors}=await mount();
 try{
  const initial=await page.evaluate(()=>window.appSessionTest.snapshot());
  await page.evaluate(({stage,outcome})=>window.appSessionTest.arm(stage,outcome),{stage,outcome});
  await page.clock.fastForward(15000);
  // Confirm a real read-client call is waiting, not merely scheduled, before logout.
  await page.waitForFunction(()=>window.appSessionTest.snapshot().held?.requested,{},{polling:10});
  const pending=await page.evaluate(()=>window.appSessionTest.snapshot());
  expect(pending.held).toEqual({stage,outcome,requested:true,released:false,responseReturned:false});
  expect(pending.requests.filter(request=>request.path==='/api/v1/me')).toHaveLength(2);
  expect(pending.requests.filter(request=>request.bearer!==null).every(request=>request.bearer==='Bearer session-test-token')).toBe(true);
  expect(await page.getByTestId('auth-status').textContent()).toBe('正在载入当前账户');
  await page.getByRole('button',{name:'安全退出',exact:true}).click();
  await expectCleared(page);
  expect((await page.evaluate(()=>window.appSessionTest.snapshot())).held?.responseReturned).toBe(false);
  await page.evaluate(()=>window.appSessionTest.release());
  await page.clock.resume();
  // The observer runs after the actual getMe/getWorkspace read and parser settle.
  await page.waitForFunction(count=>window.appSessionTest.snapshot().settled.length>=count,pending.settled.length+1);
  await page.evaluate(()=>window.appSessionTest.flushCallbacks());
  const completed=await page.evaluate(()=>window.appSessionTest.snapshot());
  expect(completed.held).toEqual({stage,outcome,requested:true,released:true,responseReturned:true});
  expect(completed.settled.slice(pending.settled.length)).toEqual([{stage,outcome}]);
  expect(completed.documentId).toBe(initial.documentId);
  expect(completed.requests).toEqual(pending.requests);
  await expectCleared(page);
  expect(unexpected).toEqual([]);expect(pageErrors).toEqual([]);
 }finally{
  await page.evaluate(()=>window.appSessionTest.release()).catch(()=>{});
  await page.close();
 }
});
