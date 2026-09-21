import {afterAll,beforeAll,expect,test} from 'vitest';
import {chromium,type Browser,type Page} from '@playwright/test';
import {build} from 'vite';
import react from '@vitejs/plugin-react';
import type {} from './App.search.interaction-harness';

const workspaceId='00000000-0000-4000-8000-000000000001';
let browser:Browser;
let bundle:string;

beforeAll(async()=>{
 const root=decodeURIComponent(new URL('../../',import.meta.url).pathname).replace(/^\/(?=[A-Za-z]:\/)/,'');
 const harness=`${root}src/app/App.search.interaction-harness.tsx`;
 const built=await build({configFile:false,root,logLevel:'error',define:{'process.env.NODE_ENV':'"test"'},plugins:[react(),{
   name:'app-search-memory-substitutes',enforce:'pre',
   resolveId(source,importer){
    if(source.endsWith('/auth/oidc'))return '\0memory-only-auth';
    if(source==='./api'&&importer?.endsWith('/src/app/App.tsx'))return '\0memory-only-api';
    if(source==='./access-api'&&importer?.endsWith('/src/app/App.tsx'))return '\0memory-only-access';
    if(source==='./AccessPanel'&&importer?.endsWith('/src/app/App.tsx'))return '\0memory-only-access-panel';
   },
   load(id){
    if(id==='\0memory-only-auth')return 'let sessionToken="memory-only-test-token";export const token=()=>sessionToken;export const beginLogin=async()=>{};export const clearSession=()=>{sessionToken=null};export const finishLogin=async()=>"/";export const logout=clearSession;';
    if(id==='\0memory-only-api')return 'export class AccountRequestError extends Error{constructor(message,kind,status){super(message);this.kind=kind;this.status=status}};export const getMe=async()=>({actor_id:"00000000-0000-4000-8000-000000000002",subject:"memory-subject",display_name:"当前作者",department:"工程部",workspace_id:"00000000-0000-4000-8000-000000000001",workspace_slug:"actual-project",workspace_name:"真实项目"});export const getReadiness=async()=>"依赖已就绪";export const isAuthenticationRejection=error=>error instanceof AccountRequestError&&error.kind==="authentication";export const isWorkspaceForbidden=error=>error instanceof AccountRequestError&&error.kind==="forbidden";';
    if(id==='\0memory-only-access')return 'export const getWorkspace=async()=>({...window.appSearchTest.context(),name:"真实项目",slug:"actual-project",display_name:"当前作者",department:"工程部",roles:["author"],clearance:1,operations:["workspace:read"]});';
    if(id==='\0memory-only-access-panel')return 'export default function AccessPanel(){return null}';
   },
 }],build:{write:false,minify:false,lib:{entry:harness,formats:['iife'],name:'AppSearchInteraction'}}});
 const output=Array.isArray(built)?built[0]:built;
 if(!('output' in output))throw new Error('Expected an in-memory browser bundle');
 bundle=output.output.filter(output=>output.type==='chunk').map(output=>output.code).join('\n');
 browser=await chromium.launch({headless:true});
},30_000);
afterAll(async()=>{await browser?.close()});

async function mount(){
 const page=await browser.newPage();page.setDefaultTimeout(3_000);
 await page.route('**/*',route=>route.request().url()==='https://app-search.invalid/'?route.fulfill({contentType:'text/html',body:'<!doctype html><div id="root"></div>'}):route.abort());
 await page.goto('https://app-search.invalid/');
 await page.addScriptTag({content:bundle});
 await page.evaluate(path=>window.appSearchTest.mount(path),`/workspaces/${workspaceId}/documents`);
 await page.getByRole('textbox',{name:'全局搜索',exact:true}).waitFor();
 return page;
}

async function submitBrowserPaste(page:Page,value:string){
 const input=page.getByRole('textbox',{name:'全局搜索',exact:true});
 await input.click();
 // Browser text insertion follows native input constraints, unlike setting value.
 await page.keyboard.insertText(value);
 await input.press('Enter');
 await page.waitForFunction(()=>window.appSearchTest.snapshot().requests.some(request=>request.url.endsWith('/search')));
 return {input,requests:await page.evaluate(()=>window.appSearchTest.snapshot().requests)};
}

const astral='𠮷';
const cases=[
 {name:'128 astral code points',entered:astral.repeat(128),expected:astral.repeat(128)},
 {name:'128 mixed BMP and astral code points',entered:Array.from({length:64},()=>`A${astral}`).join(''),expected:Array.from({length:64},()=>`A${astral}`).join('')},
 {name:'128 combining-sequence code points',entered:'e\u0301'.repeat(64),expected:'e\u0301'.repeat(64)},
 {name:'129 code points truncates at the code-point boundary',entered:astral.repeat(129),expected:astral.repeat(128)},
];

