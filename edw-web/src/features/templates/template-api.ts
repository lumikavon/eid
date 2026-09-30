import {token} from '../../auth/oidc';
import {REQUEST_TIMEOUT_MS} from '../../app/api';
import {boundedJson} from '../../http/bounded-json';
import type {WorkspaceAccess} from '../../app/access-api';

export const templateScopes=['enterprise','department','product_line','project','personal'] as const;
export type TemplateScope=typeof templateScopes[number];
export const documentTypeIds=['technical_solution','bid','prd','test_plan','project_summary','technical_requirements','quality_outline','project_plan','functional_test_outline','performance_test_outline','production_form'] as const;
export type DocumentType=typeof documentTypeIds[number];
export const knowledgeScopeIds=['project_only','project_enterprise_quality','all_authorized'] as const;
export type KnowledgeScope=typeof knowledgeScopeIds[number];
export type TypeItem={id:DocumentType;label:string;workflow_state:'catalog_only'};
export type KnowledgeScopeItem={id:KnowledgeScope;label:string;available:boolean};
export type TypeCatalog={types:TypeItem[];knowledge_scopes:KnowledgeScopeItem[]};
export type TemplateCard={template_id:string;version_id:string;name:string;description:string;scope:TemplateScope;category:string;document_type:DocumentType;version_label:string;development_only:true;outline:string[]};
export type TemplateDetail=TemplateCard&{structure:{sections:{title:string}[]}};
export type DocumentData={id:string;workspace_id:string;name:string;document_type:DocumentType;knowledge_scope:KnowledgeScope;template_version_id:string;version_id:string;base_version_id:string|null;content_hash:string;revision:number;ast:{schema_version:'1.0';document:{metadata:Record<string,unknown>;sections:{id:string;title:string;blocks:unknown[]}[];claims:unknown[];citations:unknown[];review_state:Record<string,unknown>}};replayed:boolean};
export type TemplateFilters={scope?:TemplateScope;query?:string;category?:string;document_type?:DocumentType};
export type CreateDocument={name:string;document_type:DocumentType;knowledge_scope:KnowledgeScope;template_version_id:string};
export type SaveDocument={base_version_id:string;revision:number;ast:DocumentData['ast']};
export type DocumentVersion={id:string;revision:number;base_version_id:string|null;content_hash:string;created_by:string;created_at:string;source:'template_create'|'manual_edit'|'ai_patch'};
export type VersionPage={items:DocumentVersion[];next_revision:number|null};
export type SaveTiming={debounce_ms:number;client_request_ms:number;server_processing_ms:number|null;outcome:'confirmed'|'rejected'|'unknown'};
export type UploadedImage={id:string;content_hash:string;content_type:'image/png';byte_length:number;alt:string;width:number;height:number};
export type TemplateFailure='authentication'|'forbidden'|'missing'|'context'|'deprecated'|'idempotency'|'conflict'|'readonly'|'validation'|'unavailable'|'timeout'|'cancelled'|'invalid-response';
export class TemplateError extends Error {constructor(readonly failure:TemplateFailure,message:string,readonly status?:number){super(message);this.name='TemplateError'}}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const obj=(x:unknown):x is Record<string,unknown>=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const validId=(x:unknown):x is string=>typeof x==='string'&&uuid.test(x);
const choice=<T extends string>(x:unknown,options:readonly T[]):x is T=>typeof x==='string'&&options.includes(x as T);
const boundedText=(x:unknown,max:number,min=1):x is string=>typeof x==='string'&&Array.from(x).length>=min&&Array.from(x).length<=max&&!Array.from(x).some(char=>char.codePointAt(0)!<32||char.codePointAt(0)!>=0xd800&&char.codePointAt(0)!<=0xdfff);
const invalid=():never=>{throw new TemplateError('invalid-response','模板或文档响应格式无效，请重新读取')};
function card(value:unknown):TemplateCard{
 if(!obj(value)||!validId(value.template_id)||!validId(value.version_id)||!boundedText(value.name,256)||!boundedText(value.description,2048,0)||!choice(value.scope,templateScopes)||!boundedText(value.category,128)||!choice(value.document_type,documentTypeIds)||!boundedText(value.version_label,128)||value.development_only!==true||!Array.isArray(value.outline)||value.outline.length<1||value.outline.length>64||!value.outline.every(x=>boundedText(x,256)))return invalid();
 return value as TemplateCard;
}
function data(value:unknown):unknown{if(!obj(value)||!Object.hasOwn(value,'data'))return invalid();return value.data}
function ensureContext(current:WorkspaceAccess){if(!validId(current.workspace_id)||!validId(current.actor_id)||!Array.isArray(current.policy_epoch)||current.policy_epoch.length!==3||current.policy_epoch[0]!==current.policy_epoch[2]||!current.policy_epoch.every(x=>Number.isSafeInteger(x)&&x>=1))throw new TemplateError('context','当前工作区上下文无效，请重新读取当前权限')}
function failure(status:number,code:string):TemplateError{
 if(status===401)return new TemplateError('authentication','登录已失效，请重新登录',status);
 if(status===403)return new TemplateError('forbidden','当前目标或知识范围不可访问，请重新读取当前权限',status);
 if(status===404)return new TemplateError('missing','所选模板或文档已不可访问，请重新选择',status);
 if(status===409&&code==='TEMPLATE_DEPRECATED')return new TemplateError('deprecated','模板版本已废弃，请重新选择',status);
 if(status===409&&code==='IDEMPOTENCY_KEY_REUSED')return new TemplateError('idempotency','操作标识已用于其他创建内容，请重新确认',status);
 if(status===409&&code==='DOC_VERSION_CONFLICT')return new TemplateError('conflict','文档已产生新版本，请保留本地草稿并核对',status);
 if(status===409&&code==='DOCUMENT_READ_ONLY')return new TemplateError('readonly','此文档不可直接编辑',status);
 if(status===422)return new TemplateError('validation','输入无效，请检查文档名称、文种和知识范围',status);
 return new TemplateError('unavailable','模板服务暂时不可用，请重试',status);
}
async function request(current:WorkspaceAccess,path:string,signal?:AbortSignal,body?:CreateDocument|SaveDocument,key?:string,method:'POST'|'PUT'='POST'):Promise<{status:number;value:unknown;serverTiming:string|null}>{
 ensureContext(current);const accessToken=token();if(!accessToken)throw new TemplateError('authentication','登录已失效，请重新登录',401);
 const controller=new AbortController();let timedOut=false;let rejectAbort:(reason:unknown)=>void=()=>{};
 const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const abort=()=>{controller.abort();rejectAbort(new TemplateError(timedOut?'timeout':'cancelled',timedOut?'请求超时，结果可能已经提交；请核对原操作':'请求已取消'))};
 signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>{timedOut=true;abort()},REQUEST_TIMEOUT_MS);
 const consume=async()=>{
  if(signal?.aborted){abort();throw new TemplateError('cancelled','请求已取消')}
  const response=await fetch(`/api/v1/workspaces/${current.workspace_id}${path}`,{method:body?method:'GET',signal:controller.signal,headers:{Authorization:`Bearer ${accessToken}`,'X-Request-ID':crypto.randomUUID(),...(body?{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})}:{})},body:body?JSON.stringify(body):undefined});
  if(controller.signal.aborted)throw new TemplateError('cancelled','请求已取消');
  if(!response.ok){let code='';try{const raw=await boundedJson(response,8192,'错误响应无效',controller.signal);if(obj(raw)&&obj(raw.error)&&typeof raw.error.code==='string')code=raw.error.code}catch{/* Keep status-based safe message. */}throw failure(response.status,code)}
  const raw=await boundedJson(response,path.startsWith('/documents')?1024*1024:256*1024,'响应格式无效',controller.signal);
  if(controller.signal.aborted||signal?.aborted||token()!==accessToken)throw new TemplateError('cancelled','请求已取消');
  return {status:response.status,value:data(raw),serverTiming:response.headers.get('Server-Timing')};
 };
 try{return await Promise.race([consume(),aborted])}catch(error){if(error instanceof TemplateError)throw error;if(timedOut)throw new TemplateError('timeout','请求超时，结果可能已经提交；请核对原操作');if(signal?.aborted)throw new TemplateError('cancelled','请求已取消');throw new TemplateError('unavailable','模板服务暂时不可用，请重试')}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
