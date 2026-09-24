import {useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {useLocation,useNavigate} from 'react-router-dom';
import {useQueryClient} from '@tanstack/react-query';
import {beginLogin,clearSession,finishLogin,logout,token} from '../auth/oidc';
import {Account,AccountRequestError,getMe,getReadiness,isAuthenticationRejection,isWorkspaceForbidden} from './api';
import {getWorkspace,WorkspaceAccess} from './access-api';
import AccessPanel from './AccessPanel';
import DiscoveryPanel from '../features/workspace/DiscoveryPanel';
import TaskCenter from '../features/tasks/TaskCenter';
import {type TaskAction,forgetTaskAction,restoreTaskAction} from '../features/tasks/task-action';
import {sameContext,validDiscoveryQuery} from './discovery-api';
import {getUnreadNotification,TaskError} from './task-api';
import './prototype.css';
import './workspace.css';

const nav=['工作台','项目文档','知识库','模板中心','审校管理','数据分析'];
const sideNav=['工作台','项目文档','知识管理','模板中心','审校管理','数据分析'];
const unavailableMessage='此功能尚未开放';
const validId=(id:string|undefined)=>id===undefined||/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
const limitSearchText=(value:string)=>Array.from(value).slice(0,128).join('');
const isAuthenticationFailure=(error:unknown):error is AccountRequestError|TaskError=>isAuthenticationRejection(error)||error instanceof TaskError&&error.failure==='authentication';

export default function App(){
 const route=useLocation();const navigate=useNavigate();const cache=useQueryClient();
 const routeWorkspace=/^\/workspaces\/([^/]+)/.exec(route.pathname)?.[1]?.toLowerCase();
 const resourceId=/^\/workspaces\/[^/]+\/resources\/([^/]+)/.exec(route.pathname)?.[1]?.toLowerCase();
 const discoveryId=/^\/workspaces\/[^/]+\/records\/([^/]+)/.exec(route.pathname)?.[1]?.toLowerCase();
 const taskId=/^\/workspaces\/[^/]+\/tasks\/([^/]+)$/.exec(route.pathname)?.[1]?.toLowerCase();
 const supportedRoute=['/','/auth/callback','/admin/members'].includes(route.pathname)
   ||/^\/workspaces\/[^/]+\/(home|documents|favorites|references|recycle|search|project|projects|account|tasks|notifications|tasks\/[^/]+|resources\/[^/]+|records\/[^/]+)$/.test(route.pathname);
 const validIdentifiers=supportedRoute&&validId(routeWorkspace)&&validId(resourceId)&&validId(discoveryId)&&validId(taskId)&&(route.pathname==='/auth/callback'||validDiscoveryQuery(route.search));
 const [workspace,setWorkspace]=useState<WorkspaceAccess|null>(null);
 const [accessResult,setAccessResult]=useState('');
 const [account,setAccount]=useState<Account|null>(null);
 const [auth,setAuth]=useState('正在检查登录状态');
 const [ready,setReady]=useState('正在检查依赖');
 const [error,setError]=useState('');
 const [workspaceForbidden,setWorkspaceForbidden]=useState(false);
 const [toast,setToast]=useState({message:'',shown:false});
 const [taskAction,setTaskAction]=useState<TaskAction|null>(null);
 const actionAbort=useRef<AbortController|null>(null);
 const [hasUnread,setHasUnread]=useState<boolean|null>(null);
 const unreadScope=useRef<string|null>(null);
 const [notificationRevision,setNotificationRevision]=useState(0);
 const [searchText,setSearchText]=useState('');
 const [search,setSearch]=useState({query:'',sequence:0});
 const [searchInputKey,setSearchInputKey]=useState(0);
 const searchComposing=useRef(false);
 const clearSearch=useCallback(()=>{
   searchComposing.current=false;setSearchText('');setSearch({query:'',sequence:0});
   // Cancel the browser's composition range as well as React's search state.
   setSearchInputKey(key=>key+1);
 },[]);
 const currentContext=useRef<WorkspaceAccess|null>(null);
 const previousRouteWorkspace=useRef<string|undefined>(undefined);
 const clearTaskSession=useCallback((forget=true)=>{actionAbort.current?.abort();actionAbort.current=null;setTaskAction(null);setHasUnread(null);if(forget)forgetTaskAction()},[]);
 const clearControlled=useCallback(()=>{
   for(const queryKey of [['access'],['discovery']]){void cache.cancelQueries({queryKey});cache.removeQueries({queryKey})}
 },[cache]);
 const accountGeneration=useRef(0);
 const accountInFlight=useRef<number|null>(null);
 const accountRefreshBlocked=useRef(false);
 const mounted=useRef(false);
 const toastTimer=useRef<ReturnType<typeof setTimeout>|null>(null);

 const isCurrentAccountLoad=useCallback((generation:number)=>mounted.current&&accountGeneration.current===generation,[]);
 const load=useCallback(async(generation:number)=>{
   if(!isCurrentAccountLoad(generation))return;
   setError('');
   try{
     if(route.pathname==='/auth/callback'){
       const destination=await finishLogin();
       if(!isCurrentAccountLoad(generation))return;
       navigate(destination,{replace:true});return;
     }
     if(!isCurrentAccountLoad(generation))return;
     const currentToken=token();
     if(!currentToken){setAccount(null);setWorkspace(null);currentContext.current=null;clearSearch();clearControlled();clearTaskSession(false);setAuth('需要登录');return}
     setAuth('正在载入当前账户');
     if(!validIdentifiers)throw new AccountRequestError('项目或资源地址无效','forbidden',403);
     let nextAccount=await getMe();
     if(!isCurrentAccountLoad(generation)||token()!==currentToken)return;
     let nextWorkspace;
     try{nextWorkspace=await getWorkspace(routeWorkspace??nextAccount.workspace_id)}
     catch(e){
       if(routeWorkspace||!isWorkspaceForbidden(e)||!isCurrentAccountLoad(generation))throw e;
       nextAccount=await getMe();
       if(!isCurrentAccountLoad(generation)||token()!==currentToken)return;
       try{nextWorkspace=await getWorkspace(nextAccount.workspace_id)}
       catch(retryError){
         if(isWorkspaceForbidden(retryError))throw new AccountRequestError('项目权限正在变化，请重试','transient',503);
         throw retryError;
       }
     }
     if(!isCurrentAccountLoad(generation)||token()!==currentToken)return;
     if(nextWorkspace.actor_id!==nextAccount.actor_id)throw new Error('身份上下文不一致');
     if(currentContext.current&&!sameContext(currentContext.current,nextWorkspace)){
       clearControlled();clearTaskSession();clearSearch();setAccessResult('');
     }
     currentContext.current=nextWorkspace;
     const nextScope=[nextWorkspace.actor_id,nextWorkspace.workspace_id,...nextWorkspace.policy_epoch].join(':');
     setTaskAction(old=>old?.scope===nextScope?old:restoreTaskAction(nextScope));
     accountRefreshBlocked.current=false;setWorkspaceForbidden(false);
     setWorkspace(nextWorkspace);
     setAccount({...nextAccount,workspace_id:nextWorkspace.workspace_id,workspace_name:nextWorkspace.name,workspace_slug:nextWorkspace.slug});setAuth('已安全登录');
     if(route.pathname==='/')navigate(`/workspaces/${nextWorkspace.workspace_id}/home`,{replace:true});
   }catch(e){
     if(!isCurrentAccountLoad(generation))return;
     setAccount(null);setAccessResult('');
     setWorkspace(null);currentContext.current=null;clearControlled();
     if(isAuthenticationFailure(e)){
       clearTaskSession();
       clearSearch();
       accountGeneration.current+=1;
       accountRefreshBlocked.current=false;setWorkspaceForbidden(false);
       clearSession();setAuth('认证失败');setError(e.message);
     }else if(isWorkspaceForbidden(e)){
       clearTaskSession();
       clearSearch();
       accountRefreshBlocked.current=true;setWorkspaceForbidden(true);
       setAuth('工作区访问被拒绝');setError(e.message);
     }else{
       setAuth(token()?'账户服务暂时不可用':'认证失败');
       const message=e instanceof Error?e.message:'账户请求失败';
       setError(token()?`${message}；将自动重试，也可手动重试`:`${message}；请重新登录`);
     }
   }
 },[isCurrentAccountLoad,routeWorkspace,validIdentifiers,route.pathname,navigate,clearControlled,clearSearch,clearTaskSession]);
 const rejectAccess=useCallback((e:unknown)=>{
   accountGeneration.current+=1;setAccount(null);setWorkspace(null);setAccessResult('');currentContext.current=null;clearSearch();clearControlled();clearTaskSession();
   if(isWorkspaceForbidden(e)&&!routeWorkspace){
     accountRefreshBlocked.current=false;setWorkspaceForbidden(false);setError('');
     const generation=accountGeneration.current;accountInFlight.current=generation;
     void load(generation).finally(()=>{if(accountInFlight.current===generation)accountInFlight.current=null});
     return;
   }
   if(isAuthenticationFailure(e)){clearSession();setAuth('认证失败');accountRefreshBlocked.current=false}
   else{setWorkspaceForbidden(true);accountRefreshBlocked.current=true;setAuth('工作区访问被拒绝')}
   setError(e instanceof Error?e.message:'当前权限不允许此访问');
 },[clearControlled,clearSearch,clearTaskSession,routeWorkspace,load]);
 const refreshAccount=useCallback(()=>{
   const generation=++accountGeneration.current;accountInFlight.current=generation;
   void load(generation).finally(()=>{if(accountInFlight.current===generation)accountInFlight.current=null});
 },[load]);
 const showToast=useCallback((message:string)=>{
   if(toastTimer.current!==null)clearTimeout(toastTimer.current);
   setToast({message,shown:true});
   toastTimer.current=setTimeout(()=>{toastTimer.current=null;if(mounted.current)setToast(current=>({...current,shown:false}))},1800);
 },[]);
 const signOut=()=>{
   accountGeneration.current+=1;
   setWorkspace(null);setAccessResult('');currentContext.current=null;clearSearch();clearControlled();clearTaskSession();
   accountRefreshBlocked.current=false;setWorkspaceForbidden(false);
   setAccount(null);setAuth('正在安全退出');setError('');logout();
 };

 useLayoutEffect(()=>{
   accountGeneration.current+=1;setAccount(null);setWorkspace(null);setAccessResult('');
   currentContext.current=null;clearSearch();clearControlled();clearTaskSession(Boolean(previousRouteWorkspace.current&&previousRouteWorkspace.current!==routeWorkspace));
   previousRouteWorkspace.current=routeWorkspace;
 },[routeWorkspace,clearControlled,clearSearch,clearTaskSession]);

 useEffect(()=>{
   mounted.current=true;
   let active=true;
   const refreshReadiness=()=>void getReadiness().then(value=>{if(active)setReady(value)}).catch(e=>{if(active)setReady(e instanceof Error?e.message:'本地依赖尚未就绪')});
   refreshAccount();refreshReadiness();
   const timer=setInterval(()=>{if(token()&&!accountRefreshBlocked.current&&accountInFlight.current===null)refreshAccount();refreshReadiness()},15000);
   return()=>{
     active=false;mounted.current=false;accountGeneration.current+=1;clearInterval(timer);
     if(toastTimer.current!==null){clearTimeout(toastTimer.current);toastTimer.current=null}
   };
 },[refreshAccount]);
 useEffect(()=>()=>{actionAbort.current?.abort()},[]);

 const bellScope=validIdentifiers&&account&&workspace&&account.workspace_id===workspace.workspace_id&&(!routeWorkspace||routeWorkspace===workspace.workspace_id)
   ?[workspace.actor_id,workspace.workspace_id,...workspace.policy_epoch].join(':'):null;
 const bellWorkspaceId=bellScope?workspace?.workspace_id:null;
 const visibleUnread=unreadScope.current===bellScope?hasUnread:null;
 useEffect(()=>{
   if(unreadScope.current!==bellScope){unreadScope.current=bellScope;setHasUnread(null)}
   if(!bellScope||!bellWorkspaceId){setHasUnread(null);return}
   let active=true;let controller:AbortController|null=null;
   const scan=async()=>{
     controller?.abort();const request=new AbortController();controller=request;
     try{
       const unread=await getUnreadNotification(bellWorkspaceId,request.signal);
       if(active&&!request.signal.aborted&&unreadScope.current===bellScope)setHasUnread(unread);
     }catch(cause){if(active&&!request.signal.aborted&&unreadScope.current===bellScope){setHasUnread(null);if(cause instanceof TaskError&&['authentication','forbidden'].includes(cause.failure))rejectAccess(cause)}}
   };
   void scan();const timer=setInterval(()=>void scan(),30000);
   return()=>{active=false;clearInterval(timer);controller?.abort()};
 },[bellScope,bellWorkspaceId,notificationRevision,route.pathname,rejectAccess]);

 const visibleAccount=!validIdentifiers||(routeWorkspace&&account?.workspace_id!==routeWorkspace)?null:account;
 const initial=visibleAccount?.display_name.slice(0,1)??'访';
 const hasSession=Boolean(token());
 const base=visibleAccount?`/workspaces/${visibleAccount.workspace_id}`:'';
 const taskScope=workspace?[workspace.actor_id,workspace.workspace_id,...workspace.policy_epoch].join(':'):'';
 const accountPage=route.pathname==='/admin/members'||route.pathname.endsWith('/account')||Boolean(resourceId);
 const currentView=route.pathname.split('/')[3]??'home';
 const taskPage=currentView==='tasks'||currentView==='notifications';
 const go=(view:string)=>{if(visibleAccount)navigate(`${base}/${view}`)};
 const navAction=(index:number)=>{if(index===0)go('home');else if(index===1)go('documents');else if(index===2)go('references');else showToast(unavailableMessage)};
 const activeNav=currentView==='documents'||currentView==='records'?1:currentView==='references'?2:0;
 const accountState=<><b>工作区状态 · 本地测试环境</b><p data-testid="auth-status">{auth}</p><p data-testid="ready-status">{ready}</p>{error&&<p className="error" role="alert">{error}</p>}{!visibleAccount?(workspaceForbidden?<button className="btn" onClick={signOut}>安全退出</button>:hasSession?<button className="btn primary" onClick={refreshAccount}>重试账户加载</button>:<button className="btn primary" onClick={()=>void beginLogin().catch(e=>setError(e instanceof Error?e.message:'认证失败'))}>登录工作区</button>):<button className="btn" onClick={signOut}>安全退出</button>}</>;
 return <div className="app">
  <header className="topbar"><div className="brand"><span className="logo"/>企业智能文档编写工作台</div>
   <nav className="topnav" id="topnav" aria-label="主导航">{nav.map((n,i)=><button className={i===activeNav?'active':''} aria-current={i===activeNav?'page':undefined} key={n} onClick={()=>navAction(i)}><span className="ico">{['⌂','▣','▤','⌘','✓','▥'][i]}</span>{n}</button>)}</nav>
   <div className="top-spacer"/><input key={searchInputKey} className="global-search" id="globalSearch" aria-label="全局搜索" placeholder="搜索文档、知识或功能..." disabled={!visibleAccount} value={searchText}
    onCompositionStart={()=>{searchComposing.current=true}}
    onCompositionEnd={e=>{searchComposing.current=false;setSearchText(limitSearchText(e.currentTarget.value))}}
    onChange={e=>setSearchText(searchComposing.current?e.target.value:limitSearchText(e.target.value))}
    onKeyDown={e=>{if(e.key==='Enter'&&!searchComposing.current&&!e.nativeEvent.isComposing&&e.nativeEvent.keyCode!==229&&searchText.trim()&&!searchText.includes('\0')){setSearch(old=>({query:searchText.trim(),sequence:old.sequence+1}));go('search')}}}/>
       <div className={`bell${visibleUnread===true?' unread':''}`} role="button" tabIndex={visibleAccount?0:-1} aria-label={visibleUnread===null?'通知，未读状态待确认':'通知'} aria-disabled={!visibleAccount} onClick={()=>go('notifications')} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go('notifications')}}}>♧</div>
   <button className="avatar account-toggle" aria-label="账户与会话" disabled={!visibleAccount} onClick={()=>go('account')}>{initial}</button><div className="uinfo"><b>{visibleAccount?.display_name??'未登录'}</b><small>{visibleAccount?.department??auth}</small></div>
  </header>
  <div className="shell"><aside className="sidebar" id="sidebar" aria-label="项目导航">
   <div className="side-title"><span>▧ 项目空间</span><button className="account-toggle" aria-label="打开项目选择" onClick={()=>go('account')}>⌄</button></div>
   <div className="project-card" role="button" tabIndex={0} aria-label="选择项目" onClick={()=>go('account')} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go('account')}}}><div className="project-icon">≡</div><div className="project-card-copy"><b>{visibleAccount?.workspace_name??'等待身份映射'}</b><small>{visibleAccount?.workspace_slug??(workspaceForbidden?'当前账户无权访问':'登录后显示工作区')}</small></div><span className="status">{visibleAccount?'当前':'未进入'}</span></div>
   <div className="side-menu">{sideNav.map((n,i)=><button className={`side-item ${i===activeNav?'active':''}`} key={n} onClick={()=>navAction(i)}>{`${['⌂','▣','▤','⌘','◈','▥'][i]} ${n}`}</button>)}</div><div style={{height:8}}/>
   {['☆ 我的收藏','▣ 参考资料','♲ 回收站'].map((n,i)=><button className={`side-item ${currentView===['favorites','references','recycle'][i]?'active':''}`} key={n} onClick={()=>go(['favorites','references','recycle'][i])}>{n}</button>)}
   <div className="side-bottom"><div id="discovery-storage-slot">{(!visibleAccount||accountPage)&&<div className="storage storage-fallback"><div className="storage-fallback-content"><b>可见记录元数据占用</b><p>尚未统计</p><small>打开记录集合后显示；附件与总体配额未知。</small></div></div>}</div></div>
  </aside><main className="page active"><section className="workspace">
   {!visibleAccount?<><div className="hero"><h2>👋 欢迎进入安全工作区</h2><p>{workspaceForbidden?'当前账户无法进入此工作区。':'登录后才能进入工作区。'}</p></div><div className="notice">{accountState}</div></>:workspace&&workspace.workspace_id===visibleAccount.workspace_id?<>
	    {accountPage?<><header className="page-header"><h1>项目与账户</h1><span className="grow"/><button className="btn" onClick={()=>go('home')}>返回工作台</button></header><div className="notice">{accountState}</div>{accessResult&&<p className="notice" role="status">{accessResult}</p>}<AccessPanel key={`${route.pathname}:${workspace.actor_id}:${workspace.workspace_id}:${workspace.policy_epoch.join(':')}`} current={workspace} onReject={rejectAccess} onRefresh={refreshAccount} onSaved={setAccessResult} resourceId={resourceId}/></>:taskPage?<TaskCenter key={taskScope} current={workspace} onReject={rejectAccess} onRefresh={refreshAccount} onNotificationsChanged={()=>setNotificationRevision(value=>value+1)} action={taskAction?.scope===taskScope?taskAction:null} setAction={setTaskAction} actionAbort={actionAbort}/>:<><DiscoveryPanel key={`${workspace.actor_id}:${workspace.workspace_id}:${workspace.policy_epoch.join(':')}`} current={workspace} search={search} onReject={rejectAccess} onRefresh={refreshAccount}/><details className="workspace-runtime"><summary>账户与运行状态</summary>{accountState}</details></>}
   </>:null}
  </section></main></div><div className={`toast${toast.shown?' show':''}`} role="status" aria-live="polite">{toast.message}</div><div className="mobile-note">建议在 1180px 以上桌面浏览器查看此原型。</div>
 </div>
}
