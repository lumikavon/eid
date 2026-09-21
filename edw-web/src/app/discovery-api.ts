import {token} from '../auth/oidc';
import {boundedJson} from '../http/bounded-json';
import {AccountRequestError,REQUEST_TIMEOUT_MS} from './api';
import {getWorkspaces} from './access-api';

export const tabs=['recent','created','participating','favorites'] as const;
export const collections=['all','todo','references'] as const;
export const kinds=['document','knowledge','reference'] as const;
export const documentTypes=['technical','proposal','report','manual','other'] as const;
export const lifecycles=['DRAFT','IN_REVIEW','APPROVED','ARCHIVED'] as const;
export type Context={actor_id:string;workspace_id:string;policy_epoch:number[]};
export type Filters={tab?:typeof tabs[number];collection?:typeof collections[number];kind?:typeof kinds[number];document_type?:typeof documentTypes[number];lifecycle?:typeof lifecycles[number];visibility?:'visible'|'recycled';limit?:number;cursor?:string};
export type Item={id:string;workspace_id:string;title:string;kind:typeof kinds[number];document_type:typeof documentTypes[number]|null;lifecycle:typeof lifecycles[number];visibility:'visible'|'recycled';created_by:string;created_at:string;updated_at:string;version_label:string|null;revision:number;resource_epoch:number;favorite:boolean;favorite_revision:number;participating:boolean};
export type Storage={metadata_bytes:number;measured_at:string;scope:'authorized_filtered_record_metadata';definition:'pg_column_size(discovery_record)+pg_column_size(access_resource.title)';visibility:'visible'|'recycled';attachment_bytes:null;quota_bytes:null};
export type Page={items:Item[];total_count:number;next_cursor:string|null;context:Context;storage:Storage};
export const functionRoutes=['documents','favorites','references','recycle','project'] as const;
export type FunctionResult={id:typeof functionRoutes[number];route:typeof functionRoutes[number];title:string;workspace_id:string};
export type SearchPage=Page&{functions:FunctionResult[]};
export type Detail={item:Item;context:Context;resource_context:Context;content_state:'metadata_only';actions:{favorite:boolean;restore:boolean;restore_policy_version:string|null}};
export type FuturePanel={id:'review'|'ai_words'|'quality'|'templates'|'recommendations'|'creation';value:null;state:'not_collected'|'not_evaluated'|'unavailable';reason:string;owner:string};
export type Summary={context:Context;workspace:{id:string;name:string;slug:string;project_id:string;customer_id:string;product_id:string;department:string;classification:number};total_count:number;storage:Storage;week_new_documents:{value:number;window_start:string;window_end:string;definition:'authorized_filtered_documents_created_since_utc_monday'};todo_count:number;last_activity_at:string|null;future_panels:FuturePanel[]};
export type Command={key:string;resourceId:string}&({action:'favorite.set';body:{favorite:boolean;expected_revision:number}}|{action:'restore_visibility';body:{expected_revision:number;policy_version:string}});
export type Receipt={operation_id:string;action:Command['action'];resource_id:string;replayed:boolean;occurred_at:string;context:Context;current:Item};
export type Failure='authentication'|'forbidden'|'context'|'conflict'|'invalid-cursor'|'validation'|'unavailable'|'timeout'|'offline'|'invalid-response'|'cancelled';
export class DiscoveryError extends AccountRequestError{
 constructor(readonly failure:Failure,message:string,status?:number){super(message,failure==='authentication'?'authentication':failure==='forbidden'?'forbidden':failure==='validation'?'validation':failure==='invalid-response'?'invalid-response':'transient',status);this.name='DiscoveryError'}
}
const invalid=():never=>{throw new DiscoveryError('invalid-response','响应格式无效，请重新读取')};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
function shape(v:unknown,keys:string[]):Record<string,unknown>{if(!object(v)||Object.keys(v).length!==keys.length||!keys.every(k=>Object.hasOwn(v,k)))return invalid();return v}
// JSON Schema and Pydantic measure Unicode code points, not UTF-16 code units.
function text(v:unknown,max:number,min=1):v is string{
 if(typeof v!=='string'||v.includes('\0'))return false;
 const length=Array.from(v).length;return length>=min&&length<=max;
}
const integer=(v:unknown,min=0):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=min;
export const validId=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
export function validDiscoveryQuery(search:string):boolean{
 if(search.length>512)return false;
 const params=new URLSearchParams(search);
 const allowed:Record<string,readonly string[]>={tab:tabs,kind:kinds,type:documentTypes,status:lifecycles,collection:collections,from:['home','documents','favorites','references','recycle','search']};
 return params.size<=6&&Array.from(params).every(([key,value])=>params.getAll(key).length===1&&Object.hasOwn(allowed,key)&&allowed[key].includes(value));
}
const choice=<T extends string>(v:unknown,values:readonly T[]):v is T=>typeof v==='string'&&values.includes(v as T);
function utc(v:unknown):v is string{
 if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(v))return false;
 const time=new Date(v);return Number.isFinite(time.getTime())&&time.toISOString().slice(0,19)===v.slice(0,19);
}
const cursor=(v:unknown):v is string=>text(v,2048)&&/^[A-Za-z0-9_-]+$/.test(v);
export const sameContext=(a:Context,b:Context)=>a.actor_id===b.actor_id&&a.workspace_id===b.workspace_id&&a.policy_epoch.length===3&&b.policy_epoch.length===3&&a.policy_epoch.every((v,i)=>v===b.policy_epoch[i]);
function context(v:unknown,expected:Context,resourceEpoch?:number):Context{
 const x=shape(v,['actor_id','workspace_id','policy_epoch']);
 if(!validId(x.actor_id)||!validId(x.workspace_id)||!Array.isArray(x.policy_epoch)||x.policy_epoch.length!==3||!x.policy_epoch.every(n=>integer(n,1)))return invalid();
 const result=x as Context;const wanted=resourceEpoch===undefined?expected:{...expected,policy_epoch:[expected.policy_epoch[0],expected.policy_epoch[1],resourceEpoch]};
 if(!sameContext(result,wanted))throw new DiscoveryError('context','权限上下文已变化，正在重新验证');
 return result;
}
function item(v:unknown,expected:Context,id?:string):Item{
 const x=shape(v,['id','workspace_id','title','kind','document_type','lifecycle','visibility','created_by','created_at','updated_at','version_label','revision','resource_epoch','favorite','favorite_revision','participating']);
 if(!validId(x.id)||!validId(x.workspace_id)||x.workspace_id!==expected.workspace_id||(id!==undefined&&x.id!==id)||!text(x.title,512)||!choice(x.kind,kinds)||(x.document_type!==null&&!choice(x.document_type,documentTypes))||!choice(x.lifecycle,lifecycles)||!choice(x.visibility,['visible','recycled'])||!validId(x.created_by)||!utc(x.created_at)||!utc(x.updated_at)||(x.version_label!==null&&!text(x.version_label,128,0))||!integer(x.revision,1)||!integer(x.resource_epoch,1)||!integer(x.favorite_revision)||typeof x.favorite!=='boolean'||typeof x.participating!=='boolean')return invalid();
 return x as Item;
}
function storage(v:unknown,visibility?:Filters['visibility']):Storage{
 const x=shape(v,['metadata_bytes','measured_at','scope','definition','visibility','attachment_bytes','quota_bytes']);
 if(!integer(x.metadata_bytes)||!utc(x.measured_at)||x.scope!=='authorized_filtered_record_metadata'||x.definition!=='pg_column_size(discovery_record)+pg_column_size(access_resource.title)'||!choice(x.visibility,['visible','recycled'])||(visibility!==undefined&&x.visibility!==visibility)||x.attachment_bytes!==null||x.quota_bytes!==null)return invalid();
 return x as Storage;
}
function page(v:unknown,expected:Context,filters:Filters,search:boolean):Page|SearchPage{
 const x=shape(v,['items','total_count','next_cursor','context','storage',...(search?['functions']:[])]);
 context(x.context,expected);
 if(!Array.isArray(x.items)||x.items.length>(filters.limit??20)||x.items.length>50||!integer(x.total_count)||x.total_count<x.items.length||(x.next_cursor!==null&&(!cursor(x.next_cursor)||x.next_cursor===filters.cursor||x.items.length===0)))return invalid();
 const items=x.items.map(v=>item(v,expected));
 if(new Set(items.map(i=>i.id)).size!==items.length||items.some(i=>i.visibility!==(filters.visibility??'visible')||(filters.kind&&i.kind!==filters.kind)||(filters.document_type&&i.document_type!==filters.document_type)||(filters.lifecycle&&i.lifecycle!==filters.lifecycle)||(filters.tab==='created'&&i.created_by!==expected.actor_id)||(filters.tab==='favorites'&&!i.favorite)||(filters.tab==='participating'&&!i.participating)||(filters.collection==='references'&&i.kind==='document')||(filters.collection==='todo'&&(i.kind!=='document'||i.lifecycle!=='DRAFT'||i.visibility!=='visible'))))return invalid();
 const result:Page={items,total_count:x.total_count,next_cursor:x.next_cursor as string|null,context:expected,storage:storage(x.storage,filters.visibility??'visible')};
 if(!search)return result;
 if(!Array.isArray(x.functions)||x.functions.length>5)return invalid();
 const functions=x.functions.map(v=>{const f=shape(v,['id','route','title','workspace_id']);if(!choice(f.id,functionRoutes)||f.id!==f.route||!text(f.title,128)||f.workspace_id!==expected.workspace_id)return invalid();return f as FunctionResult});
 if(new Set(functions.map(f=>f.id)).size!==functions.length)return invalid();
 return {...result,functions};
}
function detail(v:unknown,expected:Context,id:string):Detail{
 const x=shape(v,['item','context','resource_context','actions','content_state']);context(x.context,expected);
 const record=item(x.item,expected,id);context(x.resource_context,expected,record.resource_epoch);
 const actions=shape(x.actions,['favorite','restore','restore_policy_version']);
 if(x.content_state!=='metadata_only'||typeof actions.favorite!=='boolean'||typeof actions.restore!=='boolean'||(actions.restore_policy_version!==null&&!text(actions.restore_policy_version,128))||(actions.restore&&(!actions.restore_policy_version||record.visibility!=='recycled'||record.kind!=='document')))return invalid();
 return {...x,item:record} as Detail;
}
function summary(v:unknown,expected:Context,filters:Filters):Summary{
 const x=shape(v,['context','workspace','total_count','storage','week_new_documents','todo_count','last_activity_at','future_panels']);context(x.context,expected);
 const w=shape(x.workspace,['id','name','slug','project_id','customer_id','product_id','department','classification']);
 if(w.id!==expected.workspace_id||!text(w.name,512,0)||!text(w.slug,128,0)||!['project_id','customer_id','product_id','department'].every(k=>text(w[k],128))||!integer(w.classification)||w.classification>3||!integer(x.total_count)||!integer(x.todo_count)||(x.last_activity_at!==null&&!utc(x.last_activity_at)))return invalid();
 const week=shape(x.week_new_documents,['value','window_start','window_end','definition']);
 if(!integer(week.value)||!utc(week.window_start)||!utc(week.window_end)||new Date(week.window_start)>new Date(week.window_end)||week.definition!=='authorized_filtered_documents_created_since_utc_monday')return invalid();
 const ids=['review','ai_words','quality','templates','recommendations','creation'];
 if(!Array.isArray(x.future_panels)||x.future_panels.length!==6)return invalid();
 const panels=x.future_panels.map(v=>{const f=shape(v,['id','value','state','reason','owner']);if(!choice(f.id,ids)||f.value!==null||!choice(f.state,['not_collected','not_evaluated','unavailable'])||!text(f.reason,256)||!text(f.owner,32))return invalid();return f as FuturePanel});
 if(new Set(panels.map(p=>p.id)).size!==6)return invalid();
 return {...x,storage:storage(x.storage,filters.visibility??'visible'),future_panels:panels} as Summary;
}
function receipt(v:unknown,expected:Context,command:Command):Receipt{
 const x=shape(v,['operation_id','action','resource_id','replayed','occurred_at','context','current']);context(x.context,expected);
 if(!validId(x.operation_id)||x.action!==command.action||x.resource_id!==command.resourceId||typeof x.replayed!=='boolean'||!utc(x.occurred_at))return invalid();
 return {...x,current:item(x.current,expected,command.resourceId)} as Receipt;
}
function validateFilters(filters:Filters){
 const allowed=['tab','collection','kind','document_type','lifecycle','visibility','limit','cursor'];
 if(Object.keys(filters).some(k=>!allowed.includes(k))||(filters.collection!==undefined&&!choice(filters.collection,collections))||(filters.tab!==undefined&&!choice(filters.tab,tabs))||(filters.kind!==undefined&&!choice(filters.kind,kinds))||(filters.document_type!==undefined&&!choice(filters.document_type,documentTypes))||(filters.lifecycle!==undefined&&!choice(filters.lifecycle,lifecycles))||(filters.visibility!==undefined&&!choice(filters.visibility,['visible','recycled']))||(filters.limit!==undefined&&(!integer(filters.limit,1)||filters.limit>50))||(filters.cursor!==undefined&&!cursor(filters.cursor)))throw new DiscoveryError('validation','筛选格式无效');
}
function queryString(filters:Filters){validateFilters(filters);const query=new URLSearchParams();for(const [key,value] of Object.entries(filters))if(value!==undefined)query.set(key,String(value));return query.size?`?${query}`:''}
const errors:Record<Failure,string>={authentication:'登录已失效，请重新登录',forbidden:'当前目标不可访问，受保护内容已清除',context:'权限上下文已变化，请重新读取',conflict:'记录或策略已变化，请刷新后重新确认', 'invalid-cursor':'列表已变化，正在从首页重新读取',validation:'输入格式无效，请检查后重试',unavailable:'服务暂时不可用，请重试',timeout:'请求超时，请重试',offline:'网络已离线，请恢复连接后重试','invalid-response':'响应格式无效，请重新读取',cancelled:'请求已取消'};
async function request(path:string,expected:Context,signal?:AbortSignal,method='GET',body?:unknown,key?:string):Promise<unknown>{
 if(!validId(expected.workspace_id)||!validId(expected.actor_id)||expected.policy_epoch.length!==3||!expected.policy_epoch.every(n=>integer(n,1))||expected.policy_epoch[0]!==expected.policy_epoch[2])return invalid();
 const accessToken=token();if(!accessToken)throw new DiscoveryError('authentication',errors.authentication,401);
 const controller=new AbortController();let timeout=false;let rejectAbort:(reason:unknown)=>void=()=>{};
 const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject});
 const abort=()=>{controller.abort();rejectAbort(new DiscoveryError(timeout?'timeout':'cancelled',errors[timeout?'timeout':'cancelled']))};
 signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(()=>{timeout=true;abort()},REQUEST_TIMEOUT_MS);
 const consume=async()=>{
  if(signal?.aborted){abort();throw new DiscoveryError('cancelled',errors.cancelled)}
  const response=await fetch(`/api/v1/workspaces/${expected.workspace_id}${path}`,{method,signal:controller.signal,headers:{Authorization:`Bearer ${accessToken}`,'X-Request-ID':crypto.randomUUID(),...(body===undefined?{}:{'Content-Type':'application/json'}),...(key?{'Idempotency-Key':key}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  if(controller.signal.aborted)throw new DiscoveryError('cancelled',errors.cancelled);
  if(!response.ok){
   let code='';if(response.status===422){try{const raw=await boundedJson(response,8192,errors['invalid-response'],controller.signal);if(object(raw)&&object(raw.error)&&typeof raw.error.code==='string')code=raw.error.code}catch{/* Use generic safe error; never display arbitrary server text. */}}
   const failure:Failure=response.status===401?'authentication':response.status===403?'forbidden':response.status===409?'conflict':response.status===422?(code==='INVALID_CURSOR'?'invalid-cursor':'validation'):'unavailable';
   throw new DiscoveryError(failure,errors[failure],response.status);
  }
  const raw=await boundedJson(response,64*1024,errors['invalid-response'],controller.signal);
  if(controller.signal.aborted||signal?.aborted||token()!==accessToken)throw new DiscoveryError('cancelled',errors.cancelled);
  return shape(raw,['data']).data;
 };
 try{return await Promise.race([consume(),aborted])}
 catch(error){if(error instanceof DiscoveryError)throw error;if(timeout)throw new DiscoveryError('timeout',errors.timeout);if(signal?.aborted)throw new DiscoveryError('cancelled',errors.cancelled);const failure=typeof navigator!=='undefined'&&!navigator.onLine?'offline':error instanceof TypeError?'unavailable':'invalid-response';throw new DiscoveryError(failure,errors[failure])}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort)}
}
export async function getDiscovery(expected:Context,filters:Filters={},signal?:AbortSignal):Promise<Page>{return page(await request(`/discovery${queryString(filters)}`,expected,signal),expected,filters,false)}
export async function getDiscoverySummary(expected:Context,filters:Filters={},signal?:AbortSignal):Promise<Summary>{if(filters.cursor)throw new DiscoveryError('validation','首页统计不接受分页游标');return summary(await request(`/discovery/summary${queryString(filters)}`,expected,signal),expected,filters)}
export async function getDiscoveryProjects(expected:Context,after?:string,signal?:AbortSignal):Promise<{items:Summary[];next_cursor:string|null}>{
 // Project enumeration is bounded by the existing access contract. Summaries
 // are read under each returned current context, with at most four in flight.
 const selected=await getDiscoverySummary(expected,{},signal);
 let projects:Awaited<ReturnType<typeof getWorkspaces>>;
 try{projects=await getWorkspaces(after)}catch(error){const failure=error instanceof AccountRequestError&&error.kind==='authentication'?'authentication':error instanceof AccountRequestError&&error.kind==='forbidden'?'forbidden':'unavailable';throw new DiscoveryError(failure,errors[failure])}
 const output:Summary[]=[];let index=0;
 const read=async()=>{while(index<projects.workspaces.length){
  if(signal?.aborted)throw new DiscoveryError('cancelled',errors.cancelled);
  const candidate=projects.workspaces[index++];
  if(candidate.actor_id!==expected.actor_id)throw new DiscoveryError('context',errors.context);
  output.push(candidate.workspace_id===expected.workspace_id&&sameContext(candidate,expected)?selected:await getDiscoverySummary(candidate,{},signal));
 }};
 await Promise.all(Array.from({length:Math.min(4,projects.workspaces.length)},read));
 if(signal?.aborted)throw new DiscoveryError('cancelled',errors.cancelled);
 output.sort((a,b)=>(b.last_activity_at?Date.parse(b.last_activity_at):0)-(a.last_activity_at?Date.parse(a.last_activity_at):0)||b.workspace.id.localeCompare(a.workspace.id));
 return {items:output,next_cursor:projects.next_cursor};
}
export async function getDiscoveryDetail(expected:Context,id:string,signal?:AbortSignal):Promise<Detail>{if(!validId(id))throw new DiscoveryError('validation','记录地址无效');return detail(await request(`/discovery/${id}`,expected,signal),expected,id)}
export async function searchDiscovery(expected:Context,query:string,filters:Filters={},signal?:AbortSignal):Promise<SearchPage>{validateFilters(filters);query=query.trim();if(!text(query,128))throw new DiscoveryError('validation','请输入 1–128 字符的搜索词');return page(await request('/search',expected,signal,'POST',{...filters,query}),expected,filters,true) as SearchPage}
export async function executeDiscoveryCommand(expected:Context,command:Command,signal?:AbortSignal):Promise<Receipt>{
 if(!validId(command.resourceId)||!text(command.key,128)||!/^[A-Za-z0-9._:-]+$/.test(command.key))throw new DiscoveryError('validation','操作标识无效');
 if(command.action==='favorite.set'){const b=shape(command.body,['favorite','expected_revision']);if(typeof b.favorite!=='boolean'||!integer(b.expected_revision))throw new DiscoveryError('validation','收藏输入无效')}
 else if(command.action==='restore_visibility'){const b=shape(command.body,['expected_revision','policy_version']);if(!integer(b.expected_revision,1)||!text(b.policy_version,128))throw new DiscoveryError('validation','恢复输入无效')}
 else throw new DiscoveryError('validation','操作类型无效');
 const path=command.action==='favorite.set'?`/favorites/${command.resourceId}`:`/recycle/${command.resourceId}:restore`;
 return receipt(await request(path,expected,signal,command.action==='favorite.set'?'PUT':'POST',command.body,command.key),expected,command);
}