export async function getTypeCatalog(current:WorkspaceAccess,signal?:AbortSignal):Promise<TypeCatalog>{const value=(await request(current,'/document-types',signal)).value;if(!obj(value)||!Array.isArray(value.types)||!Array.isArray(value.knowledge_scopes))return invalid();const types=value.types.map(x=>{if(!obj(x)||!choice(x.id,documentTypeIds)||!boundedText(x.label,128)||x.workflow_state!=='catalog_only')return invalid();return x as TypeItem});const scopes=value.knowledge_scopes.map(x=>{if(!obj(x)||!choice(x.id,knowledgeScopeIds)||!boundedText(x.label,128)||typeof x.available!=='boolean')return invalid();return x as KnowledgeScopeItem});if(new Set(types.map(x=>x.id)).size!==documentTypeIds.length||new Set(scopes.map(x=>x.id)).size!==knowledgeScopeIds.length)return invalid();return {types,knowledge_scopes:scopes}}
export async function getTemplates(current:WorkspaceAccess,filters:TemplateFilters={},signal?:AbortSignal):Promise<TemplateCard[]>{const query=new URLSearchParams();if(filters.scope)query.set('scope',filters.scope);if(filters.query?.trim())query.set('query',filters.query.trim());if(filters.category)query.set('category',filters.category);if(filters.document_type)query.set('document_type',filters.document_type);const value=(await request(current,`/templates${query.size?'?'+query:''}`,signal)).value;if(!obj(value)||!Array.isArray(value.items))return invalid();const items=value.items.map(card);if(items.some(x=>filters.scope&&x.scope!==filters.scope||filters.document_type&&x.document_type!==filters.document_type||filters.category&&x.category!==filters.category)||new Set(items.map(x=>x.version_id)).size!==items.length)return invalid();return items}
export async function getTemplateDetail(current:WorkspaceAccess,versionId:string,signal?:AbortSignal):Promise<TemplateDetail>{if(!validId(versionId))throw new TemplateError('validation','模板版本标识无效');const value=(await request(current,`/templates/${versionId}`,signal)).value;const item=card(value);if(item.version_id!==versionId||!obj(value)||!obj(value.structure)||!Array.isArray(value.structure.sections)||value.structure.sections.length!==item.outline.length||value.structure.sections.some((x,i)=>!obj(x)||x.title!==item.outline[i]))return invalid();return value as TemplateDetail}
export function validateCreate(input:CreateDocument){const name=input.name.trim();if(!boundedText(name,256)||!choice(input.document_type,documentTypeIds)||!choice(input.knowledge_scope,knowledgeScopeIds)||!validId(input.template_version_id))throw new TemplateError('validation','请输入有效名称、文种和知识范围');return {...input,name}}
export function document(value:unknown,current:WorkspaceAccess,id?:string):DocumentData{if(!obj(value)||!validId(value.id)||id&&value.id!==id||value.workspace_id!==current.workspace_id||!boundedText(value.name,256)||!choice(value.document_type,documentTypeIds)||!choice(value.knowledge_scope,knowledgeScopeIds)||!validId(value.template_version_id)||!validId(value.version_id)||value.base_version_id!==null&&!validId(value.base_version_id)||typeof value.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(value.content_hash)||!Number.isSafeInteger(value.revision)||Number(value.revision)<1||typeof value.replayed!=='boolean'||!obj(value.ast)||value.ast.schema_version!=='1.0'||!obj(value.ast.document))return invalid();const ast=value.ast.document;if(!obj(ast.metadata)||!Array.isArray(ast.sections)||!Array.isArray(ast.claims)||!Array.isArray(ast.citations)||!obj(ast.review_state)||ast.metadata.title!==value.name||ast.metadata.document_type!==value.document_type||ast.metadata.knowledge_scope!==value.knowledge_scope||ast.metadata.template_version_id!==value.template_version_id||ast.sections.some(x=>!obj(x)||!validId(x.id)||!boundedText(x.title,256)||!Array.isArray(x.blocks)))return invalid();return value as DocumentData}
export async function getDocument(current:WorkspaceAccess,id:string,signal?:AbortSignal):Promise<DocumentData>{if(!validId(id))throw new TemplateError('validation','文档地址无效');return document((await request(current,`/documents/${id}`,signal)).value,current,id)}
export async function createDocument(current:WorkspaceAccess,input:CreateDocument,key:string,signal?:AbortSignal):Promise<DocumentData>{if(!/^[A-Za-z0-9._:-]{1,128}$/.test(key))throw new TemplateError('validation','操作标识无效');const normalized=validateCreate(input);const response=await request(current,'/documents',signal,normalized,key);if(response.status!==201)return invalid();const result=document(response.value,current);if(result.name!==normalized.name||result.document_type!==normalized.document_type||result.knowledge_scope!==normalized.knowledge_scope||result.template_version_id!==normalized.template_version_id)return invalid();return result}
export async function saveDocument(current:WorkspaceAccess,id:string,input:SaveDocument,signal?:AbortSignal,onTiming?:(event:SaveTiming)=>void,debounceMs=0):Promise<DocumentData>{
 const started=performance.now();let serverMs:number|null=null;
 try{
  if(!validId(id)||!validId(input.base_version_id)||!Number.isSafeInteger(input.revision)||input.revision<1)throw new TemplateError('validation','版本标识无效');
  const response=await request(current,`/documents/${id}`,signal,input,undefined,'PUT');
  const match=/^save;dur=(\d+(?:\.\d+)?)$/.exec(response.serverTiming??'');if(match){const duration=Number(match[1]);if(Number.isFinite(duration)&&duration>=0&&duration<=60000)serverMs=duration}
  if(response.status!==200)return invalid();const result=document(response.value,current,id);if(result.base_version_id!==input.base_version_id||result.revision!==input.revision+1||result.version_id===input.base_version_id)return invalid();
  onTiming?.({debounce_ms:debounceMs,client_request_ms:performance.now()-started,server_processing_ms:serverMs,outcome:'confirmed'});return result;
 }catch(error){onTiming?.({debounce_ms:debounceMs,client_request_ms:performance.now()-started,server_processing_ms:serverMs,outcome:error instanceof TemplateError&&['unavailable','timeout','cancelled','invalid-response'].includes(error.failure)&&!error.status?'unknown':'rejected'});throw error}
}
export async function getDocumentVersions(current:WorkspaceAccess,id:string,beforeRevision?:number,signal?:AbortSignal):Promise<VersionPage>{
 if(!validId(id)||beforeRevision!==undefined&&(!Number.isSafeInteger(beforeRevision)||beforeRevision<1))throw new TemplateError('validation','版本页参数无效');
 const query=beforeRevision?`?before_revision=${beforeRevision}`:'';const value=(await request(current,`/documents/${id}/versions${query}`,signal)).value;
 if(!obj(value)||!Array.isArray(value.items)||value.items.length>50||value.next_revision!==null&&(!Number.isSafeInteger(value.next_revision)||Number(value.next_revision)<1))return invalid();
 const items=value.items.map(item=>{if(!obj(item)||!validId(item.id)||!validId(item.created_by)||!Number.isSafeInteger(item.revision)||Number(item.revision)<1||item.base_version_id!==null&&!validId(item.base_version_id)||typeof item.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(item.content_hash)||typeof item.created_at!=='string'||Number.isNaN(Date.parse(item.created_at))||!['template_create','manual_edit'].includes(String(item.source)))return invalid();return item as DocumentVersion});
 if(items.some((item,index)=>index>0&&item.revision>=items[index-1].revision)||new Set(items.map(item=>item.id)).size!==items.length||value.next_revision!==null&&value.next_revision!==items.at(-1)?.revision)return invalid();
 return {items,next_revision:value.next_revision as number|null};
}
export async function getDocumentVersion(current:WorkspaceAccess,id:string,versionId:string,signal?:AbortSignal):Promise<DocumentData>{
 if(!validId(id)||!validId(versionId))throw new TemplateError('validation','历史版本标识无效');const value=(await request(current,`/documents/${id}/versions/${versionId}`,signal)).value;const result=document(value,current,id);if(result.version_id!==versionId)return invalid();return result;
}
export async function getTestCoverage(current:WorkspaceAccess,id:string,signal?:AbortSignal):Promise<unknown>{
 if(!validId(id))throw new TemplateError('validation','文档标识无效');
 return (await request(current,`/documents/${id}/test-coverage`,signal)).value;
}
export async function getImage(current:WorkspaceAccess,id:string,mediaId:string,signal?:AbortSignal):Promise<Blob>{
 ensureContext(current);if(!validId(id)||!validId(mediaId))throw new TemplateError('validation','图片标识无效');
 const accessToken=token();if(!accessToken)throw new TemplateError('authentication','登录已失效，请重新登录',401);
 let response:Response;try{response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${id}/images/${mediaId}`,{signal,headers:{Authorization:`Bearer ${accessToken}`,'X-Request-ID':crypto.randomUUID()}})}catch{throw new TemplateError('unavailable','无法读取图片')}
 if(!response.ok)throw failure(response.status,'');
 if(response.headers.get('Content-Type')?.split(';')[0]!=='image/png')return invalid();
 const size=Number(response.headers.get('Content-Length'));if(Number.isFinite(size)&&size>5*1024*1024)return invalid();
 const bytes=await response.arrayBuffer();if(bytes.byteLength>5*1024*1024||token()!==accessToken)return invalid();return new Blob([bytes],{type:'image/png'});
}
export async function uploadImage(current:WorkspaceAccess,id:string,bytes:Uint8Array,alt:string,signal?:AbortSignal):Promise<UploadedImage>{
 ensureContext(current);if(!validId(id)||bytes.length<1||bytes.length>5*1024*1024||!boundedText(alt.trim(),512))throw new TemplateError('validation','图片或替代文字无效');
 const accessToken=token();if(!accessToken)throw new TemplateError('authentication','登录已失效，请重新登录',401);
 let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
 let response:Response;try{response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${id}/images`,{method:'POST',signal,headers:{Authorization:`Bearer ${accessToken}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},body:JSON.stringify({alt:alt.trim(),base64_data:btoa(binary)})})}catch{throw new TemplateError('unavailable','图片上传状态未知，请核对后再操作')}
 if(!response.ok)throw failure(response.status,'');if(response.status!==201)return invalid();const raw=await boundedJson(response,8192,'图片回执无效',signal);const value=data(raw);if(!obj(value)||!validId(value.id)||typeof value.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(value.content_hash)||value.content_type!=='image/png'||!Number.isSafeInteger(value.byte_length)||!Number.isSafeInteger(value.width)||!Number.isSafeInteger(value.height)||value.alt!==alt.trim()||token()!==accessToken)return invalid();return value as UploadedImage;
}
