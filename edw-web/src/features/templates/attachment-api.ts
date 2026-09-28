import type {WorkspaceAccess} from '../../app/access-api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import {TemplateError} from './template-api';

export type Attachment={id:string;sha256:string;kind:'pdf'|'docx'|'xlsx'|'png'|'jpeg';byte_length:number;classification?:number;retention?:'formal'|'quarantine';created_at?:string;updated_at?:string;parser_version?:string;state:'QUEUED'|'RUNNING'|'PARTIAL'|'SUCCEEDED'|'FAILED'|'BLOCKED';error_code?:string|null};
export type AttachmentDetail=Attachment&{pages:{page_number:number;section:string;state:'PARSED'|'OCR'|'FAILED';error_code:string|null}[];chunks:{page_number:number;ordinal:number;locator:string;content:string;content_hash:string}[]};
export type AttachmentJob={id:string;document_id:string;state:Attachment['state'];error_code:string|null;attempt:number;created_at:string;updated_at:string};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const object=(x:unknown):x is Record<string,unknown>=>!!x&&typeof x==='object'&&!Array.isArray(x);
const invalid=():never=>{throw new TemplateError('invalid-response','附件响应无效；请重新核对当前授权')};
const valid=(x:unknown):x is Attachment=>object(x)&&typeof x.id==='string'&&uuid.test(x.id)&&typeof x.sha256==='string'&&/^[0-9a-f]{64}$/.test(x.sha256)&&['pdf','docx','xlsx','png','jpeg'].includes(String(x.kind))&&Number.isSafeInteger(x.byte_length)&&Number(x.byte_length)>0&&['QUEUED','RUNNING','PARTIAL','SUCCEEDED','FAILED','BLOCKED'].includes(String(x.state));
const base=(current:WorkspaceAccess,documentId:string)=>{
 if(!uuid.test(current.workspace_id)||!uuid.test(documentId))throw new TemplateError('validation','附件目标无效');
 return `/api/v1/workspaces/${current.workspace_id}/documents/${documentId}/attachments`;
};
async function request(current:WorkspaceAccess,documentId:string,suffix:string,signal?:AbortSignal,body?:File):Promise<unknown>{
 const access=token();if(!access)throw new TemplateError('authentication','请重新登录',401);
 const controller=new AbortController();let timedOut=false;const timer=setTimeout(()=>{timedOut=true;controller.abort()},30000);
 const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});
 try{
  let headers:Record<string,string>={Authorization:`Bearer ${access}`,'X-Request-ID':crypto.randomUUID()};
  if(body){if(body.size<1||body.size>10*1024*1024)throw new TemplateError('validation','附件大小必须在 10 MB 以内');
   const digest=await crypto.subtle.digest('SHA-256',await body.arrayBuffer());
   headers={...headers,'Content-Type':body.type,'X-Content-SHA256':Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')};}
  const response=await fetch(base(current,documentId)+suffix,{method:body?'POST':'GET',headers,body,signal:controller.signal});
  if(!response.ok){const failure=response.status===401?'authentication':response.status===403?'forbidden':response.status===404?'missing':response.status===422||response.status===413?'validation':'unavailable';throw new TemplateError(failure,`附件操作未完成 (${response.status})`,response.status)}
  const value=await boundedJson(response,1024*1024,'附件响应无效',controller.signal);
  if(controller.signal.aborted||token()!==access)return invalid();
  if(!object(value))return invalid();return value.data;
 }catch(error){if(error instanceof TemplateError)throw error;throw new TemplateError(timedOut?'timeout':'unavailable','附件操作结果未知；请刷新当前列表核对')}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
export async function listAttachmentJobs(current:WorkspaceAccess,signal?:AbortSignal):Promise<{data:AttachmentJob[];limited:boolean}>{ 
 const access=token();if(!access)throw new TemplateError('authentication','请重新登录',401);
 const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/attachment-jobs`,{
  headers:{Authorization:`Bearer ${access}`,'X-Request-ID':crypto.randomUUID()},signal});
 if(!response.ok)throw new TemplateError(response.status===401?'authentication':response.status===403?'forbidden':response.status===404?'missing':'unavailable','附件任务不可读取',response.status);
 const value=await boundedJson(response,1024*1024,'附件任务响应无效',signal);
 if(signal?.aborted||token()!==access||!object(value)||typeof value.limited!=='boolean'||!Array.isArray(value.data)||value.data.length>25||
  value.data.some((row:unknown)=>!object(row)||typeof row.id!=='string'||!uuid.test(row.id)||
   typeof row.document_id!=='string'||!uuid.test(row.document_id)||
   !['QUEUED','RUNNING','PARTIAL','SUCCEEDED','FAILED','BLOCKED'].includes(String(row.state))||
   !Number.isSafeInteger(row.attempt)||Number(row.attempt)<0||Number(row.attempt)>3||
   !(row.error_code===null||typeof row.error_code==='string'&&/^[A-Z_]{1,64}$/.test(row.error_code))||
   typeof row.created_at!=='string'||!Number.isFinite(Date.parse(row.created_at))||
   typeof row.updated_at!=='string'||!Number.isFinite(Date.parse(row.updated_at))))return invalid();
 return {data:value.data as AttachmentJob[],limited:value.limited};
}
export async function listAttachments(current:WorkspaceAccess,id:string,signal?:AbortSignal):Promise<Attachment[]>{
 const data=await request(current,id,'',signal);if(!Array.isArray(data)||data.length>100||!data.every(valid))return invalid();return data;
}
export async function uploadAttachment(current:WorkspaceAccess,id:string,file:File,signal?:AbortSignal):Promise<Attachment>{
 const data=await request(current,id,'',signal,file);if(!valid(data))return invalid();return data;
}
export async function inspectAttachment(current:WorkspaceAccess,id:string,attachmentId:string,signal?:AbortSignal):Promise<AttachmentDetail>{
 if(!uuid.test(attachmentId))return invalid();const data=await request(current,id,`/${attachmentId}`,signal);
 if(!valid(data))return invalid();
 const pages:unknown=(data as Record<string,unknown>).pages;const chunks:unknown=(data as Record<string,unknown>).chunks;
 if(!Array.isArray(pages)||!Array.isArray(chunks)||pages.length>500||chunks.length>1000||
  pages.some((p:unknown)=>!object(p)||!Number.isSafeInteger(p.page_number)||!['PARSED','OCR','FAILED'].includes(String(p.state))||typeof p.section!=='string')||
  chunks.some((c:unknown)=>!object(c)||!Number.isSafeInteger(c.page_number)||!Number.isSafeInteger(c.ordinal)||typeof c.locator!=='string'||typeof c.content!=='string'))return invalid();
 return data as AttachmentDetail;
}
