import type {WorkspaceAccess} from '../../app/access-api';
import {REQUEST_TIMEOUT_MS} from '../../app/api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import {TemplateError} from './template-api';

export type OutlineSection={id:string;title:string;template_section_id:string|null};
export type OutlineSnapshot={sections:OutlineSection[]};
export type TemplateSection={id:string;title:string;mandatory:boolean};
export type OutlineReason={code:string;path:string;other_path?:string;template_section_id?:string;expected_title?:string;context_reasons?:{code:string;path:string}[]};
export type OutlineData={version_id:string|null;revision:number;base_version_id:string|null;document_version_id:string;document_revision:number;context_version_id:string|null;template_version_id:string;development_only:true;template_sections:TemplateSection[];required_sections:TemplateSection[];snapshot:OutlineSnapshot|null;content_hash:string|null;created_by:string|null;created_at:string|null;confirmed_by:string|null;confirmed_at:string|null;state:'OUTLINE_PENDING'|'OUTLINE_READY';reasons:OutlineReason[]};
export type OutlineVersion={version_id:string;revision:number;document_version_id:string;context_version_id:string;template_version_id:string;created_by:string;created_at:string;confirmed_by:string|null;confirmed_at:string|null};
export type SaveOutline={base_outline_version_id:string|null;outline_revision:number;document_version_id:string;document_revision:number;context_version_id:string;template_version_id:string;snapshot:OutlineSnapshot};
export type ConfirmOutline={version_id:string;document_version_id:string;document_revision:number;context_version_id:string;template_version_id:string};

export class OutlineError extends TemplateError {
 constructor(failure:ConstructorParameters<typeof TemplateError>[0],message:string,status?:number,readonly reasons:OutlineReason[]=[]){super(failure,message,status)}
}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const id=(value:unknown):value is string=>typeof value==='string'&&uuid.test(value);
const object=(value:unknown):value is Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const integer=(value:unknown,min=0):value is number=>Number.isSafeInteger(value)&&Number(value)>=min;
const date=(value:unknown):value is string=>typeof value==='string'&&!Number.isNaN(Date.parse(value));
const title=(value:unknown):value is string=>typeof value==='string'&&value.trim().length>0&&Array.from(value).length<=256&&!Array.from(value).some(char=>{const code=char.codePointAt(0)!;return code<32||code>=0xd800&&code<=0xdfff});
const reason=(value:unknown):value is OutlineReason=>object(value)&&typeof value.code==='string'&&typeof value.path==='string'&&(value.other_path===undefined||typeof value.other_path==='string')&&(value.template_section_id===undefined||id(value.template_section_id))&&(value.expected_title===undefined||typeof value.expected_title==='string')&&(value.context_reasons===undefined||Array.isArray(value.context_reasons)&&value.context_reasons.every(x=>object(x)&&typeof x.code==='string'&&typeof x.path==='string'));
const section=(value:unknown):value is OutlineSection=>object(value)&&id(value.id)&&title(value.title)&&(value.template_section_id===null||id(value.template_section_id));
const snapshot=(value:unknown):value is OutlineSnapshot=>object(value)&&Array.isArray(value.sections)&&value.sections.length>=1&&value.sections.length<=128&&value.sections.every(section);
const templateSection=(value:unknown):value is TemplateSection=>object(value)&&id(value.id)&&title(value.title)&&typeof value.mandatory==='boolean';
const invalid=():never=>{throw new OutlineError('invalid-response','大纲回执无效；本地输入已保留')};
const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);

export function validateOutline(value:unknown):OutlineData{
 if(!object(value)||value.version_id!==null&&!id(value.version_id)||!integer(value.revision)||value.base_version_id!==null&&!id(value.base_version_id)||!id(value.document_version_id)||!integer(value.document_revision,1)||value.context_version_id!==null&&!id(value.context_version_id)||!id(value.template_version_id)||value.development_only!==true||!Array.isArray(value.template_sections)||value.template_sections.length<1||value.template_sections.length>128||!value.template_sections.every(templateSection)||!Array.isArray(value.required_sections)||!value.required_sections.every(templateSection)||!Array.isArray(value.reasons)||!value.reasons.every(reason)||!['OUTLINE_PENDING','OUTLINE_READY'].includes(String(value.state))||value.snapshot!==null&&!snapshot(value.snapshot)||value.content_hash!==null&&!(typeof value.content_hash==='string'&&/^[0-9a-f]{64}$/.test(value.content_hash))||value.created_by!==null&&!id(value.created_by)||value.created_at!==null&&!date(value.created_at)||value.confirmed_by!==null&&!id(value.confirmed_by)||value.confirmed_at!==null&&!date(value.confirmed_at))return invalid();
 const result=value as OutlineData;
 const required=result.template_sections.filter(x=>x.mandatory);
 if(!same(required,result.required_sections)||new Set(result.template_sections.map(x=>x.id)).size!==result.template_sections.length||result.version_id===null&&(result.revision!==0||result.snapshot!==null||result.content_hash!==null||result.created_by!==null||result.created_at!==null||result.confirmed_by!==null||result.confirmed_at!==null)||result.version_id!==null&&(result.revision<1||!result.snapshot||!result.content_hash||!result.created_by||!result.created_at)||result.state==='OUTLINE_READY'&&(result.reasons.length!==0||!result.version_id||!result.confirmed_at||!result.confirmed_by)||Boolean(result.confirmed_at)!==Boolean(result.confirmed_by))return invalid();
 if(result.state==='OUTLINE_READY'&&result.required_sections.some(rule=>{
  const matches=result.snapshot?.sections.filter(section=>section.template_section_id===rule.id);
  return matches?.length!==1||matches[0].title!==rule.title;
 }))return invalid();
 return result;
}