test.each(cases)('$name remains visible and is the exact POST query',async({entered,expected})=>{
 const page=await mount();try{
  const {input,requests}=await submitBrowserPaste(page,entered);
  expect(await input.inputValue()).toBe(expected);
  const search=requests.filter(request=>request.url.endsWith('/search'));
  expect(search).toHaveLength(1);
  expect(search[0]).toEqual({url:`/api/v1/workspaces/${workspaceId}/search`,method:'POST',body:{query:expected,collection:'all',tab:'recent',visibility:'visible',limit:20}});
  expect(search[0].url).not.toContain(expected);
 }finally{await page.close()}
});

const compositionCases=[
 {name:'127-character prefix followed by a Chinese IME commit',prefix:'A'.repeat(127),composition:'中',expected:'A'.repeat(127)+'中'},
 {name:'128 astral code points committed by IME',prefix:'',composition:astral.repeat(128),expected:astral.repeat(128)},
 {name:'over-limit IME commit truncated by code point',prefix:'A'.repeat(127),composition:astral.repeat(2),expected:'A'.repeat(127)+astral},
];

test.each(compositionCases)('$name preserves composition and submits only after commit',async({prefix,composition,expected})=>{
 const page=await mount();try{
  const input=page.getByRole('textbox',{name:'全局搜索',exact:true});
  await input.click();if(prefix)await page.keyboard.insertText(prefix);
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Input.imeSetComposition',{text:'zhong',selectionStart:5,selectionEnd:5});
  expect(await input.inputValue()).toBe(prefix+'zhong');
  // A real native Enter during an active composition must not submit a query.
  await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  // Some engines report isComposing=false on the confirming key; the active
  // composition flag must still prevent a premature submission.
  await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:false});
  expect(await page.evaluate(()=>window.appSearchTest.snapshot().requests.filter(request=>request.url.endsWith('/search')))).toEqual([]);
  await cdp.send('Input.imeSetComposition',{text:composition,selectionStart:composition.length,selectionEnd:composition.length});
  expect(await input.inputValue()).toBe(prefix+composition);
  await cdp.send('Input.insertText',{text:composition});
  expect(await input.inputValue()).toBe(expected);
  await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',keyCode:229,isComposing:false});
  expect(await page.evaluate(()=>window.appSearchTest.snapshot().requests.filter(request=>request.url.endsWith('/search')))).toEqual([]);
  await input.press('Enter');
  await page.waitForFunction(()=>window.appSearchTest.snapshot().requests.some(request=>request.url.endsWith('/search')));
  const requests=await page.evaluate(()=>window.appSearchTest.snapshot().requests.filter(request=>request.url.endsWith('/search')));
  expect(requests).toEqual([{url:`/api/v1/workspaces/${workspaceId}/search`,method:'POST',body:{query:expected,collection:'all',tab:'recent',visibility:'visible',limit:20}}]);
  await cdp.detach();
 }finally{await page.close()}
});

test.each(['context','logout'] as const)('%s clearing cancels a pending browser composition',async(reason)=>{
 const page=await mount();try{
  const input=page.getByRole('textbox',{name:'全局搜索',exact:true});
  await input.click();await page.keyboard.insertText('A'.repeat(127));
  const oldInput=await input.elementHandle();
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Input.imeSetComposition',{text:'zhong',selectionStart:5,selectionEnd:5});
  expect(await input.inputValue()).toBe('A'.repeat(127)+'zhong');
  // DOM click preserves the active IME range until App handles the reset.
  if(reason==='context'){
   await page.evaluate(()=>window.appSearchTest.advanceContext());
   await page.getByRole('button',{name:'账户与会话',exact:true}).evaluate(button=>(button as HTMLButtonElement).click());
  }else{
   await page.getByRole('button',{name:'安全退出',exact:true,includeHidden:true}).evaluate(button=>(button as HTMLButtonElement).click());
  }
  await page.waitForFunction(()=>document.querySelector<HTMLInputElement>('#globalSearch')?.value==='');
  expect(await oldInput!.evaluate(node=>node.isConnected)).toBe(false);
  // A native commit aimed at the cancelled range and a delayed compositionend
  // from the detached node cannot restore the old keyword into the new input.
  await cdp.send('Input.insertText',{text:'中'});
  await oldInput!.dispatchEvent('compositionend',{data:'中'});
  expect(await input.inputValue()).toBe('');
  await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:false});
  expect(await page.evaluate(()=>window.appSearchTest.snapshot().requests.filter(request=>request.url.endsWith('/search')))).toEqual([]);
  if(reason==='logout')expect(await input.isDisabled()).toBe(true);
  else{
   await input.click();await page.keyboard.insertText('fresh');await input.press('Enter');
   await page.waitForFunction(()=>window.appSearchTest.snapshot().requests.some(request=>request.url.endsWith('/search')));
   const requests=await page.evaluate(()=>window.appSearchTest.snapshot().requests.filter(request=>request.url.endsWith('/search')));
   expect(requests).toHaveLength(1);expect(requests[0].body).toMatchObject({query:'fresh'});
  }
  await cdp.detach();
 }finally{await page.close()}
});
