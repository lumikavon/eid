import {afterAll,beforeAll,expect,test} from 'vitest';
import {chromium,expect as browserExpect,type Browser,type Page} from '@playwright/test';
import {build} from 'vite';
import react from '@vitejs/plugin-react';
import type {} from './TemplateWorkspace.interaction-harness';

const wid='00000000-0000-4000-8000-000000000001';
let browser:Browser;
let bundle:string;
beforeAll(async()=>{
 const root=decodeURIComponent(new URL('../../../',import.meta.url).pathname).replace(/^\/(?=[A-Za-z]:\/)/,'');
 const built=await build({configFile:false,root,logLevel:'error',define:{'process.env.NODE_ENV':'"test"'},plugins:[react(),{
  name:'template-interaction-memory-auth',enforce:'pre',
  resolveId(source){if(source.endsWith('/auth/oidc'))return '\0memory-only-auth'},
  load(id){if(id==='\0memory-only-auth')return 'export const token=()=>"memory-only-test-token";'},
 }],build:{write:false,minify:false,lib:{entry:`${root}src/features/templates/TemplateWorkspace.interaction-harness.tsx`,formats:['iife'],name:'TemplateInteraction'}}});
 const output=Array.isArray(built)?built[0]:built;
 if(!('output' in output))throw new Error('Expected an in-memory browser bundle');
 bundle=output.output.filter(output=>output.type==='chunk').map(output=>output.code).join('\n');
 browser=await chromium.launch({headless:true});
},30_000);
afterAll(async()=>{await browser?.close()});

async function mount(quick=false){
 const page=await browser.newPage();page.setDefaultTimeout(3_000);
 await page.route('**/*',route=>route.request().url()==='https://templates.invalid/'?route.fulfill({contentType:'text/html',body:'<!doctype html><div id="root"></div>'}):route.abort());
 await page.goto('https://templates.invalid/');
 await page.addScriptTag({content:bundle});
 await page.evaluate(value=>window.templateTest.mount(value),quick);
 await page.getByTestId('template-center').waitFor();
 await page.locator('.tcard').first().waitFor();
 return page;
}
async function openForm(page:Page){
 await page.locator('.tcard').first().getByRole('button',{name:'使用',exact:true}).click();
 await page.getByRole('dialog',{name:'新建文档'}).waitFor();
}
async function create(page:Page,name='  我的方案  '){
 await page.getByLabel('文档名称').fill(name);
 await page.getByRole('button',{name:'创建并查看初始文档'}).click();
 await page.waitForFunction(()=>window.templateTest.snapshot().calls.length>0);
}

test('P-07 header keeps title, subtitle, search, type select, and a visibly deferred upload entry',async()=>{
 const page=await mount();try{
  const head=page.locator('.template-head');
  expect(await head.locator('h1').textContent()).toBe('模板中心');
  await browserExpect(head.getByText('海量专业模板，助力高效文档编写')).toHaveCount(1);
  await browserExpect(head.getByRole('textbox',{name:'搜索模板'})).toHaveCount(1);
  await browserExpect(head.getByRole('combobox',{name:'按文种筛选'})).toHaveCount(1);
  await browserExpect(head.getByRole('button',{name:'＋ 上传模板'})).toBeDisabled();
  await browserExpect(head.getByText('Story 2.4 开放')).toHaveCount(1);
 }finally{await page.close()}
});

test.each([403,404] as const)('create %s keeps entered form and a safe error while current workspace is unchanged',async status=>{
 const page=await mount();try{
  await openForm(page);await create(page);
  await page.evaluate(value=>window.templateTest.settle(0,value),status);
  await page.getByRole('alert').last().waitFor();
  await browserExpect(page.getByRole('dialog',{name:'新建文档'})).toBeVisible();
  expect(await page.getByLabel('文档名称').inputValue()).toBe('  我的方案  ');
  expect(await page.getByLabel('参考知识范围').inputValue()).toBe('project_only');
  expect(await page.getByRole('alert').last().textContent()).not.toContain('secret server detail');
  await browserExpect(page.getByRole('button',{name:'创建并查看初始文档'})).toBeEnabled();
  expect((await page.evaluate(()=>window.templateTest.snapshot())).refreshes).toBe(1);
 }finally{await page.close()}
});

