import {token} from '../auth/oidc';
import {boundedJson} from '../http/bounded-json';
import {validId} from './discovery-api';
import {REQUEST_TIMEOUT_MS} from './api';

export const categories=['generation','retrieval','review','parse_ocr','render','integration'] as const;
export type Category=typeof categories[number];
export const states=['QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED','FAILED','CANCELLED','DEAD_LETTER'] as const;
export type TaskState=typeof states[number];
export type TaskSnapshot={task_id:string;state:TaskState;stage:string;category:Category;operation:string;parent_task_id:string|null;attempt:number;fence_token:number;current_seq:number;retention_floor:number;progress:null;result_ref:string|null;error:string|null;error_class:string|null;next_retry_at:string|null;cancel_requested:boolean;external_effect_state:'none'|'receipt_pending'|'unknown'|'confirmed';created_at:string;updated_at:string;status_url:string;result_url:string|null;can_cancel:boolean;can_retry:boolean;action_reason:'OPERATION_UNAVAILABLE'|'EXTERNAL_EFFECT_UNKNOWN'|'TASK_TERMINAL'|'TASK_NOT_TERMINAL'|null};
export type TaskEvent={task_id:string;seq:number;event_type:string;state:TaskState;occurred_at:string};
export type EventPage={data:TaskEvent[];current_seq:number;retention_floor:number;reset_required:boolean};
export type Notification={notification_id:string;task_id:string;event_seq:number;event_type:string;state:TaskState;created_at:string;read_at:string|null};
export type InventoryResult={result_id:string;task_id:string;workspace_id:string;measured_at:string;scope:'first_authorized_visible_records';limit:number;items:{resource_id:string;kind:'document'|'knowledge'|'reference';revision:number;resource_epoch:number}[];policy_epoch:number[]};
export type Page<T>={data:T[];next_cursor:string|null};
export type TaskFailure='authentication'|'forbidden'|'missing'|'conflict'|'invalid-cursor'|'unavailable'|'invalid-response'|'cancelled';
export class TaskError extends Error{constructor(readonly failure:TaskFailure,message:string,readonly status?:number){super(message);this.name='TaskError'}}
const object=(value:unknown):value is Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const integer=(value:unknown,min=0):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=min;
const choice=<T extends string>(value:unknown,values:readonly T[]):value is T=>typeof value==='string'&&values.includes(value as T);
const utc=(value:unknown)=>typeof value==='string'&&Number.isFinite(Date.parse(value));
const invalid=():never=>{throw new TaskError('invalid-response','任务响应格式无效，请重新读取')};
const stages:Record<TaskState,string>={QUEUED:'waiting',RUNNING:'working',RETRY_WAIT:'retry_wait',SUCCEEDED:'done',BLOCKED:'blocked',FAILED:'failed',CANCELLED:'cancelled',DEAD_LETTER:'dead_letter'};
const errors=['AUTHORIZATION_EXPIRED_OR_REVOKED','DEPENDENCY_BLOCKED','INVALID_INVENTORY_INPUT','TRANSIENT_DEPENDENCY','FORMAT_REPAIRABLE','LEASE_EXPIRED','ATTEMPTS_EXHAUSTED','CANCELLED_BY_ACTOR','OUTBOX_POISONED'] as const;
const errorClasses=['TRANSIENT','FORMAT','PERMANENT','LEASE_EXPIRED','ATTEMPTS_EXHAUSTED'] as const;
function data(raw:unknown):unknown{if(!object(raw)||!Object.hasOwn(raw,'data'))return invalid();return raw.data}
function snapshot(value:unknown,workspaceId:string,taskId?:string):TaskSnapshot{
 if(!object(value)||!validId(value.task_id)||(taskId&&value.task_id!==taskId)||!choice(value.state,states)||!choice(value.category,categories)||value.stage!==(value.state==='RUNNING'&&value.operation==='inventory'&&value.category==='integration'?'inventory':stages[value.state])||typeof value.operation!=='string'||!/^[a-z][a-z0-9_]{0,63}$/.test(value.operation)||(value.parent_task_id!==null&&!validId(value.parent_task_id))||!integer(value.attempt)||!integer(value.fence_token)||!integer(value.current_seq,1)||!integer(value.retention_floor,1)||value.retention_floor>value.current_seq||value.progress!==null||(value.result_ref!==null&&!validId(value.result_ref))||(value.error!==null&&!choice(value.error,errors))||(value.error_class!==null&&!choice(value.error_class,errorClasses))||(value.next_retry_at!==null&&!utc(value.next_retry_at))||typeof value.cancel_requested!=='boolean'||!choice(value.external_effect_state,['none','receipt_pending','unknown','confirmed'])||!utc(value.created_at)||!utc(value.updated_at)||typeof value.can_cancel!=='boolean'||typeof value.can_retry!=='boolean'||(value.action_reason!==null&&!choice(value.action_reason,['OPERATION_UNAVAILABLE','EXTERNAL_EFFECT_UNKNOWN','TASK_TERMINAL','TASK_NOT_TERMINAL'])))return invalid();
 const base=`/api/v1/workspaces/${workspaceId}/tasks/${value.task_id}`;
 const inventory=value.operation==='inventory'&&value.category==='integration';
 if(value.status_url!==base||value.result_url!==(inventory?`${base}/result`:null)||(value.state==='SUCCEEDED')!==(value.result_ref!==null)||(['BLOCKED','FAILED','DEAD_LETTER'].includes(value.state))!==(value.error!==null)||(value.state==='RETRY_WAIT')!==(value.next_retry_at!==null))return invalid();
 return value as TaskSnapshot;
}
function event(value:unknown,taskId:string):TaskEvent{
 if(!object(value)||value.task_id!==taskId||!integer(value.seq,1)||!choice(value.state,states)||!choice(value.event_type,['task.queued','task.running','task.retry_wait','task.succeeded','task.blocked','task.failed','task.cancelled','task.dead_letter','task.cancel_requested'])||!utc(value.occurred_at))return invalid();
 return value as TaskEvent;
}
function notification(value:unknown):Notification{
 if(!object(value)||!validId(value.notification_id)||!validId(value.task_id)||!integer(value.event_seq,1)||!choice(value.event_type,['task.succeeded','task.blocked','task.failed','task.cancelled','task.dead_letter'])||!choice(value.state,['SUCCEEDED','BLOCKED','FAILED','CANCELLED','DEAD_LETTER'])||!utc(value.created_at)||(value.read_at!==null&&!utc(value.read_at)))return invalid();
 return value as Notification;
}
function page<T>(raw:unknown,parse:(value:unknown)=>T,after?:string):Page<T>{
 if(!object(raw)||!Array.isArray(raw.data)||raw.data.length>25||(raw.next_cursor!==null&&(!validId(raw.next_cursor)||raw.next_cursor===after||raw.data.length===0)))return invalid();
 return {data:raw.data.map(parse),next_cursor:raw.next_cursor as string|null};
}
const errorMessage:Record<TaskFailure,string>={authentication:'登录已失效，请重新登录',forbidden:'当前任务权限已失效，受保护内容已清除',missing:'目标不存在或已不可访问',conflict:'任务状态已变化，请重新读取', 'invalid-cursor':'分页游标已失效，请从首页重新读取',unavailable:'任务服务暂时不可用，请重试','invalid-response':'任务响应格式无效，请重新读取',cancelled:'请求已取消'};
function failure(response:Response):TaskError{
 const kind:TaskFailure=response.status===401?'authentication':response.status===403?'forbidden':response.status===404?'missing':response.status===409?'conflict':response.status===400||response.status===422?'invalid-cursor':'unavailable';
 return new TaskError(kind,errorMessage[kind],response.status);
}
function path(workspaceId:string,suffix=''){if(!validId(workspaceId))throw new TaskError('invalid-response','工作区地址无效');return `/api/v1/workspaces/${workspaceId}/tasks${suffix}`}
async function request(workspaceId:string,suffix:string,signal?:AbortSignal,method='GET',key?:string):Promise<unknown>{
 const accessToken=token();if(!accessToken)throw new TaskError('authentication',errorMessage.authentication,401);
 const controller=new AbortController();let timedOut=false;
 const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(()=>{timedOut=true;controller.abort()},REQUEST_TIMEOUT_MS);
 try{
  if(signal?.aborted)throw new TaskError('cancelled',errorMessage.cancelled);
  const response=await fetch(path(workspaceId,suffix),{method,signal:controller.signal,cache:'no-store',headers:{Authorization:`Bearer ${accessToken}`,'X-Request-ID':crypto.randomUUID(),...(key?{'Idempotency-Key':key}:{})}});
  if(!response.ok)throw failure(response);
  const raw=await boundedJson(response,256*1024,errorMessage['invalid-response'],controller.signal);
  if(signal?.aborted)throw new TaskError('cancelled',errorMessage.cancelled);
  if(token()!==accessToken)throw new TaskError('authentication','身份已变化，受保护内容需重新验证',401);
  return raw;
 }catch(error){if(error instanceof TaskError)throw error;if(signal?.aborted)throw new TaskError('cancelled',errorMessage.cancelled);if(timedOut)throw new TaskError('unavailable','任务请求超时，请重试');if(error instanceof TypeError)throw new TaskError('unavailable',errorMessage.unavailable);throw new TaskError('invalid-response',errorMessage['invalid-response'])}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
export async function getTasks(workspaceId:string,after?:string,signal?:AbortSignal){if(after&&!validId(after))return invalid();return page(await request(workspaceId,after?`?after=${after}`:'',signal),value=>snapshot(value,workspaceId),after)}
export async function getTask(workspaceId:string,id:string,signal?:AbortSignal){if(!validId(id))return invalid();return snapshot(data(await request(workspaceId,`/${id}`,signal)),workspaceId,id)}
export async function getEventPage(workspaceId:string,id:string,after:number,signal?:AbortSignal):Promise<EventPage>{
 if(!validId(id)||!integer(after))return invalid();const raw=await request(workspaceId,`/${id}/event-page?after=${after}`,signal);
 if(!object(raw)||!Array.isArray(raw.data)||raw.data.length>64||!integer(raw.current_seq,1)||!integer(raw.retention_floor,1)||raw.retention_floor>raw.current_seq||typeof raw.reset_required!=='boolean')return invalid();
 const currentSeq=raw.current_seq as number;const events=raw.data.map(value=>event(value,id));if(events.some((value,index)=>value.seq!==after+index+1||value.seq>currentSeq)||raw.reset_required&&events.length)return invalid();
 return {...raw,data:events} as EventPage;
}
export async function getNotifications(workspaceId:string,after?:string,signal?:AbortSignal){if(after&&!validId(after))return invalid();return page(await request(workspaceId,`/notifications${after?`?after=${after}`:''}`,signal),notification,after)}
export async function getUnreadNotification(workspaceId:string,signal?:AbortSignal):Promise<boolean>{const raw=await request(workspaceId,'/notifications/unread',signal);if(!object(raw)||Object.keys(raw).length!==1||typeof raw.has_unread!=='boolean')return invalid();return raw.has_unread}
export async function getNotification(workspaceId:string,id:string,signal?:AbortSignal){if(!validId(id))return invalid();const item=notification(data(await request(workspaceId,`/notifications/${id}`,signal)));if(item.notification_id!==id)return invalid();return item}
export async function markNotificationRead(workspaceId:string,id:string,signal?:AbortSignal){if(!validId(id))return invalid();const item=notification(data(await request(workspaceId,`/notifications/${id}/read`,signal,'POST')));if(item.notification_id!==id||!item.read_at)return invalid();return item}
export async function openNotification(workspaceId:string,id:string,expectedTaskId:string,signal?:AbortSignal){if(!validId(id)||!validId(expectedTaskId))return invalid();return snapshot(data(await request(workspaceId,`/notifications/${id}/open`,signal,'POST')),workspaceId,expectedTaskId)}
export async function cancelTask(workspaceId:string,id:string,signal?:AbortSignal){if(!validId(id))return invalid();return snapshot(data(await request(workspaceId,`/${id}/cancel`,signal,'POST')),workspaceId,id)}
export async function retryTask(workspaceId:string,id:string,key:string,signal?:AbortSignal){if(!validId(id)||!/^[A-Za-z0-9._:-]{1,128}$/.test(key))return invalid();const child=snapshot(data(await request(workspaceId,`/${id}/retry`,signal,'POST',key)),workspaceId);if(child.parent_task_id!==id)return invalid();return child}
export async function getTaskResult(workspaceId:string,id:string,expectedRef:string,signal?:AbortSignal):Promise<InventoryResult>{
 if(!validId(id)||!validId(expectedRef))return invalid();const result=data(await request(workspaceId,`/${id}/result`,signal));
 if(!object(result)||result.result_id!==expectedRef||result.task_id!==id||result.workspace_id!==workspaceId||result.scope!=='first_authorized_visible_records'||!utc(result.measured_at)||!integer(result.limit,1)||result.limit>50||!Array.isArray(result.items)||result.items.length>result.limit||!Array.isArray(result.policy_epoch)||result.policy_epoch.length!==3||!result.policy_epoch.every(n=>integer(n,1)))return invalid();
 for(const item of result.items){if(!object(item)||!validId(item.resource_id)||!choice(item.kind,['document','knowledge','reference'])||!integer(item.revision,1)||!integer(item.resource_epoch,1))return invalid()}
 return result as InventoryResult;
}

// Fetch keeps the bearer in an Authorization header. Native EventSource cannot do this.
export async function streamTask(workspaceId:string,id:string,after:number,onEvent:(value:TaskEvent)=>Promise<void>|void,onReset:()=>Promise<void>|void,signal:AbortSignal):Promise<void>{
 if(!validId(id)||!integer(after))return invalid();const accessToken=token();if(!accessToken)throw new TaskError('authentication',errorMessage.authentication,401);
 const response=await fetch(path(workspaceId,`/${id}/events`),{signal,cache:'no-store',headers:{Authorization:`Bearer ${accessToken}`,'Last-Event-ID':String(after),'X-Request-ID':crypto.randomUUID(),Accept:'text/event-stream'}});
 if(!response.ok)throw failure(response);
 if(!response.headers.get('content-type')?.toLowerCase().startsWith('text/event-stream')||!response.body) return invalid();
 const reader=response.body.getReader();const decoder=new TextDecoder('utf-8',{fatal:true});let pending='';let bytes=0;
 try{while(true){const {done,value}=await reader.read();if(signal.aborted)throw new TaskError('cancelled',errorMessage.cancelled);if(token()!==accessToken)throw new TaskError('authentication','身份已变化，受保护内容需重新验证',401);if(done)break;
	  bytes+=value.byteLength;if(bytes>1024*1024)return invalid();pending=(pending+decoder.decode(value,{stream:true})).replaceAll('\r\n','\n');
	  let boundary:number;while((boundary=pending.indexOf('\n\n'))>=0){if(boundary>16384)return invalid();const frame=pending.slice(0,boundary).replaceAll('\r','');pending=pending.slice(boundary+2);if(!frame||frame.startsWith(':'))continue;
   const lines=frame.split('\n');const kind=lines.find(line=>line.startsWith('event: '))?.slice(7);const body=lines.find(line=>line.startsWith('data: '))?.slice(6);
   if(kind==='reset_required'){await onReset();return}if(kind!=='task'||!body)return invalid();
   const idLine=lines.find(line=>line.startsWith('id: '))?.slice(4);let parsed:unknown;try{parsed=JSON.parse(body)}catch{return invalid()}
   const item=event(parsed,id);if(String(item.seq)!==idLine)return invalid();await onEvent(item);
	  }if(pending.length>16384)return invalid();
 }}catch(error){if(signal.aborted)throw new TaskError('cancelled',errorMessage.cancelled);if(error instanceof TaskError)throw error;throw new TaskError('unavailable',errorMessage.unavailable)}finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
}
