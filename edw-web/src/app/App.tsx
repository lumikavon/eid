import {useCallback,useEffect,useRef,useState} from 'react';
import {beginLogin,clearSession,finishLogin,logout,token} from '../auth/oidc';
import {Account,getMe,getReadiness,isAuthenticationRejection,isWorkspaceForbidden} from './api';
import './prototype.css';
import './workspace.css';

const nav=['工作台','项目文档','知识库','模板中心','审校管理','数据分析'];
const sideNav=['工作台','项目文档','知识管理','模板中心','审校管理','数据分析'];
const unavailableMessage='此功能尚未开放';

export default function App(){
 const [account,setAccount]=useState<Account|null>(null);
 const [auth,setAuth]=useState('正在检查登录状态');
 const [ready,setReady]=useState('正在检查依赖');
 const [error,setError]=useState('');
 const [workspaceForbidden,setWorkspaceForbidden]=useState(false);
 const [toast,setToast]=useState({message:'',shown:false});
 const accountGeneration=useRef(0);
 const accountRefreshBlocked=useRef(false);
 const mounted=useRef(false);
 const toastTimer=useRef<ReturnType<typeof setTimeout>|null>(null);

 const isCurrentAccountLoad=useCallback((generation:number)=>mounted.current&&accountGeneration.current===generation,[]);
 const load=useCallback(async(generation:number)=>{
   if(!isCurrentAccountLoad(generation))return;
   setError('');
   try{
     if(location.pathname==='/auth/callback')await finishLogin();
     if(!isCurrentAccountLoad(generation))return;
     const currentToken=token();
     if(!currentToken){setAccount(null);setAuth('需要登录');return}
     setAuth('正在载入当前账户');
     const nextAccount=await getMe();
     if(!isCurrentAccountLoad(generation)||token()!==currentToken)return;
     accountRefreshBlocked.current=false;setWorkspaceForbidden(false);
     setAccount(nextAccount);setAuth('已安全登录');
   }catch(e){
     if(!isCurrentAccountLoad(generation))return;
     setAccount(null);
     if(isAuthenticationRejection(e)){
       accountGeneration.current+=1;
       accountRefreshBlocked.current=false;setWorkspaceForbidden(false);
       clearSession();setAuth('认证失败');setError(e.message);
     }else if(isWorkspaceForbidden(e)){
       accountRefreshBlocked.current=true;setWorkspaceForbidden(true);
       setAuth('工作区访问被拒绝');setError(e.message);
     }else{
       setAuth(token()?'账户服务暂时不可用':'认证失败');
       const message=e instanceof Error?e.message:'账户请求失败';
       setError(token()?`${message}；将自动重试，也可手动重试`:`${message}；请重新登录`);
     }
   }
 },[isCurrentAccountLoad]);
 const refreshAccount=useCallback(()=>{const generation=++accountGeneration.current;void load(generation)},[load]);
 const showToast=useCallback((message:string)=>{
   if(toastTimer.current!==null)clearTimeout(toastTimer.current);
   setToast({message,shown:true});
   toastTimer.current=setTimeout(()=>{toastTimer.current=null;if(mounted.current)setToast(current=>({...current,shown:false}))},1800);
 },[]);
 const signOut=()=>{
   accountGeneration.current+=1;
   accountRefreshBlocked.current=false;setWorkspaceForbidden(false);
   setAccount(null);setAuth('正在安全退出');setError('');logout();
 };

 useEffect(()=>{
   mounted.current=true;
   let active=true;
   const refreshReadiness=()=>void getReadiness().then(value=>{if(active)setReady(value)}).catch(e=>{if(active)setReady(e instanceof Error?e.message:'本地依赖尚未就绪')});
   refreshAccount();refreshReadiness();
   const timer=setInterval(()=>{if(token()&&!accountRefreshBlocked.current)refreshAccount();refreshReadiness()},15000);
   return()=>{
     active=false;mounted.current=false;accountGeneration.current+=1;clearInterval(timer);
     if(toastTimer.current!==null){clearTimeout(toastTimer.current);toastTimer.current=null}
   };
 },[refreshAccount]);

 const initial=account?.display_name.slice(0,1)??'访';
 const hasSession=Boolean(token());
 return <div className="app"><header className="topbar"><div className="brand"><span className="logo"/>企业智能文档编写工作台</div><nav className="topnav" id="topnav">{nav.map((n,i)=><button className={i===0?'active':''} key={n} onClick={()=>{if(i!==0)showToast(unavailableMessage)}}><span className="ico">{['⌂','▣','▤','⌘','✓','▥'][i]}</span>{n}</button>)}</nav><div className="top-spacer"/><input className="global-search" id="globalSearch" aria-label="全局搜索" placeholder="搜索文档、知识或功能..." readOnly onClick={()=>showToast('搜索功能尚未开放')}/><div className="bell" role="button" tabIndex={0} aria-label="通知" onClick={()=>showToast('通知功能尚未开放')} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showToast('通知功能尚未开放')}}}>♧</div><div className="avatar">{initial}</div><div className="uinfo"><b>{account?.display_name??'未登录'}</b><small>{account?.department??auth}</small></div></header>
 <div className="shell"><aside className="sidebar" id="sidebar"><div className="side-title"><span>▧ 项目空间</span><span>⌄</span></div><div className="project-card"><div className="project-icon">≡</div><div className="project-card-copy"><b>{account?.workspace_name??'等待身份映射'}</b><small>{account?.workspace_slug??(workspaceForbidden?'当前账户无权访问':'登录后显示工作区')}</small></div><span className="status">{account?'当前':'未进入'}</span></div><div className="side-menu">{sideNav.map((n,i)=><button className={`side-item ${i===0?'active':''}`} key={n} onClick={()=>{if(i!==0)showToast(unavailableMessage)}}>{`${['⌂','▣','▤','⌘','◈','▥'][i]} ${n}`}</button>)}</div><div style={{height:8}}/>{['☆ 我的收藏','▣ 参考资料','♲ 回收站'].map(n=><button className="side-item" key={n} onClick={()=>showToast(unavailableMessage)}>{n}</button>)}<div className="side-bottom"><div className="storage"><b>项目存储空间</b><div className="progress unknown"><i/></div><small>尚未统计</small></div></div></aside>
 <main className="page active"><section className="workspace"><div className="hero"><h2>👋 {account?`你好，${account.display_name}`:'欢迎进入安全工作区'}</h2><p>{account?'当前工作区已连接。':workspaceForbidden?'当前账户无法进入此工作区。':'登录后才能进入工作区。'}</p></div><div className="notice"><b>工作区状态 · 本地测试环境</b><p data-testid="auth-status">{auth}</p><p data-testid="ready-status">{ready}</p>{error&&<p className="error" role="alert">{error}</p>}{!account?(workspaceForbidden?<button className="btn" onClick={signOut}>安全退出</button>:hasSession?<button className="btn primary" onClick={refreshAccount}>重试账户加载</button>:<button className="btn primary" onClick={()=>void beginLogin().catch(e=>setError(e instanceof Error?e.message:'认证失败'))}>登录工作区</button>):<button className="btn" onClick={signOut}>安全退出</button>}</div></section></main></div><div className={`toast${toast.shown?' show':''}`} role="status" aria-live="polite">{toast.message}</div><div className="mobile-note">建议在 1180px 以上桌面浏览器查看此原型。</div></div>
}
