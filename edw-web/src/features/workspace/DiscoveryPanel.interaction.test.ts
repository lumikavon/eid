import {afterAll,beforeAll,expect,test} from 'vitest';
import {chromium,type Browser,type Page} from '@playwright/test';
import {build} from 'vite';
import react from '@vitejs/plugin-react';
import type {} from './DiscoveryPanel.interaction-harness';

const wid='00000000-0000-4000-8000-000000000001';
const rid='00000000-0000-4000-8000-000000000003';
let browser:Browser;
let bundle:string;
beforeAll(async()=>{
 const root=decodeURIComponent(new URL('../../../',import.meta.url).pathname).replace(/^\/(?=[A-Za-z]:\/)/,'');
 const api=`${root}src/app/discovery-api.ts`;
 const built=await build({configFile:false,root,logLevel:'error',define:{'process.env.NODE_ENV':'"test"'},plugins:[react(),{
  name:'discovery-interaction-fixtures',enforce:'pre',
  resolveId(source,importer){
   if(source.endsWith('/auth/oidc'))return '\0memory-only-auth';
   if(source==='../../app/discovery-api'&&importer?.endsWith('/DiscoveryPanel.tsx'))return '\0deferred-discovery-api';
  },
  load(id){
   if(id==='\0memory-only-auth')return 'export const token=()=>"memory-only-test-token";';
   if(id==='\0deferred-discovery-api')return `export * from ${JSON.stringify(api)};export const getDiscoveryDetail=(...args)=>window.discoveryTest.getDetail(...args);export const executeDiscoveryCommand=(...args)=>window.discoveryTest.executeCommand(...args);`;
  },
 }],build:{write:false,minify:false,lib:{entry:`${root}src/features/workspace/DiscoveryPanel.interaction-harness.tsx`,formats:['iife'],name:'DiscoveryInteraction'}}});
 const output=Array.isArray(built)?built[0]:built;
 if(!('output' in output))throw new Error('Expected an in-memory browser bundle');
 bundle=output.output.filter(output=>output.type==='chunk').map(output=>output.code).join('\n');
 browser=await chromium.launch({headless:true});
},30_000);
afterAll(async()=>{await browser?.close()});

async function mount(path=`/workspaces/${wid}/records/${rid}`){
 const page=await browser.newPage();
 page.setDefaultTimeout(3_000);
 // Supply a secure origin entirely from memory so crypto.randomUUID is real.
 await page.route('**/*',route=>route.request().url()==='https://discovery.invalid/'?route.fulfill({contentType:'text/html',body:'<!doctype html><div id="root"></div>'}):route.abort());
 await page.goto('https://discovery.invalid/');
 await page.addScriptTag({content:bundle});
 await page.evaluate(path=>window.discoveryTest.mount(path),path);
 return page;
}
async function beginFavorite(page:Page){
 await page.getByRole('button',{name:'添加收藏',exact:true}).click();
 await page.getByRole('button',{name:'确认操作',exact:true}).click();
 await page.waitForSelector('[data-testid="discovery-command"][data-state="pending"]');
 expect((await page.evaluate(()=>window.discoveryTest.snapshot())).calls).toHaveLength(1);
}
async function settle(page:Page,outcome:'success'|'failure',index=0){
 await page.evaluate(({index,outcome})=>window.discoveryTest.settle(index,outcome),{index,outcome});
 // Let React commit promise-driven updates and paint before checking absence.
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
}
async function noResurrectedCommand(page:Page){
 expect(await page.getByTestId('discovery-command').count()).toBe(0);
 expect(await page.getByRole('button',{name:'核对原操作',exact:true}).count()).toBe(0);
 expect(await page.getByText(/操作已确认/).count()).toBe(0);
}

test.each(['success','failure'] as const)('detail denial aborts pending favorite and discards late %s',async outcome=>{
 const page=await mount();try{
  await beginFavorite(page);await page.evaluate(()=>window.discoveryTest.denyDetail());
  await page.waitForSelector('[data-testid="discovery-state"][data-state="forbidden"]');
  const snapshot=await page.evaluate(()=>window.discoveryTest.snapshot());
  expect(snapshot.calls[0].aborted).toBe(true);expect(snapshot.refreshes).toBe(1);expect(snapshot.rejections).toBe(0);
  expect(await page.getByTestId('discovery-detail').count()).toBe(0);await noResurrectedCommand(page);
  await settle(page,outcome);await noResurrectedCommand(page);
  expect(await page.getByText('当前授权文档',{exact:true}).count()).toBe(0);
  expect(await page.locator('[data-state="forbidden"]').count()).toBe(1);
 }finally{await page.close()}
});

