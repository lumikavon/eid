import type {WorkspaceAccess} from '../../app/access-api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import {document,type DocumentData} from '../templates/template-api';

export type Claim={id:string;document_version_id:string;section_id:string;block_id:string;start_offset:number;end_offset:number;statement:string;claim_type:string;conditions:string;value:string;unit:string;critical:boolean;status:'supported'|'partially_supported'|'conflicting'|'unsupported'|'unknown';needs_review:boolean};
export type Trace={claim_id:string;state:'current'|'needs_review';links:{id:string;relation:'supports'|'conflicts'|'contextual';quoted_text:string;source_id:string;version:string;locator:string;chunk_hash:string;can_cite:boolean}[]};
export type Bookmark={base_version_id:string;revision:number;section_id:string;block_id:string;start_offset:number;end_offset:number;selected_text:string};
const id=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
async function call(current:WorkspaceAccess,documentId:string,path:string,signal:AbortSignal,body?:unknown):Promise<unknown>{
 if(!id.test(documentId))throw Error('文档标识无效');const access=token();if(!access)throw Error('登录已失效');
 const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${documentId}${path}`,{method:body?'POST':'GET',signal,headers:{Authorization:`Bearer ${access}`,'X-Request-ID':crypto.randomUUID(),...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
 if(!response.ok)throw Error(response.status===409?'版本、选区或来源已变化；请重新选择正文':response.status===403||response.status===404?'来源失权或已失效；受控摘录已清空':'Claim 操作不可用；请重新核对');
 const value=await boundedJson(response,1024*1024,'Claim 响应无效',signal) as {data?:unknown};
 if(signal.aborted||access!==token()||!value||typeof value!=='object'||!value.data)throw Error('授权状态已变化');return value.data;
}
export async function getClaims(current:WorkspaceAccess,documentId:string,signal:AbortSignal):Promise<{version_id:string;revision:number;items:Claim[]}>{
 const value=await call(current,documentId,'/claims',signal) as {version_id:string;revision:number;items:Claim[]};
 if(!Number.isSafeInteger(value.revision)||value.revision<1||!id.test(value.version_id)||!Array.isArray(value.items)||value.items.length>2048||value.items.some(x=>!id.test(x.id)||!id.test(x.block_id)||typeof x.statement!=='string'))throw Error('Claim 响应无效');return value;
}
export async function getTrace(current:WorkspaceAccess,documentId:string,claimId:string,signal:AbortSignal):Promise<Trace>{
 const value=await call(current,documentId,`/claims/${claimId}/trace`,signal) as Trace;
 if(value.claim_id!==claimId||!Array.isArray(value.links)||value.links.length>30||value.links.some(x=>!id.test(x.id)||typeof x.quoted_text!=='string'||typeof x.can_cite!=='boolean'))throw Error('来源追溯无效');return value;
}
export async function extractClaims(current:WorkspaceAccess,documentId:string,signal:AbortSignal){return call(current,documentId,'/claims/extract',signal,{})}
export async function declareClaim(current:WorkspaceAccess,documentId:string,body:Bookmark&{claim_type:string;conditions:string;value:string;unit:string;critical:boolean},signal:AbortSignal){
 const command=Object.fromEntries(Object.entries(body).filter(([key])=>key!=='selected_text'));return call(current,documentId,'/claims',signal,command);
}
export async function bindClaim(current:WorkspaceAccess,documentId:string,claimId:string,body:{base_version_id:string;revision:number;pack_id:string;item_ordinal:number;relation:'supports'|'conflicts'|'contextual';quoted_text:string},signal:AbortSignal){return call(current,documentId,`/claims/${claimId}/links`,signal,body)}
export async function citeClaim(current:WorkspaceAccess,documentId:string,body:Bookmark&{claim_id:string;link_id:string;quoted_text:string},signal:AbortSignal):Promise<DocumentData>{
  return document(await call(current,documentId,'/citations',signal,body),current,documentId);
}
export async function citeRequirement(current:WorkspaceAccess,documentId:string,body:{base_version_id:string;revision:number;section_id:string;block_id:string;claim_id:string;link_id:string;quoted_text:string},signal:AbortSignal):Promise<DocumentData>{
 return document(await call(current,documentId,'/requirements/citations',signal,body),current,documentId);
}
