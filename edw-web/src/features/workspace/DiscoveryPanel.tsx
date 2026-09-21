import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {useLocation,useNavigate} from 'react-router-dom';
import {type WorkspaceAccess} from '../../app/access-api';
import {type Command,type Filters,type FuturePanel,type Item,type Page,type SearchPage,type Storage,type Summary,DiscoveryError,collections,documentTypes,executeDiscoveryCommand,getDiscovery,getDiscoveryDetail,getDiscoveryProjects,getDiscoverySummary,kinds,lifecycles,searchDiscovery,tabs} from '../../app/discovery-api';
import './discovery.css';

type Props={current:WorkspaceAccess;search:{query:string;sequence:number};onReject:(error:unknown)=>void;onRefresh:()=>void};
const tabLabels=['最近文档','我创建的','我参与的','我的收藏'];
const kindLabels={document:'文档',knowledge:'知识元数据',reference:'参考资料'};
const typeLabels={technical:'技术方案',proposal:'方案建议',report:'报告',manual:'手册',other:'其他'};
const statusLabels={DRAFT:'草稿',IN_REVIEW:'审校中',APPROVED:'已批准',ARCHIVED:'已归档（只读）'};
const viewLabels:Record<string,string>={home:'工作台',documents:'项目文档',references:'参考资料',favorites:'我的收藏',recycle:'回收站',search:'搜索结果',project:'项目详情',projects:'可访问项目',records:'记录详情'};
const stamp=(time:string)=>time.replace('T',' ').replace(/(?:\.\d+)?(?:Z|\+00:00)$/,' UTC');
const futureLabels={not_collected:'未采集',not_evaluated:'未评估',unavailable:'尚未开放'};
const quickTypes=[['新建标书','招投标文件、商务标/技术标'],['新建 PRD','产品需求文档'],['新建技术方案','架构设计、技术实现方案'],['新建测试方案','测试计划、测试用例'],['新建项目总结报告','项目复盘、成果总结']];
const catalog=['技术方案','PRD','测试方案','技术要求','质量大纲','项目计划','功能测试大纲','性能测试大纲','项目总结','标书','生产表单'];

function Future({panel}:{panel?:FuturePanel}){return <p className="discovery-reason">{panel?`${futureLabels[panel.state]}：${panel.reason}（${panel.owner}）`:'正在读取可用状态'}</p>}
function ReadState({loading,error,empty=false,filtered=false,retry,reset,retryable=true}:{loading?:boolean;error?:unknown;empty?:boolean;filtered?:boolean;retry:()=>void;reset?:()=>void;retryable?:boolean}){
 if(error){const failure=error instanceof DiscoveryError?error.failure:'unavailable';return <div className="discovery-state" data-testid="discovery-state" data-state={failure} role="alert"><p>{error instanceof Error?error.message:'读取失败，请重试'}</p>{retryable&&failure!=='authentication'&&failure!=='context'&&<button className="btn" onClick={retry}>重新读取</button>}{!retryable&&reset&&<button className="btn" onClick={reset}>重置筛选</button>}</div>}
 if(loading)return <div className="discovery-state" data-testid="discovery-state" data-state="loading" role="status">正在加载当前授权记录…</div>;
 if(empty)return <div className="discovery-state" data-testid="discovery-state" data-state={filtered?'empty-filtered':'empty'} role="status"><p>{filtered?'无符合筛选条件的数据':'当前项目尚无可显示的记录'}</p>{filtered&&reset&&<button className="btn" onClick={reset}>重置筛选</button>}</div>;
 return null;
}
function StorageInfo({value}:{value?:Storage}){return <div className="storage" data-testid="discovery-storage"><b>可见记录元数据占用</b><p>{value?`${value.metadata_bytes.toLocaleString()} 字节`:'尚未统计'}</p><small>{value?<>当前授权筛选集合 · {value.visibility==='recycled'?'仅回收站记录':'不含回收站记录'}<br/>计量时间：{stamp(value.measured_at)}<br/>数据库持久元数据与标题的实际字节；附件与总体配额未统计。</>:'读取当前集合后显示；附件与总体配额未知。'}</small></div>}
function RecordTable({page,current,onOpen,selected}:{page:Page;current:WorkspaceAccess;onOpen:(item:Item)=>void;selected?:string}){return <table data-testid="discovery-table"><thead><tr><th>文档名称</th><th>类型</th><th>所属项目</th><th>最后更新</th><th>状态</th></tr></thead><tbody>{page.items.map(item=><tr key={item.id} data-record-id={item.id} className={selected===item.id?'discovery-selected':undefined}><td><button className="discovery-link" aria-current={selected===item.id?'true':undefined} onClick={()=>onOpen(item)}>{item.title}</button>{item.favorite&&<span aria-label="已收藏"> ☆</span>}</td><td>{item.document_type?typeLabels[item.document_type]:kindLabels[item.kind]}</td><td>{current.name}</td><td>{stamp(item.updated_at)}</td><td><span className="pill">{statusLabels[item.lifecycle]}</span>{item.visibility==='recycled'&&' · 回收站'}</td></tr>)}</tbody></table>}

