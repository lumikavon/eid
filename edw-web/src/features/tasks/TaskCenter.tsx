import {type Dispatch,type SetStateAction,useCallback,useEffect,useRef,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import type {WorkspaceAccess} from '../../app/access-api';
import {type Category,type InventoryResult,type Notification,type Page,type TaskEvent,type TaskSnapshot,TaskError,categories,cancelTask,getEventPage,getNotification,getNotifications,getTask,getTaskResult,getTasks,markNotificationRead,openNotification,retryTask,streamTask} from '../../app/task-api';
import {type TaskAction,forgetTaskAction,rememberTaskAction} from './task-action';
import './tasks.css';

type Props={current:WorkspaceAccess;onReject:(error:unknown)=>void;onRefresh:()=>void;onNotificationsChanged:()=>void;action:TaskAction|null;setAction:Dispatch<SetStateAction<TaskAction|null>>;actionAbort:{current:AbortController|null}};
const labels:Record<Category,string>={generation:'生成',retrieval:'检索',review:'审校',parse_ocr:'解析/OCR',render:'渲染',integration:'集成'};
const stateLabels:Record<TaskSnapshot['state'],string>={QUEUED:'排队中',RUNNING:'运行中',RETRY_WAIT:'等待重试',SUCCEEDED:'已完成',BLOCKED:'已阻塞',FAILED:'失败',CANCELLED:'已取消',DEAD_LETTER:'死信'};
const reasons:Record<NonNullable<TaskSnapshot['action_reason']>,string>={OPERATION_UNAVAILABLE:'此业务操作尚未注册安全执行能力',EXTERNAL_EFFECT_UNKNOWN:'外部效果尚未确认，禁止盲目取消或重试',TASK_TERMINAL:'任务已结束，不能取消',TASK_NOT_TERMINAL:'任务尚未结束，不能手动重试'};
const time=(value:string)=>value.replace('T',' ').replace(/(?:\.\d+)?(?:Z|\+00:00)$/,' UTC');
const terminal=new Set(['SUCCEEDED','BLOCKED','FAILED','CANCELLED','DEAD_LETTER']);
const message=(error:unknown)=>error instanceof Error?error.message:'读取失败，请重试';
const guarded=(error:unknown)=>error instanceof TaskError&&['authentication','forbidden','missing'].includes(error.failure);

export default function TaskCenter({current,onReject,onRefresh,onNotificationsChanged,action,setAction,actionAbort}:Props){
 const route=useLocation();const navigate=useNavigate();const base=`/workspaces/${current.workspace_id}`;
 const detailId=/\/tasks\/([^/]+)$/.exec(route.pathname)?.[1]?.toLowerCase();
 const notificationsView=route.pathname.endsWith('/notifications');
 const scope=[current.actor_id,current.workspace_id,...current.policy_epoch].join(':');
 const [category,setCategory]=useState<Category|'all'>('all');
 const [taskCursors,setTaskCursors]=useState<string[]>([]);
 const [notificationCursors,setNotificationCursors]=useState<string[]>([]);
 const [tasks,setTasks]=useState<Page<TaskSnapshot>|null>(null);
 const [notifications,setNotifications]=useState<Page<Notification>|null>(null);
 const [selectedNotification,setSelectedNotification]=useState<Notification|null>(null);
 const [task,setTask]=useState<TaskSnapshot|null>(null);
 const [events,setEvents]=useState<TaskEvent[]>([]);
 const [historyLimited,setHistoryLimited]=useState(false);
 const [result,setResult]=useState<InventoryResult|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [revision,setRevision]=useState(0);
 const [selectedNotificationId,setSelectedNotificationId]=useState<string|null>(null);
 const live=useRef('');const notificationAbort=useRef<AbortController|null>(null);
 const taskCursor=taskCursors.at(-1);const notificationCursor=notificationCursors.at(-1);
 const resultRef=task?.result_ref;const resultState=task?.state;const resultUrl=task?.result_url;
 const requestKey=JSON.stringify([scope,route.pathname,taskCursor,notificationCursor,revision]);
 live.current=requestKey;
 const denied=useCallback((cause:unknown)=>{
  if(!guarded(cause))return false;
	  live.current='';if(cause instanceof TaskError&&cause.failure!=='missing'){actionAbort.current?.abort();setAction(null)}notificationAbort.current?.abort();setTask(null);setEvents([]);setResult(null);setTasks(null);setNotifications(null);setSelectedNotification(null);setError(message(cause));
  if(cause instanceof TaskError&&cause.failure==='missing')onRefresh();else onReject(cause);
  return true;
 },[onReject,onRefresh,actionAbort,setAction]);
 useEffect(()=>()=>{live.current='';notificationAbort.current?.abort()},[scope]);
 useEffect(()=>{setTaskCursors([]);setNotificationCursors([]);setTasks(null);setNotifications(null);setTask(null);setEvents([]);setHistoryLimited(false);setResult(null);setSelectedNotification(null);setSelectedNotificationId(null);setError('');setNotice('')},[scope]);
 useEffect(()=>{
  if(detailId||notificationsView)return;const controller=new AbortController();const key=requestKey;setBusy(true);setError('');setTasks(null);
  void getTasks(current.workspace_id,taskCursor,controller.signal).then(page=>{if(live.current===key)setTasks(page)}).catch(cause=>{if(live.current!==key||controller.signal.aborted)return;if(!denied(cause)){if(cause instanceof TaskError&&cause.failure==='invalid-cursor'){setTaskCursors([]);setNotice('任务列表已变化，已从首页重新读取')}else setError(message(cause))}}).finally(()=>{if(live.current===key)setBusy(false)});
  return()=>controller.abort();
 },[current.workspace_id,detailId,notificationsView,requestKey,taskCursor,denied]);
 useEffect(()=>{
  if(!notificationsView)return;const controller=new AbortController();const key=requestKey;setBusy(true);setError('');setNotifications(null);
  void getNotifications(current.workspace_id,notificationCursor,controller.signal).then(page=>{if(live.current===key)setNotifications(page)}).catch(cause=>{if(live.current!==key||controller.signal.aborted)return;if(!denied(cause)){if(cause instanceof TaskError&&cause.failure==='invalid-cursor'){setNotificationCursors([]);setNotice('通知列表已变化，已从首页重新读取')}else setError(message(cause))}}).finally(()=>{if(live.current===key)setBusy(false)});
  return()=>controller.abort();
 },[current.workspace_id,notificationsView,notificationCursor,requestKey,denied]);
 useEffect(()=>{
  if(!selectedNotificationId||!notificationsView)return;const controller=new AbortController();const key=requestKey;setSelectedNotification(null);
  void getNotification(current.workspace_id,selectedNotificationId,controller.signal).then(item=>{if(live.current===key)setSelectedNotification(item)}).catch(cause=>{if(live.current===key&&!controller.signal.aborted&&!denied(cause))setError(message(cause))});
  return()=>controller.abort();
 },[current.workspace_id,selectedNotificationId,notificationsView,requestKey,denied]);
 useEffect(()=>{
  if(!detailId)return;const controller=new AbortController();const key=requestKey;let cursor=0;let eventCount=0;let stopped=false;
  setTask(null);setEvents([]);setHistoryLimited(false);setResult(null);setError('');setBusy(true);
  const active=()=>!stopped&&!controller.signal.aborted&&live.current===key;
  const snapshot=async()=>{const fresh=await getTask(current.workspace_id,detailId,controller.signal);if(!active())return null;setTask(fresh);cursor=fresh.current_seq;return fresh};
  const replay=async()=>{
   const page=await getEventPage(current.workspace_id,detailId,cursor,controller.signal);
   if(page.reset_required){await resetHistory();return}
   if(page.data.length){for(const item of page.data){if(item.seq<=cursor)continue;if(item.seq!==cursor+1){await resetHistory();return}cursor=item.seq;if(eventCount===64)setHistoryLimited(true);eventCount=Math.min(64,eventCount+1);setEvents(old=>[...old.filter(e=>e.seq!==item.seq),item].slice(-64))}await snapshotPreservingCursor()}
  };
  const snapshotPreservingCursor=async()=>{const previous=cursor;const fresh=await getTask(current.workspace_id,detailId,controller.signal);if(active()){setTask(fresh);cursor=previous}};
  const history=async(initial:TaskSnapshot,recovering=false)=>{let fresh:TaskSnapshot|null=initial;for(let attempt=0;attempt<3&&fresh&&active();attempt++){
   const after=Math.max(fresh.retention_floor-1,fresh.current_seq-64);
   const page=await getEventPage(current.workspace_id,detailId,after,controller.signal);if(!active())return;
   const last=page.data.at(-1)?.seq;
   if(!page.reset_required&&last!==undefined&&last>=fresh.current_seq){cursor=last;eventCount=page.data.length;setEvents(page.data);setHistoryLimited(after>fresh.retention_floor-1);if(last>fresh.current_seq)await snapshotPreservingCursor();if(active()&&(recovering||attempt>0))setNotice('事件历史已按最新保留窗口恢复');return}
   eventCount=0;setEvents([]);setHistoryLimited(false);setNotice('事件保留窗口已变化，正在重新读取受权任务快照');fresh=await snapshot();
   }if(active())throw new TaskError('invalid-response','事件历史持续变化，无法核对；请刷新任务重试')};
  const resetHistory=async()=>{eventCount=0;setEvents([]);setHistoryLimited(false);setNotice('事件出现缺口或保留窗口变化，正在重新读取受权任务快照');const fresh=await snapshot();if(fresh&&active())await history(fresh,true)};
  const pause=()=>new Promise<void>(resolve=>{const done=()=>{clearTimeout(timer);controller.signal.removeEventListener('abort',done);resolve()};const timer=setTimeout(done,1500);controller.signal.addEventListener('abort',done,{once:true})});
  const run=async()=>{
   try{const fresh=await snapshot();if(!fresh||!active())return;await history(fresh);if(!active())return;setBusy(false);
    while(active()){
     try{
      await replay();if(!active())return;
      await streamTask(current.workspace_id,detailId,cursor,async item=>{
       if(!active()||item.seq<=cursor)return;
       if(item.seq!==cursor+1){await replay();if(item.seq<=cursor)return;if(item.seq!==cursor+1){await resetHistory();return}}
       cursor=item.seq;if(eventCount===64)setHistoryLimited(true);eventCount=Math.min(64,eventCount+1);setEvents(old=>[...old.filter(e=>e.seq!==item.seq),item].slice(-64));await snapshotPreservingCursor();
       },resetHistory,controller.signal);
     }catch(cause){if(!active()||denied(cause))return;
      if(cause instanceof TaskError&&cause.failure==='conflict'){await resetHistory();continue}
      if(cause instanceof TaskError&&['invalid-response','invalid-cursor'].includes(cause.failure)){setError(message(cause));return}
      setNotice('事件连接已中断，正在按序号重连并核对缺口');
     }
     if(!active())return;await pause();
    }
   }catch(cause){if(!active()||denied(cause))return;setError(`${message(cause)}；可刷新任务重试`);setBusy(false)}
  };void run();return()=>{stopped=true;controller.abort()};
 },[current.workspace_id,detailId,requestKey,denied]);
 useEffect(()=>{if(!detailId||resultState!=='SUCCEEDED'||!resultRef||!resultUrl)return;const controller=new AbortController();const key=requestKey;setResult(null);
  void getTaskResult(current.workspace_id,detailId,resultRef,controller.signal).then(value=>{if(live.current===key)setResult(value)}).catch(cause=>{if(live.current===key&&!controller.signal.aborted&&!denied(cause))setError(`结果读取失败：${message(cause)}`)});
  return()=>controller.abort();
 },[current.workspace_id,detailId,resultRef,resultState,resultUrl,requestKey,denied]);
 const refresh=()=>setRevision(v=>v+1);
 const openTask=(id:string)=>{setNotice('');navigate(`${base}/tasks/${id}`)};
 const notificationAction=async(kind:'read'|'open')=>{
	  if(!selectedNotification||busy)return;const controller=new AbortController();notificationAbort.current=controller;const key=requestKey;setBusy(true);setError('');
	  try{if(kind==='read'){const item=await markNotificationRead(current.workspace_id,selectedNotification.notification_id,controller.signal);onNotificationsChanged();if(live.current===key){setSelectedNotification(item);setNotifications(old=>old?{...old,data:old.data.map(row=>row.notification_id===item.notification_id?item:row)}:old);setNotice('通知已读；任务状态未改变')}}
	   else{const target=await openNotification(current.workspace_id,selectedNotification.notification_id,selectedNotification.task_id,controller.signal);onNotificationsChanged();if(live.current===key)openTask(target.task_id)}
  }catch(cause){if(live.current===key&&!controller.signal.aborted&&!denied(cause))setError(message(cause))}finally{if(live.current===key)setBusy(false)}
 };
 const confirmAction=(kind:'cancel'|'retry')=>{if(!task||action||!(kind==='cancel'?task.can_cancel:task.can_retry))return;const next:TaskAction={scope,taskId:task.task_id,kind,key:crypto.randomUUID(),state:'confirm',message:kind==='cancel'?'取消请求可能先于或晚于任务完成，请确认提交。':'重试会创建新任务并保留此任务历史，请确认提交。'};rememberTaskAction(next);setAction(next)};
 const performAction=async(command:TaskAction)=>{
  if(command.scope!==scope||command.state==='pending'||command.state==='resolved'||actionAbort.current)return;
  const controller=new AbortController();actionAbort.current=controller;setAction(old=>old?.scope===scope&&old.key===command.key?{...old,state:'pending',message:'正在提交，请勿重复操作'}:old);setError('');
  try{const outcome=command.kind==='cancel'?await cancelTask(current.workspace_id,command.taskId,controller.signal):await retryTask(current.workspace_id,command.taskId,command.key,controller.signal);
   if(controller.signal.aborted)return;forgetTaskAction();
   setAction(old=>old?.scope===scope&&old.key===command.key?{...old,state:'resolved',outcomeTaskId:outcome.task_id,message:command.kind==='cancel'?'取消请求已持久提交；请以当前任务状态确认最终结果':`重试已创建新任务 ${outcome.task_id}；原任务历史已保留`}:old);
   if(live.current===requestKey&&detailId===command.taskId){if(command.kind==='cancel')setTask(outcome);refresh()}
  }catch(cause){if(controller.signal.aborted)return;
   if(cause instanceof TaskError&&cause.failure==='missing'){forgetTaskAction();setAction(old=>old?.scope===scope&&old.key===command.key?{...old,state:'resolved',message:'目标不存在或已不可访问；操作结果不能推定成功，请重新读取授权任务'}:old);denied(cause);return}
   if(denied(cause))return;
   if(cause instanceof TaskError&&cause.failure==='conflict'){forgetTaskAction();setAction(old=>old?.scope===scope&&old.key===command.key?{...old,state:'resolved',message:'任务状态已变化；请求未被接受，请刷新详情后重新判断'}:old);refresh();return}
   setAction(old=>old?.scope===scope&&old.key===command.key?{...old,state:'unknown',message:command.kind==='retry'?'提交结果未知。仅可用相同操作标识核对，不要创建新的重试。':'取消提交结果未知。先刷新任务状态，不要盲目重复提交。'}:old);setError(message(cause));
  }finally{if(actionAbort.current===controller)actionAbort.current=null}
 };
 const categoryRows=tasks?.data.filter(row=>category==='all'||row.category===category)??[];
 const activeAction=action?.scope===scope?action:null;
 return <div className="task-center" data-testid="task-center" data-context={scope}>
  <header className="page-header"><div><h1>{notificationsView?'通知':detailId?'任务详情':'任务中心'}</h1><p>当前项目：{current.name} · 仅显示当前授权的持久记录</p></div><span className="grow"/><button className="btn" onClick={()=>navigate(`${base}/tasks`)}>任务中心</button><button className="btn" onClick={()=>navigate(`${base}/notifications`)}>通知</button><button className="btn" onClick={refresh}>刷新</button></header>
	  <div className="task-body">{notice&&<p className="task-notice" role="status">{notice}</p>}{error&&<p className="task-error" role="alert">{error}</p>}{activeAction&&<section className="task-action" role="status"><p>{activeAction.message}</p>{detailId!==activeAction.taskId&&<button className="btn" onClick={()=>openTask(activeAction.taskId)}>查看原任务</button>}{activeAction.state==='confirm'?<><button className="btn" onClick={()=>{forgetTaskAction();setAction(null)}}>返回</button><button className="btn primary" onClick={()=>void performAction(activeAction)}>确认提交</button></>:activeAction.state==='unknown'?<><button className="btn" onClick={refresh}>刷新状态</button>{activeAction.kind==='retry'&&<button className="btn" onClick={()=>void performAction(activeAction)}>以相同标识核对重试</button>}</>:activeAction.state==='resolved'?<><button className="btn" onClick={()=>setAction(null)}>知道了</button>{activeAction.kind==='retry'&&activeAction.outcomeTaskId&&<button className="btn primary" onClick={()=>{const id=activeAction.outcomeTaskId!;setAction(null);openTask(id)}}>查看新任务</button>}</>:null}</section>}{busy&&<p role="status">正在读取当前授权记录…</p>}
  {notificationsView?<><section className="task-columns"><div><h2>持久通知</h2>{notifications&&notifications.data.length===0&&<p>当前项目暂无通知。</p>}{notifications?.data.map(item=><button className={`task-row ${item.read_at?'':'unread'}`} key={item.notification_id} onClick={()=>setSelectedNotificationId(item.notification_id)}><b>{stateLabels[item.state]}</b><span>{item.event_type} · {time(item.created_at)}</span><small>{item.read_at?'已读':'未读'} · 任务 {item.task_id}</small></button>)}{notifications&&<div className="task-pager"><button className="btn" disabled={!notificationCursors.length} onClick={()=>setNotificationCursors(old=>old.slice(0,-1))}>上一页</button><button className="btn" disabled={!notifications.next_cursor} onClick={()=>setNotificationCursors(old=>[...old,notifications.next_cursor!])}>下一页</button></div>}</div><div><h2>通知详情</h2>{selectedNotification&&selectedNotification.notification_id===selectedNotificationId?<><dl className="task-meta">{[['通知 ID',selectedNotification.notification_id],['任务 ID',selectedNotification.task_id],['事件',selectedNotification.event_type],['状态',stateLabels[selectedNotification.state]],['创建时间',time(selectedNotification.created_at)],['已读时间',selectedNotification.read_at?time(selectedNotification.read_at):'未读']].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><div className="task-actions"><button className="btn" disabled={busy||Boolean(selectedNotification.read_at)} onClick={()=>void notificationAction('read')}>标为已读</button><button className="btn primary" disabled={busy} onClick={()=>void notificationAction('open')}>打开目标任务</button></div><p>标为已读只更新通知；打开目标会重新核对任务与结果权限。</p></>:<p>选择通知查看详情与操作。</p>}</div></section></>:
   detailId?<><button className="btn" onClick={()=>navigate(`${base}/tasks`)}>返回任务列表</button>{task&&<article className="task-detail"><h2>{labels[task.category]} · {task.operation}</h2><p><span className={`pill ${terminal.has(task.state)?task.state==='SUCCEEDED'?'green':'red':'blue'}`}>{stateLabels[task.state]}</span> · {task.stage} · 进度{task.progress===null?'未知':task.progress}</p><dl className="task-meta">{[['任务 ID',task.task_id],['父任务',task.parent_task_id??'无'],['尝试次数',String(task.attempt)],['当前序号',String(task.current_seq)],['保留窗口起点',String(task.retention_floor)],['创建时间',time(task.created_at)],['更新时间',time(task.updated_at)],['取消请求',task.cancel_requested?'已提交，等待最终状态':'未提交'],['下次重试',task.next_retry_at?time(task.next_retry_at):'无'],['错误',task.error??'无'],['错误分类',task.error_class??'无'],['外部效果',task.external_effect_state],['结果引用',task.result_ref??'无']].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
	    <div className="task-actions"><button className="btn" disabled={!task.can_cancel||Boolean(activeAction)} onClick={()=>confirmAction('cancel')}>取消任务</button><button className="btn" disabled={!task.can_retry||Boolean(activeAction)} onClick={()=>confirmAction('retry')}>手动重试</button></div>{task.action_reason&&<p className="task-reason">操作限制：{reasons[task.action_reason]}</p>}
    <h3>事件轨迹</h3>{task.retention_floor>1&&<p>较早事件已超出保留窗口；当前任务状态来自受权快照。</p>}{historyLimited&&<p>保留事件较多，此处仅展示已读取的部分事件；任务状态仍以当前受权快照为准。</p>}{events.length?<ol className="task-events">{events.map(item=><li key={item.seq}>#{item.seq} · {item.event_type} · {stateLabels[item.state]} · {time(item.occurred_at)}</li>)}</ol>:<p>暂无可显示事件。</p>}
    <h3>结果</h3>{task.state==='SUCCEEDED'?task.result_url?result?<><p>结果 ID：{result.result_id} · 实际计量：{time(result.measured_at)} · 当前授权记录 {result.items.length} 条</p><ul>{result.items.map(item=><li key={item.resource_id}>{item.kind} · {item.resource_id} · 修订 {item.revision}</li>)}</ul></>:<p>正在重新核对结果权限；不可使用旧结果。</p>:<p>当前类别尚未注册结果读取能力；保留结果引用，不能打开或推断结果内容。</p>:<p>当前状态无最终结果。</p>}
   </article>}</>:
   <><div className="task-filter"><label>任务类别 <select value={category} onChange={e=>setCategory(e.target.value as Category|'all')}><option value="all">全部类别</option>{categories.map(value=><option key={value} value={value}>{labels[value]}</option>)}</select></label></div>{tasks&&categoryRows.length===0&&<p>{category==='all'?(tasks.next_cursor?'本页没有任务，请查看下一页。':'当前项目暂无可显示的持久任务。'):`本页没有${labels[category]}任务${tasks.next_cursor?'；可继续翻页':'；目前没有更多页'}。只有已注册且获授权的操作可提交，不能创建示例任务。`}</p>}{categoryRows.map(item=><button className="task-row" key={item.task_id} onClick={()=>openTask(item.task_id)}><b>{labels[item.category]} · {stateLabels[item.state]}</b><span>{item.operation} · 尝试 {item.attempt} · {time(item.updated_at)}</span><small>{item.error?`错误：${item.error}`:item.cancel_requested?'取消请求已提交':item.action_reason?reasons[item.action_reason]:item.result_url?'查看详情与结果':'查看任务详情'}</small></button>)}{tasks&&<div className="task-pager"><button className="btn" disabled={!taskCursors.length} onClick={()=>setTaskCursors(old=>old.slice(0,-1))}>上一页</button><button className="btn" disabled={!tasks.next_cursor} onClick={()=>setTaskCursors(old=>[...old,tasks.next_cursor!])}>下一页</button></div>}</>}
  </div>
 </div>
}
