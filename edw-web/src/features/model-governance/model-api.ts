import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import type {WorkspaceAccess} from '../../app/access-api';

type Policy={id:string;version:number;provider:'internal'|'external';model_id:string;prompt_ref:string;prompt_sha256:string;capabilities:string[];max_classification:number;max_context_chars:number;max_output_tokens:number;daily_token_budget:number;max_cost_micros:number;timeout_seconds:number;redact_rules:string[];external_l2_exception:boolean;created_at:string};
export type PolicyView={revision:number;active:Policy|null};
export class ModelError extends Error{constructor(message:string,public status:number){super(message)}}
const id=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
export async function getModelPolicy(current:WorkspaceAccess,signal?:AbortSignal):Promise<PolicyView>{
 if(!id.test(current.workspace_id))throw new ModelError('工作区无效',422);
 const access=token();if(!access)throw new ModelError('请重新登录',401);
 const controller=new AbortController();const stop=()=>controller.abort();signal?.addEventListener('abort',stop,{once:true});
 const timer=setTimeout(stop,8000);
 try{
  const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/model-governance/policy`,{signal:controller.signal,headers:{Authorization:`Bearer ${access}`,'X-Request-ID':crypto.randomUUID()},cache:'no-store'});
  if(!response.ok)throw new ModelError(response.status===403?'当前账户无模型配置权限':'模型配置暂不可用',response.status);
  const raw=await boundedJson(response,8192,'模型配置回执无效',controller.signal);
  if(token()!==access||signal?.aborted)throw new ModelError('当前授权已变化',409);
  if(!object(raw)||!object(raw.data)||!Number.isSafeInteger(raw.data.revision)||Number(raw.data.revision)<0)return Promise.reject(new ModelError('模型配置回执无效',503));
  const value=raw.data;
  if(value.active!==null&&(!object(value.active)||!id.test(String(value.active.id))||typeof value.active.model_id!=='string'||typeof value.active.provider!=='string'))throw new ModelError('模型配置回执无效',503);
  return value as PolicyView;
 }catch(error){if(error instanceof ModelError)throw error;throw new ModelError('模型配置暂不可用',503)}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',stop)}
}
