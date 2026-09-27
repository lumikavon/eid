import {token} from '../../auth/oidc';
import {REQUEST_TIMEOUT_MS} from '../../app/api';
import type {WorkspaceAccess} from '../../app/access-api';
import {boundedJson} from '../../http/bounded-json';
import {TemplateError,type DocumentType,type TemplateScope} from './template-api';

export type Section={id:string;title:string;mandatory:boolean};
export type Manifest={schema_version:'1.0';name:string;description:string;category:string;document_type:DocumentType;sections:Section[];rules:Record<string,string|null>;assets:string[]};
export type Preview={manifest:Manifest;manifest_sha256:string;assets:{name:string;source_sha256:string;sha256:string;width:number;height:number}[];formal_ready:false;formal_blockers:string[]};
export type Candidate={id:string;template_id:string;workspace_id:string;version_label:string;scope:TemplateScope;classification:number;base_version_id:string|null;created_at:string;state:'QUEUED'|'RUNNING'|'VALIDATED'|'REJECTED'|'BLOCKED';error_code:string|null;attempt:number;updated_at:string;development_only:true;published_version_id:string|null;head_version_id:string|null;preview:Preview|null};
export type Version={id:string;template_id:string;version_label:string;name:string;scope:TemplateScope;classification:number;structure:{sections:{title:string}[]};status:'active'|'deprecated';rule_refs:Manifest;manifest_sha256:string;candidate_id:string;published_at:string;published_by:string;development_only:true};
export type References={items:{document_id:string;name:string;template_version_id:string}[];next_cursor:string|null;scope:'currently_authorized_documents_only'};
export type CandidateMetadata={template_id?:string;base_version_id?:string;version_label:string;scope:TemplateScope;classification:number};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const hash=/^[0-9a-f]{64}$/;
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const id=(v:unknown):v is string=>typeof v==='string'&&uuid.test(v);
const digest=(v:unknown):v is string=>typeof v==='string'&&hash.test(v);
const invalid=():never=>{throw new TemplateError('invalid-response','治理回执无效；结果未知，请用原操作标识核对')};
const error=(status:number,code:string)=>{
 if(status===401)return new TemplateError('authentication','登录已失效',status);
 if(status===403)return new TemplateError('forbidden','当前不允许管理此模板',status);
 if(status===404)return new TemplateError('missing','模板不可访问或已失权',status);
 if(status===409)return new TemplateError('conflict',code==='IDEMPOTENCY_KEY_REUSED'?'操作标识已用于不同内容':code==='FORMAL_TEMPLATE_NOT_CONFIGURED'?'正式字体、主题及批准规则未配置，禁止正式发布':`治理状态冲突（${code||'请重新读取'}）`,status);
 if(status===413||status===415||status===422)return new TemplateError('validation',`模板包或命令无效（${code||status}）`,status);
 return new TemplateError('unavailable','模板治理暂不可用',status);
};
function context(current:WorkspaceAccess){if(!id(current.workspace_id)||!id(current.actor_id)||current.policy_epoch.length!==3||current.policy_epoch[0]!==current.policy_epoch[2]||!current.policy_epoch.every(x=>Number.isSafeInteger(x)&&x>0))throw new TemplateError('context','权限上下文无效')}
async function call(current:WorkspaceAccess,path:string,method:'GET'|'POST'='GET',body?:BodyInit,key?:string,signal?:AbortSignal){
 context(current);const bearer=token();if(!bearer)throw new TemplateError('authentication','请重新登录',401);
 const controller=new AbortController();let timedOut=false;let rejectAbort:(error:unknown)=>void=()=>{};
 const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const abort=()=>{controller.abort();rejectAbort(new TemplateError(timedOut?'timeout':'cancelled','请求中断；若已提交，请用原操作标识核对'))};
 signal?.addEventListener('abort',abort,{once:true});const timer=setTimeout(()=>{timedOut=true;abort()},REQUEST_TIMEOUT_MS);
 try{
  if(signal?.aborted)abort();
  return await Promise.race([(async()=>{
   const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/template-governance${path}`,{method,body,signal:controller.signal,headers:{Authorization:`Bearer ${bearer}`,'X-Request-ID':crypto.randomUUID(),...(key?{'Idempotency-Key':key}:{}),...(body instanceof Blob?{'Content-Type':'application/zip'}:body?{'Content-Type':'application/json'}:{})}});
   if(!response.ok){let code='';try{const value=await boundedJson(response,8192,'错误无效',controller.signal);if(object(value)&&object(value.error)&&typeof value.error.code==='string')code=value.error.code}catch{/* Status remains authoritative. */}throw error(response.status,code)}
   const value=await boundedJson(response,256*1024,'治理回执无效',controller.signal);
   if(controller.signal.aborted||signal?.aborted||token()!==bearer)return invalid();
   if(!object(value)||!Object.hasOwn(value,'data'))return invalid();
   return {status:response.status,data:value.data};
  })(),aborted]);
 }catch(e){if(e instanceof TemplateError)throw e;throw new TemplateError(timedOut?'timeout':signal?.aborted?'cancelled':'unavailable','请求结果未知，请使用原操作标识核对')}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
function candidate(v:unknown,workspace:string):Candidate{
 if(!object(v)||!id(v.id)||!id(v.template_id)||v.workspace_id!==workspace||typeof v.version_label!=='string'||!['enterprise','department','product_line','project','personal'].includes(String(v.scope))||!Number.isInteger(v.classification)||v.base_version_id!==null&&!id(v.base_version_id)||!['QUEUED','RUNNING','VALIDATED','REJECTED','BLOCKED'].includes(String(v.state))||v.error_code!==null&&typeof v.error_code!=='string'||!Number.isInteger(v.attempt)||v.development_only!==true||v.published_version_id!==null&&!id(v.published_version_id)||v.head_version_id!==null&&!id(v.head_version_id)||typeof v.created_at!=='string'||typeof v.updated_at!=='string')return invalid();
 if(v.preview!==null){const p=v.preview;if(!object(p)||!object(p.manifest)||!digest(p.manifest_sha256)||!Array.isArray(p.manifest.sections)||p.manifest.sections.length<1||p.manifest.sections.length>64||!p.manifest.sections.every(s=>object(s)&&id(s.id)&&typeof s.title==='string'&&typeof s.mandatory==='boolean')||!Array.isArray(p.assets)||p.assets.length>15||!p.assets.every(a=>object(a)&&typeof a.name==='string'&&digest(a.source_sha256)&&digest(a.sha256)&&Number.isInteger(a.width)&&Number.isInteger(a.height))||p.formal_ready!==false||!Array.isArray(p.formal_blockers)||p.formal_blockers.length<1||!p.formal_blockers.every(x=>typeof x==='string'))return invalid()}
 return v as Candidate;
}
function version(v:unknown):Version{if(!object(v)||!id(v.id)||!id(v.template_id)||!id(v.candidate_id)||!id(v.published_by)||!digest(v.manifest_sha256)||v.development_only!==true||!['active','deprecated'].includes(String(v.status))||typeof v.name!=='string'||!v.name||typeof v.version_label!=='string'||!v.version_label||!['enterprise','department','product_line','project','personal'].includes(String(v.scope))||!Number.isInteger(v.classification)||Number(v.classification)<0||Number(v.classification)>3||typeof v.published_at!=='string'||Number.isNaN(Date.parse(v.published_at))||!object(v.structure)||!Array.isArray(v.structure.sections)||v.structure.sections.length<1||!v.structure.sections.every(s=>object(s)&&typeof s.title==='string'&&!!s.title)||!object(v.rule_refs))return invalid();return v as Version}
export async function listCandidates(current:WorkspaceAccess,after?:string,signal?:AbortSignal){if(after&&!id(after))return invalid();const response=await call(current,`/candidates${after?`?after=${after}`:''}`,'GET',undefined,undefined,signal);const v=response.data;if(!object(v)||!Array.isArray(v.items)||v.items.length>100||v.next_cursor!==null&&!id(v.next_cursor))return invalid();return {items:v.items.map(x=>candidate(x,current.workspace_id)),next_cursor:v.next_cursor as string|null}}
export async function getOperation(current:WorkspaceAccess,key:string,signal?:AbortSignal):Promise<{kind:'unresolved'}|{kind:'candidate';candidate:Candidate}|{kind:'version';version:Version}>{
 if(!validKey(key))return invalid();
 const v=(await call(current,`/operations/${encodeURIComponent(key)}`,'GET',undefined,undefined,signal)).data;
 if(!object(v))return invalid();
 if(v.kind==='unresolved'&&Object.keys(v).length===1)return {kind:'unresolved'};
 if(v.kind==='candidate'){const c=candidate(v.candidate,current.workspace_id);return {kind:'candidate',candidate:c}}
 if(v.kind==='version')return {kind:'version',version:version(v.version)};
 return invalid();
}
export async function getCandidate(current:WorkspaceAccess,candidateId:string,signal?:AbortSignal){if(!id(candidateId))return invalid();const v=(await call(current,`/candidates/${candidateId}`,'GET',undefined,undefined,signal)).data;const c=candidate(v,current.workspace_id);if(c.id!==candidateId)return invalid();return c}
const validKey=(key:string)=>/^[A-Za-z0-9._:-]{1,128}$/.test(key);
export async function uploadCandidate(current:WorkspaceAccess,metadata:CandidateMetadata,file:File,key:string,signal?:AbortSignal){if(!validKey(key)||file.size<1||file.size>5*1024*1024||!metadata.version_label||metadata.version_label!==metadata.version_label.trim()||metadata.version_label.length>128||!['enterprise','department','product_line','project','personal'].includes(metadata.scope)||!Number.isInteger(metadata.classification)||metadata.classification<0||metadata.classification>current.clearance||metadata.base_version_id&&!metadata.template_id||metadata.base_version_id&&!id(metadata.base_version_id)||metadata.template_id&&!id(metadata.template_id))throw new TemplateError('validation','请选择不超过 5 MiB 的 ZIP 包并填写版本标签');const params=new URLSearchParams({version_label:metadata.version_label,scope:metadata.scope,classification:String(metadata.classification)});if(metadata.template_id)params.set('template_id',metadata.template_id);if(metadata.base_version_id)params.set('base_version_id',metadata.base_version_id);const response=await call(current,`/candidates?${params}`,'POST',file,key,signal);if(response.status!==201)return invalid();return candidate(response.data,current.workspace_id)}
export async function publishCandidate(current:WorkspaceAccess,candidateId:string,manifestSha:string,key:string,signal?:AbortSignal){if(!id(candidateId)||!digest(manifestSha)||!validKey(key))throw new TemplateError('validation','版本或操作标识无效');const r=await call(current,`/candidates/${candidateId}/publish`,'POST',JSON.stringify({manifest_sha256:manifestSha,mode:'development',confirmed:true}),key,signal);if(r.status!==201)return invalid();const v=version(r.data);if(v.candidate_id!==candidateId||v.manifest_sha256!==manifestSha)return invalid();return v}
export async function getVersion(current:WorkspaceAccess,versionId:string,signal?:AbortSignal){if(!id(versionId))return invalid();const v=version((await call(current,`/versions/${versionId}`,'GET',undefined,undefined,signal)).data);if(v.id!==versionId)return invalid();return v}
export async function deprecateVersion(current:WorkspaceAccess,versionId:string,reason:string,key:string,signal?:AbortSignal){if(!id(versionId)||!validKey(key)||!reason.trim()||reason.length>512)throw new TemplateError('validation','请填写废弃原因');const r=await call(current,`/versions/${versionId}/deprecate`,'POST',JSON.stringify({reason:reason.trim(),confirmed:true}),key,signal);const v=version(r.data);if(v.id!==versionId||v.status!=='deprecated')return invalid();return v}
export async function getReferences(current:WorkspaceAccess,versionId:string,after?:string,signal?:AbortSignal):Promise<References>{if(!id(versionId)||after&&!id(after))return invalid();const v=(await call(current,`/versions/${versionId}/references${after?`?after=${after}`:''}`,'GET',undefined,undefined,signal)).data;if(!object(v)||v.scope!=='currently_authorized_documents_only'||!Array.isArray(v.items)||v.items.length>100||v.next_cursor!==null&&!id(v.next_cursor)||!v.items.every(x=>object(x)&&id(x.document_id)&&typeof x.name==='string'&&x.template_version_id===versionId))return invalid();return v as References}