test.each(['success','failure'] as const)('re-reading the same allowed detail cannot revive a denied old command: %s',async outcome=>{
 const page=await mount();try{
  await beginFavorite(page);await page.evaluate(()=>window.discoveryTest.denyDetail());
  await page.waitForSelector('[data-state="forbidden"]');await page.evaluate(()=>window.discoveryTest.allowDetail());
  await page.getByRole('button',{name:'重新读取',exact:true}).click();
  await page.waitForSelector('[data-testid="discovery-detail"]');
  await settle(page,outcome);await noResurrectedCommand(page);
  await page.getByRole('button',{name:'添加收藏',exact:true}).click();
  await page.waitForSelector('[data-testid="discovery-command"][data-state="confirm"]');
 }finally{await page.close()}
});

test.each((['actor','workspace','epoch','route','unmount'] as const).flatMap(change=>(['success','failure'] as const).map(outcome=>({change,outcome}))))('changing $change discards late $outcome from the former context',async({change,outcome})=>{
 const page=await mount();try{
  await beginFavorite(page);const previous=await page.getByTestId('discovery-root').getAttribute('data-context');
  await page.evaluate(change=>window.discoveryTest.change(change),change);
  if(change==='unmount')await page.waitForSelector('[data-testid="discovery-root"]',{state:'detached'});
  else if(change==='route')await page.waitForSelector('[data-testid="discovery-root"][data-view="documents"]');
  else await page.waitForFunction(previous=>document.querySelector('[data-testid="discovery-root"]')?.getAttribute('data-context')!==previous,previous);
  expect((await page.evaluate(()=>window.discoveryTest.snapshot())).calls[0].aborted).toBe(true);
  await settle(page,outcome);await noResurrectedCommand(page);
 }finally{await page.close()}
});

test('a live unknown result only rechecks the exact original command',async()=>{
 const page=await mount();try{
  await beginFavorite(page);await settle(page,'failure');
  await page.waitForSelector('[data-testid="discovery-command"][data-state="unknown"]');
  expect(await page.getByRole('button',{name:'添加收藏',exact:true}).isDisabled()).toBe(true);
  await page.getByRole('button',{name:'核对原操作',exact:true}).click();
  await page.waitForFunction(()=>window.discoveryTest.snapshot().calls.length===2);
  const {calls}=await page.evaluate(()=>window.discoveryTest.snapshot());expect(calls[1].command).toEqual(calls[0].command);
  await settle(page,'success',1);expect(await page.getByText(/操作已确认（已核对原操作）/).count()).toBe(1);
 }finally{await page.close()}
});

test.each(['all','todo','references'])('route collection %s and every other filter reach the actual list request',async collection=>{
 const page=await mount(`/workspaces/${wid}/favorites?collection=${collection}&kind=reference&type=manual&status=ARCHIVED`);try{
  await page.waitForSelector('[data-testid="discovery-total"]');
  const {requests}=await page.evaluate(()=>window.discoveryTest.snapshot());expect(requests).toHaveLength(1);
  const query=new URL(requests[0].url,'https://fixture.invalid').searchParams;
  expect(Object.fromEntries(query)).toEqual({collection,tab:'favorites',visibility:'visible',limit:'20',kind:'reference',document_type:'manual',lifecycle:'ARCHIVED'});
  expect(await page.getByLabel('记录类型',{exact:true}).inputValue()).toBe('reference');
 }finally{await page.close()}
});

test('references plus the document view stays an empty AND intersection in the request',async()=>{
 const page=await mount(`/workspaces/${wid}/documents?collection=references`);try{
  await page.waitForSelector('[data-testid="discovery-total"]');
  const {requests}=await page.evaluate(()=>window.discoveryTest.snapshot());const query=new URL(requests[0].url,'https://fixture.invalid').searchParams;
  expect(query.get('collection')).toBe('references');expect(query.get('kind')).toBe('document');
  expect(await page.locator('[data-state="empty-filtered"]').count()).toBe(1);
 }finally{await page.close()}
});

test('search references preserves the route filters in POST while keeping the term out of the URL',async()=>{
 const page=await mount(`/workspaces/${wid}/search?collection=references&kind=knowledge&tab=participating&status=APPROVED`);try{
  await page.waitForSelector('[data-testid="discovery-total"]');
  const {requests}=await page.evaluate(()=>window.discoveryTest.snapshot());expect(requests).toHaveLength(1);
  expect(requests[0]).toEqual({url:`/api/v1/workspaces/${wid}/search`,body:{query:'参考',collection:'references',tab:'participating',visibility:'visible',limit:20,kind:'knowledge',lifecycle:'APPROVED'}});
 }finally{await page.close()}
});