function ensureScope(current:WorkspaceAccess,documentId:string){
 if(!id(current.workspace_id)||!id(current.actor_id)||!id(documentId)||current.policy_epoch.length!==3||!current.policy_epoch.every(x=>integer(x,1))||current.policy_epoch[0]!==current.policy_epoch[2])throw new OutlineError('context','当前权限范围无效，请重新读取');
}
async function raw(current:WorkspaceAccess,documentId:string,suffix:string,method:'GET'|'PUT'|'POST',body?:SaveOutline|ConfirmOutline,signal?:AbortSignal):Promise<unknown>{
 ensureScope(current,documentId);const access=token();if(!access)throw new OutlineError('authentication','请重新登录',401);
 const controller=new AbortController();let timedOut=false;let rejectAbort:(error:unknown)=>void=()=>{};
 const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const abort=()=>{controller.abort();rejectAbort(new OutlineError(timedOut?'timeout':'cancelled','操作结果未知；请核对当前版本'))};
 signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>{timedOut=true;abort()},REQUEST_TIMEOUT_MS);
 try{
  if(signal?.aborted)abort();
  return await Promise.race([(async()=>{
   const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${documentId}/outline${suffix}`,{method,signal:controller.signal,headers:{Authorization:`Bearer ${access}`,'X-Request-ID':crypto.randomUUID(),...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
   if(controller.signal.aborted)throw new OutlineError('cancelled','操作结果未知；请核对当前版本');
   if(!response.ok){let reasons:OutlineReason[]=[];try{const error=await boundedJson(response,8192,'错误响应无效',controller.signal);if(object(error)&&object(error.error)&&object(error.error.details)&&Array.isArray(error.error.details.reasons))reasons=error.error.details.reasons.filter(reason)}catch{/* HTTP status remains authoritative */}
    const failure=response.status===401?'authentication':response.status===403?'forbidden':response.status===404?'missing':response.status===409?'conflict':response.status===422?'validation':'unavailable';
    throw new OutlineError(failure,`大纲操作被拒绝 (${response.status})`,response.status,reasons);
   }
   const value=await boundedJson(response,256*1024,'大纲响应无效',controller.signal);
   if(controller.signal.aborted||signal?.aborted||token()!==access)throw new OutlineError('cancelled','权限或请求状态变化；请核对版本');
   if(!object(value)||!Object.hasOwn(value,'data'))return invalid();return value.data;
  })(),aborted]);
 }catch(error){if(error instanceof TemplateError)throw error;throw new OutlineError(timedOut?'timeout':'unavailable','大纲操作结果未知；请核对当前版本')}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
const data=async(current:WorkspaceAccess,documentId:string,suffix:string,method:'GET'|'PUT'|'POST',body?:SaveOutline|ConfirmOutline,signal?:AbortSignal)=>validateOutline(await raw(current,documentId,suffix,method,body,signal));
export const getOutline=(current:WorkspaceAccess,documentId:string,signal?:AbortSignal)=>data(current,documentId,'','GET',undefined,signal);
export const getOutlineVersion=(current:WorkspaceAccess,documentId:string,versionId:string,signal?:AbortSignal)=>{if(!id(versionId))throw new OutlineError('validation','版本标识无效');return data(current,documentId,`/versions/${versionId}`,'GET',undefined,signal)};
export async function getOutlineVersions(current:WorkspaceAccess,documentId:string,signal?:AbortSignal):Promise<{items:OutlineVersion[];more:boolean}>{
 const value=await raw(current,documentId,'/versions','GET',undefined,signal);
 if(!object(value)||!Array.isArray(value.items)||value.items.length>100||typeof value.more!=='boolean'||value.items.some(x=>!object(x)||!id(x.version_id)||!integer(x.revision,1)||!id(x.document_version_id)||!id(x.context_version_id)||!id(x.template_version_id)||!id(x.created_by)||!date(x.created_at)||x.confirmed_by!==null&&!id(x.confirmed_by)||x.confirmed_at!==null&&!date(x.confirmed_at)))return invalid();
 return value as {items:OutlineVersion[];more:boolean};
}
export async function saveOutline(current:WorkspaceAccess,documentId:string,body:SaveOutline,signal?:AbortSignal):Promise<OutlineData>{
 const result=await data(current,documentId,'','PUT',body,signal);
 if(result.base_version_id!==body.base_outline_version_id||result.revision!==body.outline_revision+1||!result.version_id||result.document_version_id!==body.document_version_id||result.document_revision!==body.document_revision||result.context_version_id!==body.context_version_id||result.template_version_id!==body.template_version_id||!same(result.snapshot,body.snapshot))return invalid();
 return result;
}
export async function confirmOutline(current:WorkspaceAccess,documentId:string,body:ConfirmOutline,signal?:AbortSignal):Promise<OutlineData>{
 const result=await data(current,documentId,'/confirm','POST',body,signal);
 if(result.version_id!==body.version_id||result.document_version_id!==body.document_version_id||result.document_revision!==body.document_revision||result.context_version_id!==body.context_version_id||result.template_version_id!==body.template_version_id||result.state!=='OUTLINE_READY')return invalid();
 return result;
}
