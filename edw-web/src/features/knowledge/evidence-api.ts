import type {WorkspaceAccess} from '../../app/access-api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';

export type EvidenceHit={chain:'attachment'|'enterprise';source_id:string;document_id?:string;version:string;chunk_hash:string;locator:string;page?:number;ordinal:number;excerpt:string;queries:string[];governance?:{authority:number;conflict_id?:string|null}[];semantic_score?:number|null;rerank_score?:number|null};
export function evidenceOrdinal(hit:EvidenceHit):number{
 if(!Number.isInteger(hit.ordinal)||hit.ordinal<1||hit.ordinal>30)throw Error('证据序号无效');
 return hit.ordinal;
}
export type EvidencePack={id:string;snapshot_hash:string;view_hash:string;state:'insufficient';queries:string[];items:EvidenceHit[];chains:unknown[];gaps:string[];version_conflicts:string[];conflict_ids:string[];section_id:string;outline_version_id:string;context_version_id:string;document_version_id:string;policy_hash:string;retrieval_version:string;budget:{queries:number;max_items:number}};
export type EvidenceJob={id:string;state:'QUEUED'|'RUNNING'|'RETRY_WAIT'|'SUCCEEDED'|'BLOCKED'|'FAILED';stage:string;attempt:number;error_code:string|null;pack?:EvidencePack|null};
export type SimilarDoc={document_id:string;version:string;locator:string};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export async function evidenceRequest(current:WorkspaceAccess,documentId:string,path:string,signal:AbortSignal,body?:unknown):Promise<unknown>{
 if(!uuid.test(documentId))throw Error('文档范围无效');const access=token();if(!access)throw Error('请重新登录');
 const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${documentId}/evidence${path}`,{method:body?'POST':'GET',signal,headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},body:body?JSON.stringify(body):undefined});
 if(!response.ok)throw Error(response.status===404||response.status===403?'权限或版本已失效；证据已清除':'证据任务不可用；请重新核对');
 const reply=await boundedJson(response,256*1024,'证据响应无效',signal) as {data?:unknown};
 if(signal.aborted||access!==token()||!reply||typeof reply!=='object'||!reply.data)throw Error('当前授权状态已变化');return reply.data;
}
export async function getEvidenceJob(current:WorkspaceAccess,documentId:string,id:string,signal:AbortSignal):Promise<EvidenceJob>{
 const data=await evidenceRequest(current,documentId,`/jobs/${id}`,signal) as EvidenceJob;
 if(!uuid.test(data.id)||!['QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED','FAILED'].includes(data.state)||data.pack&&(!uuid.test(data.pack.id)||data.pack.state!=='insufficient'||!Array.isArray(data.pack.items)||data.pack.items.length>30||data.pack.items.some(item=>!Number.isInteger(item.ordinal)||item.ordinal<1||item.ordinal>30)||!Array.isArray(data.pack.gaps)||!Array.isArray(data.pack.queries)||data.pack.queries.length<3||data.pack.queries.length>10))throw Error('证据响应无效');return data;
}
export async function requestEvidence(current:WorkspaceAccess,documentId:string,body:unknown,signal:AbortSignal):Promise<EvidenceJob>{
 const data=await evidenceRequest(current,documentId,'/jobs',signal,body) as EvidenceJob;
 if(!uuid.test(data.id))throw Error('任务响应无效');return data;
}
export async function similarDocuments(current:WorkspaceAccess,documentId:string,selection:{section_id:string;outline_version_id:string;context_version_id:string;document_version_id:string},signal:AbortSignal):Promise<{items:SimilarDoc[];limited:boolean}>{ 
 const params=new URLSearchParams(selection);const data=await evidenceRequest(current,documentId,`/similar?${params}`,signal) as {items:SimilarDoc[];limited:boolean};
 if(typeof data.limited!=='boolean'||!Array.isArray(data.items)||data.items.length>5||data.items.some(item=>!uuid.test(item.document_id)||!uuid.test(item.version)||item.locator!==`document:${item.document_id}`))throw Error('相似文档响应无效');return data;
}
