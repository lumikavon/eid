import {token} from '../auth/oidc';
import {boundedJson} from '../http/bounded-json';
import {AccountRequestError,REQUEST_TIMEOUT_MS} from './api';

export type WorkspaceAccess={workspace_id:string;name:string;slug:string;actor_id:string;display_name:string;department:string;roles:string[];clearance:number;policy_epoch:number[];operations:string[]};
export type WorkspacePage={workspaces:WorkspaceAccess[];next_cursor:string|null};
export type Member={identity_id:string;display_name:string;active:boolean;roles:string[];project_scope:string[];customer_scope:string[];product_scope:string[];department_scope:string[];owner_scope:'self'|'any';approval_states:string[];clearance:number;valid_from:string;valid_until:string|null};
export type MemberList={members:Member[];policy_epoch:number[];next_cursor:string|null};
export const roles:Record<string,string>={author:'作者',expert:'专家',quality:'质量人员',template_admin:'模板管理员',knowledge_admin:'知识管理员',approver:'审批人',system_admin:'系统管理员'};
const object=(value:unknown):value is Record<string,unknown>=>typeof value==='object'&&value!==null&&!Array.isArray(value);
const strings=(value:unknown):value is string[]=>Array.isArray(value)&&value.every(x=>typeof x==='string');
const epoch=(value:unknown):value is number[]=>Array.isArray(value)&&value.length===3&&value.every(x=>Number.isSafeInteger(x)&&x>0);
const nextCursor=(value:unknown,after?:string)=>value===null||(typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)&&(!after||value>after));

async function request(path:string,method='GET',body?:unknown,maxBytes=64*1024):Promise<unknown>{
 const accessToken=token();if(!accessToken)throw new AccountRequestError('请重新登录','authentication',401);
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
 try{
  const response=await fetch(`/api/v1/access${path}`,{method,signal:controller.signal,headers:{Authorization:`Bearer ${accessToken}`,'X-Request-ID':crypto.randomUUID(),...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
  if(response.status===401)throw new AccountRequestError('登录已失效，请重新登录','authentication',401);
  if(response.status===403)throw new AccountRequestError('当前权限不允许此访问，受保护内容已清除','forbidden',403);
  if(response.status===409)throw new AccountRequestError('权限已变化，请刷新后重新确认','transient',409);
  if(response.status===422)throw new AccountRequestError('输入格式无效，请检查范围（每项1–128字符）、角色、密级及带时区的生效/失效时间','validation',422);
  if(!response.ok)throw new AccountRequestError('权限服务暂时不可用，请重试','transient',response.status);
  const result=await boundedJson(response,maxBytes,'权限响应格式无效');
  if(!object(result)||!('data' in result))throw new Error('权限响应格式无效');
  return result.data;
 }catch(error){
  if(error instanceof AccountRequestError)throw error;
  throw new AccountRequestError(controller.signal.aborted?'权限请求超时，请重试':'权限响应不可用，请重试','transient');
 }finally{clearTimeout(timer)}
}

function workspace(value:unknown):WorkspaceAccess{
 if(!object(value)||!['workspace_id','name','slug','actor_id','display_name','department'].every(k=>typeof value[k]==='string')||!strings(value.roles)||!strings(value.operations)||!epoch(value.policy_epoch)||!Number.isInteger(value.clearance)||Number(value.clearance)<0||Number(value.clearance)>3)throw new AccountRequestError('权限响应格式无效','invalid-response');
 return value as WorkspaceAccess;
}
export async function getWorkspaces(cursor?:string):Promise<WorkspacePage>{
  const value=await request(`/workspaces${cursor?'?after='+encodeURIComponent(cursor):''}`);
  if(!object(value)||!Array.isArray(value.workspaces)||value.workspaces.length>50||
    !nextCursor(value.next_cursor,cursor))throw new Error('项目响应格式无效');
  return {workspaces:value.workspaces.map(workspace),next_cursor:value.next_cursor as string|null};
}
export async function getWorkspace(id:string):Promise<WorkspaceAccess>{return workspace(await request(`/workspaces/${encodeURIComponent(id)}`))}
export async function getMembers(id:string,after?:string):Promise<MemberList>{
 const value=await request(`/workspaces/${encodeURIComponent(id)}/members${after?'?after='+encodeURIComponent(after):''}`,'GET',undefined,256*1024);
 if(!object(value)||!epoch(value.policy_epoch)||!Array.isArray(value.members)||value.members.length>50)throw new Error('成员响应格式无效');
 if(!nextCursor(value.next_cursor,after))throw new Error('成员响应格式无效');
 for(const row of value.members){
  if(!object(row)||typeof row.identity_id!=='string'||typeof row.display_name!=='string'||typeof row.active!=='boolean'||!['roles','project_scope','customer_scope','product_scope','department_scope','approval_states'].every(k=>strings(row[k]))||!['self','any'].includes(String(row.owner_scope))||!Number.isInteger(row.clearance)||Number(row.clearance)<0||Number(row.clearance)>3||typeof row.valid_from!=='string'||(row.valid_until!==null&&typeof row.valid_until!=='string'))throw new Error('成员响应格式无效');
 }
 return value as MemberList;
}
export async function saveMember(id:string,member:Member,expected_epoch:number[]){
 const {identity_id,...value}=member;
 const body=Object.fromEntries(Object.entries(value).filter(([key])=>['active','roles','project_scope','customer_scope','product_scope','department_scope','owner_scope','approval_states','clearance','valid_from','valid_until'].includes(key)));
 const result=await request(`/workspaces/${encodeURIComponent(id)}/members/${encodeURIComponent(identity_id)}`,'PUT',{...body,expected_epoch});
 if(!object(result)||typeof result.audit_id!=='string'||!Number.isSafeInteger(result.workspace_epoch))throw new Error('保存结果未知，请刷新权限后核对');
 return result;
}
export async function getResource(workspaceId:string,resourceId:string){
 const result=await request(`/workspaces/${encodeURIComponent(workspaceId)}/resources/${encodeURIComponent(resourceId)}`);
 if(!object(result)||typeof result.id!=='string'||result.id.toLowerCase()!==resourceId.toLowerCase()||typeof result.title!=='string'||typeof result.kind!=='string')throw new Error('资源响应格式无效');
 return result as {id:string;title:string;kind:string};
}