export default function DiscoveryPanel({current,search,onReject,onRefresh}:Props){
 const location=useLocation();const navigate=useNavigate();const cache=useQueryClient();
 const base=`/workspaces/${current.workspace_id}`;
 const view=location.pathname==='/'?'home':location.pathname.slice(base.length+1).split('/')[0];
 const resourceId=view==='records'?location.pathname.split('/')[4]?.toLowerCase():undefined;
 const params=new URLSearchParams(location.search);
 const tab=tabs.find(t=>t===params.get('tab'))??'recent';
 const kind=kinds.find(k=>k===params.get('kind'));
 const documentType=documentTypes.find(t=>t===params.get('type'));
 const lifecycle=lifecycles.find(t=>t===params.get('status'));
 const collection=collections.find(value=>value===params.get('collection'))??'all';
 const scope=[current.actor_id,current.workspace_id,...current.policy_epoch].join(':');
 const listView=view==='records'?(params.get('from')??'documents'):view;
 const kindConflict=['home','documents'].includes(listView)&&Boolean(kind&&kind!=='document');
 const collectionConflict=listView==='references'&&collection!=='all'&&collection!=='references';
 const tabConflict=listView==='favorites'&&Boolean(params.get('tab')&&tab!=='favorites');
 const conflictMessage=kindConflict?'当前视图仅显示文档，不能与所选记录类型同时使用。':collectionConflict?'“参考资料”仅支持全部或参考资料集合，不能与所选集合同时使用。':tabConflict?'“我的收藏”固定显示收藏标签，不能与所选标签同时使用。':null;
 const filterConflict=Boolean(conflictMessage);
 const conflictError=filterConflict?new DiscoveryError('validation',conflictMessage!):null;
 const filters:Filters={collection:listView==='references'?'references':collection,tab:listView==='favorites'?'favorites':tab,visibility:listView==='recycle'?'recycled':'visible',limit:20,...(kind?{kind}:{}),...(documentType?{document_type:documentType}:{}),...(lifecycle?{lifecycle}:{}),...(['home','documents'].includes(listView)?{kind:'document' as const}:{})};
 const rawFilterKey=JSON.stringify([params.get('tab'),params.get('kind'),params.get('collection'),params.get('type'),params.get('status')]);
 const filterKey=JSON.stringify([scope,listView,filters,listView==='search'?search:null,rawFilterKey]);
 const [pagination,setPagination]=useState<{key:string;cursors:string[]}>({key:'',cursors:[]});
 const cursors=pagination.key===filterKey?pagination.cursors:[];
 const cursor=cursors.at(-1);
 const requestKey=JSON.stringify([filterKey,view,resourceId,cursor]);
 // This ref changes during render, so even a promise resolving before effect cleanup
 // cannot commit a former route, query, identity or policy context.
 const activeRequest=useRef(requestKey);
 const commandController=useRef<AbortController|null>(null);
 const returnPosition=useRef<{key:string;id:string;top:number}|null>(null);
 const [online,setOnline]=useState(()=>typeof navigator==='undefined'||navigator.onLine);
 const [blocked,setBlocked]=useState<{key:string;error:DiscoveryError}|null>(null);
 const [feedback,setFeedback]=useState<{key:string;message:string}|null>(null);
 const [commandState,setCommandState]=useState<{key:string;command:Command;state:'confirm'|'pending'|'unknown';message:string}|null>(null);
 const [catalogOpen,setCatalogOpen]=useState(false);
 const blockedHere=blocked?.key===requestKey?blocked.error:null;
 const pending=commandState?.key===requestKey?commandState:null;
 const queryPrefix=['discovery',current.actor_id,current.workspace_id,...current.policy_epoch];
 const canRead=online&&!blockedHere&&!filterConflict;
 const isList=['home','documents','favorites','references','recycle','search'].includes(view);
 const isSearch=view==='search';
 const validSearch=search.query.trim().length>0;
 const list=useQuery({queryKey:[...queryPrefix,'list',filterKey,cursor],queryFn:({signal})=>isSearch?searchDiscovery(current,search.query,{...filters,...(cursor?{cursor}:{})},signal):getDiscovery(current,{...filters,...(cursor?{cursor}:{})},signal),enabled:canRead&&isList&&(!isSearch||validSearch),retry:false,gcTime:0});
 const summary=useQuery({queryKey:[...queryPrefix,'summary'],queryFn:({signal})=>getDiscoverySummary(current,{},signal),enabled:canRead&&['home','project'].includes(view),retry:false,gcTime:0});
 const projects=useQuery({queryKey:[...queryPrefix,'projects',view==='projects'?cursor:undefined],queryFn:({signal})=>getDiscoveryProjects(current,view==='projects'?cursor:undefined,signal),enabled:canRead&&['home','projects'].includes(view),retry:false,gcTime:0});
 const todo=useQuery({queryKey:[...queryPrefix,'todo'],queryFn:({signal})=>getDiscovery(current,{collection:'todo',limit:3},signal),enabled:canRead&&view==='home',retry:false,gcTime:0});
 const detail=useQuery({queryKey:[...queryPrefix,'detail',resourceId],queryFn:({signal})=>getDiscoveryDetail(current,resourceId!,signal),enabled:canRead&&Boolean(resourceId),retry:false,gcTime:0});
 const listError=isList?list.error:null;const summaryError=['home','project'].includes(view)?summary.error:null;const detailError=resourceId?detail.error:null;const todoError=view==='home'?todo.error:null;
 const projectsError=['home','projects'].includes(view)?projects.error:null;
 const activeError=conflictError??blockedHere??listError??summaryError??detailError;
 const fatal=[listError,summaryError,detailError,todoError,projectsError].find(e=>e instanceof DiscoveryError&&['authentication','forbidden','context'].includes(e.failure));
 activeRequest.current=blockedHere||fatal?'':requestKey;
 const rejectHandled=useRef<unknown>(null);
 useLayoutEffect(()=>{
  if(!fatal||rejectHandled.current===fatal)return;rejectHandled.current=fatal;
  commandController.current?.abort();commandController.current=null;activeRequest.current='';
  returnPosition.current=null;setCommandState(null);setFeedback(null);setBlocked({key:requestKey,error:fatal as DiscoveryError});
  if(fatal instanceof DiscoveryError&&fatal.failure==='authentication')onReject(fatal);
  else if(fatal instanceof DiscoveryError&&fatal.failure==='forbidden'&&!resourceId&&fatal!==projectsError)onReject(fatal);
  else onRefresh();
 },[fatal,onReject,onRefresh,requestKey,resourceId,projectsError]);
 // First disable observers above, then remove controlled data. Cache removal alone
 // can recreate an enabled observer while a denial is being handled.
 useEffect(()=>{if(blockedHere){void cache.cancelQueries({queryKey:['discovery']});cache.removeQueries({queryKey:['discovery']})}},[blockedHere,cache]);
 useEffect(()=>{
  if(listError instanceof DiscoveryError&&listError.failure==='invalid-cursor'&&cursor){setPagination({key:filterKey,cursors:[]});setFeedback({key:filterKey,message:'列表已变化，已清除旧游标并从首页重新读取'})}
 },[listError,cursor,filterKey,requestKey]);
 useLayoutEffect(()=>{return()=>{commandController.current?.abort();activeRequest.current='';}},[requestKey]);
 useLayoutEffect(()=>{activeRequest.current=blockedHere||fatal?'':requestKey},[requestKey,blockedHere,fatal]);
 useEffect(()=>{const update=()=>setOnline(navigator.onLine);window.addEventListener('online',update);window.addEventListener('offline',update);return()=>{window.removeEventListener('online',update);window.removeEventListener('offline',update)}},[]);
 useEffect(()=>{setCommandState(null);setCatalogOpen(false)},[requestKey]);
 const retry=()=>{if(filterConflict)return;setBlocked(null);rejectHandled.current=null;if(resourceId)void detail.refetch();else{if(isList&&(!isSearch||validSearch))void list.refetch();if(view==='home'||view==='project')void summary.refetch();if(view==='home')void todo.refetch();if(view==='home'||view==='projects')void projects.refetch()}};
 const currentList=canRead&&!list.isFetching&&!listError?list.data:undefined;
 const currentFunctions=isSearch&&currentList&&'functions' in currentList?(currentList as SearchPage).functions:[];
 const currentSummary=canRead&&!summary.isFetching&&!summaryError?summary.data:undefined;
 const currentProjects=canRead&&!projects.isFetching&&!projectsError?projects.data:undefined;
 const currentTodo=canRead&&!todo.isFetching&&!todoError?todo.data:undefined;
 const currentDetail=canRead&&!detail.isFetching&&!detailError?detail.data:undefined;
 const safeStorage=!activeError&&online?(isList?currentList?.storage:currentSummary?.storage):undefined;
 const portal=typeof document!=='undefined'?document.getElementById('discovery-storage-slot'):null;
 const setFilter=(name:string,value:string)=>{const next=new URLSearchParams(location.search);if(value)next.set(name,value);else next.delete(name);next.delete('from');navigate(`${base}/${view}?${next}`)};
 const reset=()=>navigate(location.pathname);
 const open=(item:Item)=>{returnPosition.current={key:filterKey,id:item.id,top:document.querySelector('.workspace')?.scrollTop??0};const next=new URLSearchParams(location.search);next.set('from',view);navigate(`${base}/records/${item.id}?${next}`)};
 const back=()=>{const from=params.get('from');const target=from&&['home','documents','favorites','references','recycle','search'].includes(from)?from:'documents';const next=new URLSearchParams(location.search);next.delete('from');navigate(`${base}/${target}${next.size?'?'+next:''}`)};
 const future=(id:FuturePanel['id'])=>currentSummary?.future_panels.find(p=>p.id===id);
 const offlineError=!online?new DiscoveryError('offline','网络已离线，请恢复连接后重新读取'):null;
 useEffect(()=>{
  const position=returnPosition.current;if(!isList||!currentList||position?.key!==filterKey)return;
  if(!currentList.items.some(item=>item.id===position.id)){returnPosition.current=null;return}
  const scroller=document.querySelector('.workspace');if(scroller)scroller.scrollTop=position.top;
 },[isList,currentList,filterKey]);
 const perform=async(command:Command)=>{
  if(!online||blockedHere||fatal||filterConflict||pending?.state==='pending')return;
  const captured=requestKey;const controller=new AbortController();commandController.current?.abort();commandController.current=controller;
  setCommandState({key:captured,command,state:'pending',message:'正在提交，请勿重复操作'});setFeedback(null);
  try{
   const receipt=await executeDiscoveryCommand(current,command,controller.signal);
   if(controller.signal.aborted||activeRequest.current!==captured)return;
   setCommandState(null);
   // Receipt.current is current at the transaction boundary; refresh again rather
   // than using a historical acknowledgement to overwrite a subsequent change.
   setFeedback({key:captured,message:`操作已确认${receipt.replayed?'（已核对原操作）':''} · ${receipt.operation_id}；正在读取当前状态`});
   await cache.invalidateQueries({queryKey:['discovery',current.actor_id,current.workspace_id]});
  }catch(error){
   if(controller.signal.aborted||activeRequest.current!==captured)return;
   const failure=error instanceof DiscoveryError?error:new DiscoveryError('unavailable','结果尚待确认');
   if(['authentication','forbidden','context'].includes(failure.failure)){
    controller.abort();commandController.current=null;activeRequest.current='';returnPosition.current=null;setCommandState(null);setFeedback(null);setBlocked({key:captured,error:failure});
    if(failure.failure==='authentication')onReject(failure);else onRefresh();
   }
   else if(failure.failure==='conflict'||failure.failure==='validation'){
    setCommandState(null);setFeedback({key:captured,message:failure.message});await cache.invalidateQueries({queryKey:['discovery',current.actor_id,current.workspace_id]});
   }else setCommandState({key:captured,command,state:'unknown',message:'结果尚待确认。核对时会重发相同操作标识与原始内容，服务端重新校验当前权限；请勿提交新操作。'});
  }
 };
 const confirm=(action:Command['action'])=>{
  if(!currentDetail||pending||!online||blockedHere||fatal)return;const item=currentDetail.item;
  const command:Command=action==='favorite.set'?{key:crypto.randomUUID(),resourceId:item.id,action,body:{favorite:!item.favorite,expected_revision:item.favorite_revision}}:{key:crypto.randomUUID(),resourceId:item.id,action,body:{expected_revision:item.revision,policy_version:currentDetail.actions.restore_policy_version!}};
  setCommandState({key:requestKey,command,state:'confirm',message:action==='favorite.set'?`确认${item.favorite?'取消':'添加'}你自己的收藏：${item.title}`:`确认恢复“${item.title}”的列表可见性；归档、版本与历史保持不变。`});
 };
 const filtersUi=<div className="discovery-filters"><label>记录类型<select value={filters.kind??''} aria-label="记录类型" disabled={['home','documents'].includes(view)} onChange={e=>setFilter('kind',e.target.value)}><option value="">全部类型</option>{kinds.filter(k=>view!=='references'||k!=='document').map(k=><option key={k} value={k}>{kindLabels[k]}</option>)}</select></label><label>文档类型<select value={documentType??''} onChange={e=>setFilter('type',e.target.value)}><option value="">全部文档类型</option>{documentTypes.map(k=><option key={k} value={k}>{typeLabels[k]}</option>)}</select></label><label>状态<select value={lifecycle??''} onChange={e=>setFilter('status',e.target.value)}><option value="">全部状态</option>{lifecycles.map(k=><option key={k} value={k}>{statusLabels[k]}</option>)}</select></label><button className="btn" onClick={reset}>重置筛选</button></div>;
 const tabsUi=<div className="tabs" role="tablist" aria-label="最近记录视图">{tabs.map((t,index)=><button key={t} id={`discovery-tab-${t}`} role="tab" aria-selected={filters.tab===t} aria-controls="discovery-list" tabIndex={filters.tab===t?0:-1} className={filters.tab===t?'active':''} onClick={()=>setFilter('tab',t)} onKeyDown={e=>{const delta=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;const next=e.key==='Home'?0:e.key==='End'?3:delta?(index+delta+4)%4:-1;if(next>=0){e.preventDefault();setFilter('tab',tabs[next]);document.getElementById(`discovery-tab-${tabs[next]}`)?.focus()}}}>{tabLabels[index]}</button>)}</div>;
 const listUi=<section className="recent-table" data-testid="discovery-list-section">{view!=='favorites'&&tabsUi}{filtersUi}<div id="discovery-list" role="tabpanel" aria-label={viewLabels[view]}>
  {feedback?.key===filterKey&&<p role="status">{feedback.message}</p>}{!filterConflict&&filters.collection==='todo'&&<p>待办集合：本人有权处理的自有草稿，与其他筛选条件同时生效。</p>}
  {isSearch&&<p>搜索范围：{current.name} · {search.query?`“${search.query}”`:'请在顶部输入关键词并按 Enter'}</p>}
  {(!isSearch||validSearch)&&<ReadState loading={list.isFetching||list.isPending} error={offlineError??conflictError??blockedHere??listError} empty={Boolean(currentList&&currentList.items.length===0&&currentFunctions.length===0)} filtered={isSearch||Boolean(documentType||lifecycle||kind||collection!=='all'||filters.tab!=='recent')} retry={retry} reset={reset} retryable={!filterConflict}/>}
  {currentList&&<><p className="discovery-count" data-testid="discovery-total">共 {currentList.total_count} 条当前授权记录{view==='recycle'?' · 仅回收站记录': ' · 不含回收站记录'}</p>{currentList.items.length>0&&<RecordTable page={currentList} current={current} onOpen={open} selected={returnPosition.current?.key===filterKey?returnPosition.current.id:undefined}/>}{currentFunctions.length>0&&<section aria-label="功能结果"><h3>功能</h3>{currentFunctions.map(f=><button className="btn" key={f.id} onClick={()=>navigate(`${base}/${f.route}`)}>{f.title} · {current.name}</button>)}</section>}
   <div className="discovery-pagination"><span>第 {cursors.length+1} 页{!currentList.next_cursor?' · 已是末页':''}</span><button className="btn" disabled={cursors.length===0} onClick={()=>setPagination({key:filterKey,cursors:cursors.slice(0,-1)})}>上一页记录</button><button className="btn" disabled={!currentList.next_cursor} onClick={()=>setPagination({key:filterKey,cursors:[...cursors,currentList.next_cursor!]})}>下一页记录</button><button className="btn" onClick={retry}>刷新记录</button></div></>}
 </div></section>;
 const title=<header className="page-header"><div><h1 tabIndex={-1}>{viewLabels[view]??'记录发现'}</h1><p>当前项目：{current.name} · 仅显示当前权限允许的元数据</p></div><span className="grow"/><button className="btn" onClick={()=>navigate(`${base}/home`)}>返回工作台</button></header>;
 const writeUi=pending&&<section className="discovery-command" role="status" data-testid="discovery-command" data-state={pending.state}><p>{pending.message}</p>{pending.state==='confirm'?<><button className="btn" onClick={()=>setCommandState(null)}>取消</button><button className="btn primary" disabled={!online} onClick={()=>void perform(pending.command)}>确认操作</button></>:pending.state==='unknown'?<button className="btn" disabled={!online} onClick={()=>void perform(pending.command)}>核对原操作</button>:null}</section>;
 const detailUi=<>{title}<div className="discovery-body"><button className="btn" onClick={back}>返回记录列表</button><ReadState loading={detail.isFetching||detail.isPending} error={offlineError??blockedHere??detailError} retry={retry}/>{currentDetail&&<article data-testid="discovery-detail"><h2>{currentDetail.item.title}</h2><p className="notice">仅有元数据；正文、编辑与版本内容尚未开放。</p><dl className="discovery-metadata">{[['记录 ID',currentDetail.item.id],['所属项目',current.name],['项目 ID',currentDetail.item.workspace_id],['记录类型',kindLabels[currentDetail.item.kind]],['文档类型',currentDetail.item.document_type?typeLabels[currentDetail.item.document_type]:'未提供'],['状态',statusLabels[currentDetail.item.lifecycle]],['可见性',currentDetail.item.visibility==='recycled'?'回收站':'正常列表'],['创建者 ID',currentDetail.item.created_by],['创建时间',stamp(currentDetail.item.created_at)],['最后更新',stamp(currentDetail.item.updated_at)],['版本',currentDetail.item.version_label??'未提供版本标识']].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><div className="discovery-actions"><button className="btn" disabled={!currentDetail.actions.favorite||Boolean(pending)||!online} onClick={()=>confirm('favorite.set')}>{currentDetail.item.favorite?'取消收藏':'添加收藏'}</button>{currentDetail.item.visibility==='recycled'&&<button className="btn" disabled={!currentDetail.actions.restore||Boolean(pending)||!online} onClick={()=>confirm('restore_visibility')}>恢复列表可见性</button>}<button className="btn" disabled={Boolean(pending)} onClick={retry}>刷新详情</button></div>{currentDetail.item.visibility==='recycled'&&!currentDetail.actions.restore&&<p>当前权限或恢复策略不支持此记录；保留记录与历史。</p>}{currentDetail.item.lifecycle==='ARCHIVED'&&<p>归档内容只读。收藏或恢复列表可见性不会修改归档状态。</p>}</article>}{writeUi}{feedback?.key===requestKey&&<p role="status" className="notice">{feedback.message}</p>}</div></>;
 const homeUi=<div className="home-wrap discovery-home"><div><section className="hero"><h2>👋 你好，{current.display_name}</h2><div className="hero-subtitle">专注文档创作，用智能让专业更高效</div><div className="quote">“好的文档，是好项目的开始。”</div></section><ReadState loading={summary.isFetching} error={offlineError??blockedHere??summaryError} retry={retry}/><section className="kpis" data-testid="discovery-kpis"><div className="kpi"><div className="kt"><span className="ki">▤</span>本周新建文档</div><strong>{currentSummary?.week_new_documents.value??'—'}</strong><span className="discovery-reason">{currentSummary?<>UTC 周一至计量时刻<br/>{stamp(currentSummary.week_new_documents.window_start)} 至 {stamp(currentSummary.week_new_documents.window_end)}<br/>当前授权正常列表文档；无可比上周数据</>:'正在读取实际统计'}</span></div>{(['review','ai_words','quality'] as const).map((id,index)=><div className="kpi" key={id}><div className="kt"><span className="ki">{['✓','✦','★'][index]}</span>{['已完成审校','AI 生成字数','质量均分'][index]}</div><strong>—</strong><Future panel={future(id)}/></div>)}</section><section className="quad" data-testid="discovery-home-cards"><div className="mini-card"><div className="card-title">待办文档（{currentTodo?.total_count??'—'}）<button className="more" onClick={()=>navigate(`${base}/documents?collection=todo`)}>更多 ›</button></div><ReadState loading={todo.isFetching} error={offlineError??blockedHere??todoError} empty={currentTodo?.total_count===0} retry={retry}/>{currentTodo?.items.map(item=><div className="list-row" key={item.id}><span className="doc-ico">▤</span><div><button className="discovery-link" onClick={()=>open(item)}>{item.title}</button><div className="meta">最后更新 {stamp(item.updated_at)}</div></div><span className="pill">待完成</span></div>)}<p className="discovery-reason">当前可见且本人有权处理的自有草稿。</p></div><div className="mini-card"><div className="card-title">最近项目<button className="more" onClick={()=>navigate(`${base}/projects`)}>更多 ›</button></div><ReadState loading={projects.isFetching} error={offlineError??blockedHere??projectsError} empty={currentProjects?.items.length===0} retry={retry}/>{currentProjects?.items.slice(0,3).map(p=><div className="list-row" key={p.workspace.id}><span className="doc-ico">▣</span><div><button className="discovery-link" onClick={()=>navigate(`/workspaces/${p.workspace.id}/project`)}>{p.workspace.name}</button><div className="meta">{p.last_activity_at?`最后活动 ${stamp(p.last_activity_at)}`:'暂无记录活动'}</div></div></div>)}<p className="discovery-reason">当前可访问项目页内按实际活动排序。</p></div><div className="mini-card"><div className="card-title">审校提醒<button className="more" disabled>更多 ›</button></div><Future panel={future('review')}/></div><div className="mini-card"><div className="card-title">模板快捷入口<button className="more" disabled>更多 ›</button></div><Future panel={future('templates')}/></div></section>{listUi}</div><aside className="rightcol"><div className="quick"><div className="card-title">快速新建<button className="more" onClick={()=>setCatalogOpen(v=>!v)} aria-expanded={catalogOpen}>更多 ›</button></div>{quickTypes.map(([label,description])=><button className="quick-item" key={label} disabled aria-describedby="creation-unavailable"><span className="qico">▤</span><span><b>{label}</b><span className="meta">{description}</span></span><span className="grow"/>›</button>)}<div id="creation-unavailable"><Future panel={future('creation')}/></div>{catalogOpen&&<section className="discovery-catalog"><h3>完整文档类型</h3><ul>{catalog.map(t=><li key={t}>{t} · 创建尚未开放</li>)}</ul></section>}</div><div className="ai-rec"><div className="card-title">✦ AI 推荐<button className="more" disabled>换一批 ↻</button></div><Future panel={future('recommendations')}/><button className="btn" disabled>使用</button> <button className="btn" disabled>创建</button></div></aside></div>;
 const projectsUi=<>{title}<div className="discovery-body"><p>每页最多 50 个当前授权项目，页内按实际记录活动时间排序；没有活动的项目单独标明。</p><ReadState loading={projects.isPending||projects.isFetching} error={offlineError??blockedHere??projectsError} empty={currentProjects?.items.length===0} retry={retry}/>{currentProjects&&<><table data-testid="discovery-projects"><thead><tr><th>项目</th><th>项目标识</th><th>最近活动</th></tr></thead><tbody>{currentProjects.items.map(p=><tr key={p.workspace.id}><td><button className="discovery-link" onClick={()=>navigate(`/workspaces/${p.workspace.id}/project`)}>{p.workspace.name}</button></td><td>{p.workspace.project_id}</td><td>{p.last_activity_at?stamp(p.last_activity_at):'暂无记录活动'}</td></tr>)}</tbody></table><div className="discovery-pagination"><span>第 {cursors.length+1} 页</span><button className="btn" disabled={!cursors.length} onClick={()=>setPagination({key:filterKey,cursors:cursors.slice(0,-1)})}>上一页项目</button><button className="btn" disabled={!currentProjects.next_cursor} onClick={()=>setPagination({key:filterKey,cursors:[...cursors,currentProjects.next_cursor!]})}>下一页项目</button></div></>}</div></>;
 const projectUi=<>{title}<div className="discovery-body"><ReadState loading={summary.isPending||summary.isFetching} error={offlineError??blockedHere??summaryError} retry={retry}/>{currentSummary&&<ProjectInfo summary={currentSummary} openDocuments={()=>navigate(`${base}/documents`)}/>}</div></>;
 return <>{portal&&!filterConflict&&createPortal(<StorageInfo value={safeStorage}/>,portal)}<div className="discovery-root" data-testid="discovery-root" data-view={view} data-context={scope}>{filterConflict?<>{title}<div className="discovery-body"><ReadState error={conflictError} retry={retry} reset={reset} retryable={false}/></div></>:view==='home'?homeUi:resourceId?detailUi:view==='project'?projectUi:view==='projects'?projectsUi:<>{title}<div className="discovery-body">{view==='references'&&<p>已注册的参考资料与知识元数据；正文检索、上传和 Evidence 尚未开放。</p>}{view==='recycle'&&<p>回收站只管理列表可见性；不提供永久删除或保留期限推断。</p>}{listUi}</div></>}</div></>;
}
function ProjectInfo({summary,openDocuments}:{summary:Summary;openDocuments:()=>void}){return <article data-testid="discovery-project"><h2>{summary.workspace.name}</h2><dl className="discovery-metadata">{[['项目 ID',summary.workspace.id],['项目标识',summary.workspace.project_id],['客户',summary.workspace.customer_id],['产品',summary.workspace.product_id],['部门',summary.workspace.department],['密级',`L${summary.workspace.classification}`],['当前授权记录',String(summary.total_count)],['最近活动',summary.last_activity_at?stamp(summary.last_activity_at):'暂无记录活动']].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><button className="btn" onClick={openDocuments}>打开项目文档</button></article>}