test('a current workspace rejection on refresh discards the form',async()=>{
 const page=await mount();try{
  await openForm(page);await create(page);
  await page.evaluate(()=>{window.templateTest.denyWorkspaceOnRefresh();window.templateTest.settle(0,403)});
  await page.getByText('工作区访问被拒绝').waitFor();
  expect(await page.getByRole('dialog').count()).toBe(0);
 }finally{await page.close()}
});

test('authentication rejection clears the form and protected detail without showing server text',async()=>{
 const page=await mount();try{
  await openForm(page);await create(page);
  await page.evaluate(()=>window.templateTest.settle(0,401));
  await page.getByRole('alert').first().waitFor();
  expect(await page.getByRole('dialog').count()).toBe(0);
  const snapshot=await page.evaluate(()=>window.templateTest.snapshot());
  expect(snapshot.rejections).toBe(1);expect(snapshot.queryCount).toBe(0);
  expect(await page.getByTestId('template-center').textContent()).not.toContain('secret server detail');
 }finally{await page.close()}
});

test('cancel and backdrop interaction never send a create request',async()=>{
 const page=await mount();try{
  await openForm(page);await page.getByLabel('文档名称').fill('不应创建');
  await page.locator('#modalMask').click({position:{x:2,y:2}});
  await browserExpect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  expect(await page.getByRole('dialog').count()).toBe(0);
  expect((await page.evaluate(()=>window.templateTest.snapshot())).calls).toHaveLength(0);
 }finally{await page.close()}
});

test('unknown outcome can only retry the same body and idempotency key',async()=>{
 const page=await mount();try{
  await openForm(page);await create(page);
  await page.evaluate(()=>window.templateTest.settle(0,503));
  await page.getByRole('button',{name:'核对原操作'}).waitFor();
  await browserExpect(page.getByRole('button',{name:'创建并查看初始文档'})).toBeDisabled();
  await page.getByRole('button',{name:'核对原操作'}).click();
  await page.waitForFunction(()=>window.templateTest.snapshot().calls.length===2);
  const {calls}=await page.evaluate(()=>window.templateTest.snapshot());
  expect(calls[0].key).toBeTruthy();expect(calls[1].key).toBe(calls[0].key);expect(calls[1].body).toEqual(calls[0].body);
  expect(calls[0].body.name).toBe('我的方案');
  await page.evaluate(()=>window.templateTest.settle(1,201));
  await page.waitForFunction(()=>window.templateTest.snapshot().routePath.includes('/documents/'));
  expect((await page.evaluate(()=>window.templateTest.snapshot())).routePath).toBe(`/workspaces/${wid}/documents/00000000-0000-4000-8000-000000000005`);
 }finally{await page.close()}
});

test('document name input permits 256 emoji code points without truncation',async()=>{
 const page=await mount();try{
  await openForm(page);
  const name='😀'.repeat(256);
  expect(await page.getByLabel('文档名称').getAttribute('maxlength')).toBe('512');
  await create(page,name);
  expect(await page.getByLabel('文档名称').inputValue()).toBe(name);
  expect((await page.evaluate(()=>window.templateTest.snapshot())).calls[0].body.name).toBe(name);
 }finally{await page.close()}
});

test('quick entry selects the requested document type and opens the same create dialog',async()=>{
 const page=await mount(true);try{
  await page.getByRole('dialog',{name:'新建文档'}).waitFor();
  expect(await page.getByLabel('文档类型').inputValue()).toBe('technical_solution');
  expect(await page.getByRole('dialog').textContent()).toContain('项目技术方案');
  await page.getByRole('button',{name:'取消',exact:true}).click();
  expect((await page.evaluate(()=>window.templateTest.snapshot())).calls).toHaveLength(0);
 }finally{await page.close()}
});
