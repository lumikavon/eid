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
export type TemplateFailure='authentication'|'forbidden'|'missing'|'context'|'deprecated'|'idempotency'|'validation'|'unavailable'|'timeout'|'cancelled'|'invalid-response';
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
 if(status===422)return new TemplateError('validation','输入无效，请检查文档名称、文种和知识范围',status);
 return new TemplateError('unavailable','模板服务暂时不可用，请重试',status);
}
async function request(current:WorkspaceAccess,path:string,signal?:AbortSignal,body?:CreateDocument,key?:string):Promise<{status:number;value:unknown}>{
 ensureContext(current);const accessToken=token();if(!accessToken)throw new TemplateError('authentication','登录已失效，请重新登录',401);
 const controller=new AbortController();let timedOut=false;let rejectAbort:(reason:unknown)=>void=()=>{};
 const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const abort=()=>{controller.abort();rejectAbort(new TemplateError(timedOut?'timeout':'cancelled',timedOut?'请求超时，结果可能已经提交；请核对原操作':'请求已取消'))};
 signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>{timedOut=true;abort()},REQUEST_TIMEOUT_MS);
 const consume=async()=>{
  if(signal?.aborted){abort();throw new TemplateError('cancelled','请求已取消')}
  const response=await fetch(`/api/v1/workspaces/${current.workspace_id}${path}`,{method:body?'POST':'GET',signal:controller.signal,headers:{Authorization:`Bearer ${accessToken}`,'X-Request-ID':crypto.randomUUID(),...(body?{'Content-Type':'application/json','Idempotency-Key':key!}:{})},body:body?JSON.stringify(body):undefined});
  if(controller.signal.aborted)throw new TemplateError('cancelled','请求已取消');
  if(!response.ok){let code='';try{const raw=await boundedJson(response,8192,'错误响应无效',controller.signal);if(obj(raw)&&obj(raw.error)&&typeof raw.error.code==='string')code=raw.error.code}catch{/* Keep status-based safe message. */}throw failure(response.status,code)}
  const raw=await boundedJson(response,256*1024,'响应格式无效',controller.signal);
  if(controller.signal.aborted||signal?.aborted||token()!==accessToken)throw new TemplateError('cancelled','请求已取消');
  return {status:response.status,value:data(raw)};
 };
 try{return await Promise.race([consume(),aborted])}catch(error){if(error instanceof TemplateError)throw error;if(timedOut)throw new TemplateError('timeout','请求超时，结果可能已经提交；请核对原操作');if(signal?.aborted)throw new TemplateError('cancelled','请求已取消');throw new TemplateError('unavailable','模板服务暂时不可用，请重试')}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
export async function getTypeCatalog(current:WorkspaceAccess,signal?:AbortSignal):Promise<TypeCatalog>{const value=(await request(current,'/document-types',signal)).value;if(!obj(value)||!Array.isArray(value.types)||!Array.isArray(value.knowledge_scopes))return invalid();const types=value.types.map(x=>{if(!obj(x)||!choice(x.id,documentTypeIds)||!boundedText(x.label,128)||x.workflow_state!=='catalog_only')return invalid();return x as TypeItem});const scopes=value.knowledge_scopes.map(x=>{if(!obj(x)||!choice(x.id,knowledgeScopeIds)||!boundedText(x.label,128)||typeof x.available!=='boolean')return invalid();return x as KnowledgeScopeItem});if(new Set(types.map(x=>x.id)).size!==documentTypeIds.length||new Set(scopes.map(x=>x.id)).size!==knowledgeScopeIds.length)return invalid();return {types,knowledge_scopes:scopes}}
export async function getTemplates(current:WorkspaceAccess,filters:TemplateFilters={},signal?:AbortSignal):Promise<TemplateCard[]>{const query=new URLSearchParams();if(filters.scope)query.set('scope',filters.scope);if(filters.query?.trim())query.set('query',filters.query.trim());if(filters.category)query.set('category',filters.category);if(filters.document_type)query.set('document_type',filters.document_type);const value=(await request(current,`/templates${query.size?'?'+query:''}`,signal)).value;if(!obj(value)||!Array.isArray(value.items))return invalid();const items=value.items.map(card);if(items.some(x=>filters.scope&&x.scope!==filters.scope||filters.document_type&&x.document_type!==filters.document_type||filters.category&&x.category!==filters.category)||new Set(items.map(x=>x.version_id)).size!==items.length)return invalid();return items}
export async function getTemplateDetail(current:WorkspaceAccess,versionId:string,signal?:AbortSignal):Promise<TemplateDetail>{if(!validId(versionId))throw new TemplateError('validation','模板版本标识无效');const value=(await request(current,`/templates/${versionId}`,signal)).value;const item=card(value);if(item.version_id!==versionId||!obj(value)||!obj(value.structure)||!Array.isArray(value.structure.sections)||value.structure.sections.length!==item.outline.length||value.structure.sections.some((x,i)=>!obj(x)||x.title!==item.outline[i]))return invalid();return value as TemplateDetail}
export function validateCreate(input:CreateDocument){const name=input.name.trim();if(!boundedText(name,256)||!choice(input.document_type,documentTypeIds)||!choice(input.knowledge_scope,knowledgeScopeIds)||!validId(input.template_version_id))throw new TemplateError('validation','请输入有效名称、文种和知识范围');return {...input,name}}
function document(value:unknown,current:WorkspaceAccess,id?:string):DocumentData{if(!obj(value)||!validId(value.id)||id&&value.id!==id||value.workspace_id!==current.workspace_id||!boundedText(value.name,256)||!choice(value.document_type,documentTypeIds)||!choice(value.knowledge_scope,knowledgeScopeIds)||!validId(value.template_version_id)||!validId(value.version_id)||value.base_version_id!==null&&!validId(value.base_version_id)||typeof value.content_hash!=='string'||!/^[0-9a-f]{64}$/.test(value.content_hash)||!Number.isSafeInteger(value.revision)||Number(value.revision)<1||typeof value.replayed!=='boolean'||!obj(value.ast)||value.ast.schema_version!=='1.0'||!obj(value.ast.document))return invalid();const ast=value.ast.document;if(!obj(ast.metadata)||!Array.isArray(ast.sections)||!Array.isArray(ast.claims)||!Array.isArray(ast.citations)||!obj(ast.review_state)||ast.metadata.title!==value.name||ast.metadata.document_type!==value.document_type||ast.metadata.knowledge_scope!==value.knowledge_scope||ast.metadata.template_version_id!==value.template_version_id||ast.sections.some(x=>!obj(x)||!validId(x.id)||!boundedText(x.title,256)||!Array.isArray(x.blocks)))return invalid();return value as DocumentData}
export async function getDocument(current:WorkspaceAccess,id:string,signal?:AbortSignal):Promise<DocumentData>{if(!validId(id))throw new TemplateError('validation','文档地址无效');return document((await request(current,`/documents/${id}`,signal)).value,current,id)}
export async function createDocument(current:WorkspaceAccess,input:CreateDocument,key:string,signal?:AbortSignal):Promise<DocumentData>{if(!/^[A-Za-z0-9._:-]{1,128}$/.test(key))throw new TemplateError('validation','操作标识无效');const normalized=validateCreate(input);const response=await request(current,'/documents',signal,normalized,key);if(response.status!==201)return invalid();const result=document(response.value,current);if(result.name!==normalized.name||result.document_type!==normalized.document_type||result.knowledge_scope!==normalized.knowledge_scope||result.template_version_id!==normalized.template_version_id)return invalid();return result}
