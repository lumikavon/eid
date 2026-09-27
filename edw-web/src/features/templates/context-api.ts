// Keep transport independent of browser-only app/api module for offline contract checks.
const REQUEST_TIMEOUT_MS=8000;
import {boundedJson} from '../../http/bounded-json';
import type {WorkspaceAccess} from '../../app/access-api';
import {TemplateError} from './template-api';

export type Source={locator:string;resource_id:string|null};
export type Fact={key:string;value:string;unit:string|null;source:Source;owner_id:string;confirmed:boolean};
export type ContextSnapshot={intent:string;facts:Fact[];glossary:{term:string;definition:string}[];constraints:{text:string;source:Source}[];missing:{key:string;required:boolean;resolved:boolean}[];zero_facts:boolean};
export type ContextData={version_id:string|null;revision:number;document_version_id:string;document_revision:number;snapshot:ContextSnapshot|null;content_hash:string|null;created_by:string|null;created_at:string|null;confirmed_by:string|null;confirmed_at:string|null;state:'CONTEXT_READY'|'CONTEXT_PENDING';reasons:{code:string;path:string}[]};
export const blankContext=():ContextSnapshot=>({intent:'',facts:[],glossary:[],constraints:[],missing:[],zero_facts:false});
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const validId=(x:unknown):x is string=>typeof x==='string'&&uuid.test(x);
const obj=(x:unknown):x is Record<string,unknown>=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const invalid=():never=>{throw new TemplateError('invalid-response','上下文回执无效；本地输入已保留')};
const text=(x:unknown,max:number)=>typeof x==='string'&&x.trim().length>0&&Array.from(x).length<=max&&!Array.from(x).some(char=>char.codePointAt(0)!<32||char.codePointAt(0)!>=0xd800&&char.codePointAt(0)!<=0xdfff);
const source=(x:unknown)=>obj(x)&&text(x.locator,512)&&(x.resource_id===null||validId(x.resource_id));
const snapshot=(x:unknown)=>obj(x)&&typeof x.intent==='string'&&x.intent.length<=2048&&typeof x.zero_facts==='boolean'&&Array.isArray(x.facts)&&x.facts.length<=100&&x.facts.every(f=>obj(f)&&text(f.key,128)&&text(f.value,2048)&&(f.unit===null||text(f.unit,64))&&source(f.source)&&validId(f.owner_id)&&typeof f.confirmed==='boolean')&&Array.isArray(x.glossary)&&x.glossary.length<=100&&x.glossary.every(g=>obj(g)&&text(g.term,128)&&text(g.definition,2048))&&Array.isArray(x.constraints)&&x.constraints.length<=100&&x.constraints.every(c=>obj(c)&&text(c.text,2048)&&source(c.source))&&Array.isArray(x.missing)&&x.missing.length<=100&&x.missing.every(m=>obj(m)&&text(m.key,128)&&typeof m.required==='boolean'&&typeof m.resolved==='boolean')&&(!x.zero_facts||x.facts.length===0);
export function validateContext(x:unknown):ContextData{
 if(!obj(x)||x.version_id!==null&&!validId(x.version_id)||!Number.isSafeInteger(x.revision)||Number(x.revision)<0||!validId(x.document_version_id)||!Number.isSafeInteger(x.document_revision)||Number(x.document_revision)<1||x.state!=='CONTEXT_READY'&&x.state!=='CONTEXT_PENDING'||!Array.isArray(x.reasons)||x.reasons.some(r=>!obj(r)||typeof r.code!=='string'||typeof r.path!=='string')||x.confirmed_at!==null&&typeof x.confirmed_at!=='string'||x.confirmed_by!==null&&!validId(x.confirmed_by)||x.version_id===null&&x.snapshot!==null||x.version_id!==null&&(!snapshot(x.snapshot)||typeof x.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(x.content_hash)||!validId(x.created_by)||typeof x.created_at!=='string'||Number.isNaN(Date.parse(x.created_at))))return invalid();
 if(x.state==='CONTEXT_READY'&&(x.reasons.length!==0||!x.confirmed_at||!x.confirmed_by||x.version_id===null||!snapshot(x.snapshot)||!(x.snapshot as ContextSnapshot).intent.trim()||(!(x.snapshot as ContextSnapshot).zero_facts&&(x.snapshot as ContextSnapshot).facts.length===0)||(x.snapshot as ContextSnapshot).facts.some(f=>!f.confirmed)||(x.snapshot as ContextSnapshot).missing.some(m=>m.required&&!m.resolved)))return invalid();
 return x as ContextData;
}
async function callRaw(current:WorkspaceAccess,id:string,suffix:string,method:'GET'|'PUT'|'POST',body?:unknown,signal?:AbortSignal):Promise<unknown>{
 if(!validId(id)||!validId(current.workspace_id))throw new TemplateError('validation','上下文目标无效');
 const {token}=await import('../../auth/oidc');const access=token();if(!access)throw new TemplateError('authentication','请重新登录',401);
 const controller=new AbortController();let expired=false;let rejectAbort:(reason:unknown)=>void=()=>{};const abortPromise=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const abort=()=>{controller.abort();rejectAbort(new TemplateError(expired?'timeout':'cancelled','操作结果未知；请核对当前版本'))};
 signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>{expired=true;abort()},REQUEST_TIMEOUT_MS);
 try{
  if(signal?.aborted)abort();
  return await Promise.race([(async()=>{
   const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${id}/context${suffix}`,{method,signal:controller.signal,headers:{Authorization:`Bearer ${access}`,'X-Request-ID':crypto.randomUUID(),...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
   if(controller.signal.aborted)throw new TemplateError('cancelled','操作结果未知；请核对当前版本');
   if(!response.ok){let details='';try{const value=await boundedJson(response,8192,'错误响应无效',controller.signal);if(obj(value)&&obj(value.error)&&obj(value.error.details))details=JSON.stringify(value.error.details).slice(0,1200)}catch{/* status stays authoritative */}
    const type=response.status===401?'authentication':response.status===403?'forbidden':response.status===404?'missing':response.status===409?'conflict':response.status===422?'validation':'unavailable';
    throw new TemplateError(type,`上下文操作被拒绝 (${response.status})${details?`：${details}`:''}`,response.status)}
   const raw=await boundedJson(response,256*1024,'上下文响应无效',controller.signal);
   if(controller.signal.aborted||signal?.aborted||token()!==access)throw new TemplateError('cancelled','权限或请求状态变化；请核对版本');
   if(!obj(raw))return invalid();return raw.data;
  })(),abortPromise]);
 }catch(error){if(error instanceof TemplateError)throw error;throw new TemplateError(expired?'timeout':'unavailable','上下文操作结果未知；请核对当前版本')}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
const call=async(current:WorkspaceAccess,id:string,suffix:string,method:'GET'|'PUT'|'POST',body?:unknown,signal?:AbortSignal):Promise<ContextData>=>validateContext(await callRaw(current,id,suffix,method,body,signal));
export const getContext=(current:WorkspaceAccess,id:string,signal?:AbortSignal)=>call(current,id,'','GET',undefined,signal);
export const getContextVersion=(current:WorkspaceAccess,id:string,versionId:string,signal?:AbortSignal)=>{
 if(!validId(versionId))throw new TemplateError('validation','上下文版本标识无效');return call(current,id,`/versions/${versionId}`,'GET',undefined,signal);
};
export async function getContextVersions(current:WorkspaceAccess,id:string,signal?:AbortSignal):Promise<{items:{version_id:string;revision:number;created_by:string;created_at:string;confirmed_by:string|null;confirmed_at:string|null}[];more:boolean}>{
 const value=await callRaw(current,id,'/versions','GET',undefined,signal);
 if(!obj(value)||!Array.isArray(value.items)||value.items.length>100||typeof value.more!=='boolean'||value.items.some(x=>!obj(x)||!validId(x.version_id)||!Number.isSafeInteger(x.revision)||!validId(x.created_by)||typeof x.created_at!=='string'||x.confirmed_by!==null&&!validId(x.confirmed_by)||x.confirmed_at!==null&&typeof x.confirmed_at!=='string'))return invalid();
 return value as {items:{version_id:string;revision:number;created_by:string;created_at:string;confirmed_by:string|null;confirmed_at:string|null}[];more:boolean};
}
export const saveContext=(current:WorkspaceAccess,id:string,body:{base_context_version_id:string|null;context_revision:number;document_version_id:string;document_revision:number;snapshot:ContextSnapshot},signal?:AbortSignal)=>call(current,id,'','PUT',body,signal);
export const confirmContext=(current:WorkspaceAccess,id:string,body:{version_id:string;document_version_id:string;document_revision:number;zero_facts_acknowledged:boolean},signal?:AbortSignal)=>call(current,id,'/confirm','POST',body,signal);
