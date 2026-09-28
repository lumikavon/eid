import type {WorkspaceAccess} from '../../app/access-api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';

export type Category='all'|'attachment'|'enterprise'|'golden';
export type Governance={assertion_id:string;authority:number;authority_label:string;conflict_id?:string|null;effective_from:string;effective_until:string|null};
export type Hit={chain:'attachment'|'enterprise';category:Category;source_id:string;document_id?:string;version:string;chunk_hash:string;page?:number;ordinal?:number;locator:string;excerpt:string;classification:number;keyword_version:string;embedding_version:string|null;keyword_match?:boolean;semantic_score?:number|null;rerank_score?:number;reranker_version?:string;policy:string;valid_until?:string;project_id?:string;product_id?:string|null;customer_id?:string|null;governance?:Governance[]};
export type SearchResult={items:Hit[];chains:Record<'keyword'|'semantic'|'rerank'|'enterprise'|'golden','available'|'unavailable'>;complete:false;limited:boolean;scope:string;retrieval_version:string;policy_epoch:number[]};
export type SearchInput={query:string;context_document_id:string;context_version_id?:string;source_sha256?:string;classification?:number;category:Category;limit:number};
export class KnowledgeError extends Error{constructor(readonly failure:'authentication'|'forbidden'|'unavailable'|'invalid',message:string){super(message)}}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const obj=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const validHit=(x:unknown):x is Hit=>obj(x)&&['attachment','enterprise'].includes(String(x.chain))&&typeof x.source_id==='string'&&typeof x.version==='string'&&
 typeof x.chunk_hash==='string'&&/^[0-9a-f]{64}$/.test(x.chunk_hash)&&typeof x.locator==='string'&&x.locator.length>0&&x.locator.length<=512&&typeof x.excerpt==='string'&&x.excerpt.length>0&&x.excerpt.length<=4000&&
 Number.isInteger(x.classification)&&Number(x.classification)>=0&&Number(x.classification)<=3&&typeof x.policy==='string'&&typeof x.keyword_version==='string'&&
 (x.embedding_version===null||typeof x.embedding_version==='string')&&
 (x.chain==='enterprise'||typeof x.document_id==='string'&&uuid.test(x.document_id)&&Number.isInteger(x.page)&&Number.isInteger(x.ordinal));
export type ConflictView={id:string;revision:number;status:string;sides:({state:'forbidden'}|{state:'current';id:string;chain:string;source_id:string;version:string;locator:string;statement:string;value:string;unit:string;conditions:string;authority:number;authority_label:string;effective_until:string|null})[];history:{revision:number;status:string;reason:string;actor_id:string;decided_at:string}[]};
async function governanceRequest(current:WorkspaceAccess,path:string,body:unknown,signal:AbortSignal,method:'GET'|'POST'='POST'){
 const access=token();if(!access)throw new KnowledgeError('authentication','请重新登录');
 const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/knowledge/${path}`,{method,signal,headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},...(method==='POST'?{body:JSON.stringify(body)}:{})});
 if(!response.ok)throw new KnowledgeError(response.status===401?'authentication':response.status===404||response.status===403?'forbidden':'unavailable','来源或当前权限已失效');
 const reply=await boundedJson(response,64*1024,'来源响应无效',signal);
 if(signal.aborted||access!==token()||!obj(reply)||!obj(reply.data))throw new KnowledgeError('invalid','来源已失效');
 return reply.data;
}
export async function inspectConflict(current:WorkspaceAccess,id:string,context:string,signal:AbortSignal):Promise<ConflictView>{
 if(!uuid.test(id)||!uuid.test(context))throw new KnowledgeError('invalid','来源无效');
 const data=await governanceRequest(current,`conflicts/${id}?context_document_id=${context}`,null,signal,'GET');
 if(!Array.isArray(data.sides)||data.sides.length!==2||!data.sides.every((s:unknown)=>obj(s)&&['forbidden','current'].includes(String(s.state)))||!Array.isArray(data.history)||!Number.isSafeInteger(data.revision))throw new KnowledgeError('invalid','来源响应无效');
 return data as ConflictView;
}
export async function decideConflict(current:WorkspaceAccess,id:string,body:unknown,signal:AbortSignal):Promise<ConflictView>{
 return await governanceRequest(current,`conflicts/${id}/dispositions`,body,signal) as ConflictView;
}
export async function registerAssertion(current:WorkspaceAccess,body:unknown,signal:AbortSignal):Promise<string>{
 const data=await governanceRequest(current,'assertions',body,signal);
 if(typeof data.assertion_id!=='string'||!uuid.test(data.assertion_id))throw new KnowledgeError('invalid','登记响应无效');
 return data.assertion_id as string;
}
export async function searchKnowledge(current:WorkspaceAccess,input:SearchInput,signal:AbortSignal):Promise<SearchResult>{
 if(!uuid.test(input.context_document_id)||!input.query.trim()||input.query.length>128)throw new KnowledgeError('invalid','请输入有效的文档范围和查询');
 const access=token();if(!access)throw new KnowledgeError('authentication','请重新登录');
 const controller=new AbortController();const abort=()=>controller.abort();signal.addEventListener('abort',abort,{once:true});const timeout=setTimeout(()=>controller.abort(),10000);
 try{
  const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/knowledge/search`,{method:'POST',signal:controller.signal,
   headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},body:JSON.stringify(input)});
  if(!response.ok)throw new KnowledgeError(response.status===401?'authentication':response.status===403||response.status===404?'forbidden':'unavailable','检索失败；来源可能已失效，请重新核对当前权限');
  const body=await boundedJson(response,256*1024,'检索响应无效',controller.signal);
  if(controller.signal.aborted||signal.aborted||access!==token()||!obj(body)||!obj(body.data))throw new KnowledgeError('invalid','检索已失效');
  const data=body.data;if(!Array.isArray(data.items)||data.items.length>20||!data.items.every(validHit)||!obj(data.chains)||data.complete!==false||typeof data.limited!=='boolean'||!Array.isArray(data.policy_epoch)||data.policy_epoch.length!==3||data.policy_epoch.some((n:unknown)=>!Number.isSafeInteger(n))||typeof data.scope!=='string'||typeof data.retrieval_version!=='string')throw new KnowledgeError('invalid','检索响应无效');
  if(data.items.some((item:Hit)=>item.governance!==undefined&&(!Array.isArray(item.governance)||item.governance.some(g=>!Number.isInteger(g.authority)||g.authority<1||g.authority>8||!uuid.test(g.assertion_id)))))throw new KnowledgeError('invalid','治理元数据无效');
  return data as SearchResult;
 }catch(error){if(error instanceof KnowledgeError)throw error;throw new KnowledgeError('unavailable','检索链路暂不可用，请重新核对')}
 finally{clearTimeout(timeout);signal.removeEventListener('abort',abort)}
}
