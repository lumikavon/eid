import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {useLocation,useNavigate} from 'react-router-dom';
import {getMembers,getResource,getWorkspace,getWorkspaces,Member,roles,saveMember,WorkspaceAccess} from './access-api';
import {AccountRequestError,isAuthenticationRejection,isWorkspaceForbidden} from './api';

export default function AccessPanel({current,onReject,onRefresh,onSaved,resourceId}:{current:WorkspaceAccess;onReject:(error:unknown)=>void;onRefresh:()=>void;onSaved:(message:string)=>void;resourceId?:string}){
 const navigate=useNavigate();const {pathname}=useLocation();const cache=useQueryClient();const [admin,setAdmin]=useState(pathname==='/admin/members');
 const [editing,setEditing]=useState<Member|null>(null);const [saving,setSaving]=useState(false);const [message,setMessage]=useState('');
 const [blocked,setBlocked]=useState<{members:Error|null;resource:Error|null}>({members:null,resource:null});
 const [memberPages,setMemberPages]=useState<string[]>([]);const memberCursor=memberPages.at(-1);
 const [projectPages,setProjectPages]=useState<string[]>([]);const projectCursor=projectPages.at(-1);
 const alive=useRef(false);useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
 const key=['access',current.actor_id,current.workspace_id,...current.policy_epoch];
 const projects=useQuery({queryKey:[...key,'projects',projectCursor],queryFn:async()=>{
  const [page,freshCurrent]=await Promise.all([getWorkspaces(projectCursor),getWorkspace(current.workspace_id)]);
  return {...page,current:freshCurrent};
 },retry:false});
 const members=useQuery({queryKey:[...key,'members',memberCursor],queryFn:()=>getMembers(current.workspace_id,memberCursor),enabled:admin&&!blocked.members,retry:false});
 const resource=useQuery({queryKey:[...key,'resource',resourceId],queryFn:()=>getResource(current.workspace_id,resourceId!),enabled:Boolean(resourceId)&&!blocked.resource,retry:false});
 const memberError=admin?(blocked.members??members.error):null;const resourceError=resourceId?(blocked.resource??resource.error):null;
 const listedCurrent=projects.data?.current;
 const policyChanged=Boolean(listedCurrent&&listedCurrent.policy_epoch.join(':')!==current.policy_epoch.join(':'));
 const denied=[projects.error,memberError,resourceError].find(isAuthenticationRejection)
   ||(isWorkspaceForbidden(projects.error)?projects.error:null);
 const scopedDenied=[memberError,resourceError].find(isWorkspaceForbidden);
 useLayoutEffect(()=>{if(denied){cache.removeQueries({queryKey:['access']});onReject(denied)}},[denied,cache,onReject]);
 useLayoutEffect(()=>{if(scopedDenied){
   setBlocked(old=>({members:isWorkspaceForbidden(memberError)?memberError:old.members,resource:isWorkspaceForbidden(resourceError)?resourceError:old.resource}));
   setEditing(null);onRefresh();
 }},[scopedDenied,memberError,resourceError,onRefresh]);
 // Disable the observer before removing its cached query, including queued option effects.
 useEffect(()=>{
  if(blocked.members||blocked.resource)cache.removeQueries({queryKey:['access',current.actor_id,current.workspace_id],predicate:q=>Boolean((blocked.members&&q.queryKey.includes('members'))||(blocked.resource&&q.queryKey.includes('resource')))});
 },[blocked.members,blocked.resource,cache,current.actor_id,current.workspace_id]);
 useLayoutEffect(()=>{if(policyChanged)onRefresh()},[policyChanged,onRefresh]);
 const error=projects.error||memberError||resourceError;
 const switchProject=(id:string)=>{for(const queryKey of [['access'],['discovery']]){void cache.cancelQueries({queryKey});cache.removeQueries({queryKey})}setEditing(null);setMessage('');navigate(`/workspaces/${id}/home`)};
 const save=async()=>{
  if(!editing||!members.data||saving)return;setSaving(true);setMessage('');
  try{const result=await saveMember(current.workspace_id,editing,members.data.policy_epoch);if(!alive.current)return;setEditing(null);onSaved(`权限已保存，审计编号 ${result.audit_id}`);cache.removeQueries({queryKey:['access']});onRefresh()}
  catch(e){if(!alive.current)return;setMessage(e instanceof Error?e.message:'保存失败');
   if(e instanceof AccountRequestError&&e.status===409){setEditing(null);await members.refetch()}
   else if(isAuthenticationRejection(e)){setEditing(null);cache.removeQueries({queryKey:['access']});onReject(e)}
   else if(isWorkspaceForbidden(e)){setEditing(null);setBlocked(old=>({...old,members:e}))}}
  finally{if(alive.current)setSaving(false)}
 };
 if(denied)return null;
 if(policyChanged)return <div className="access-panel"><p role="status">权限已变化，正在读取当前上下文</p></div>;
 if(error)return <div className="access-panel"><p role="alert">{error.message}</p><button className="btn" onClick={()=>{setBlocked({members:null,resource:null});void projects.refetch();if(admin&&!blocked.members)void members.refetch();if(resourceId&&!blocked.resource)void resource.refetch()}}>重新读取权限</button><button className="btn" onClick={()=>{setAdmin(false);navigate(`/workspaces/${current.workspace_id}/home`)}}>返回项目首页</button></div>;
 return <div className="access-panel">
  <div className="access-heading"><h3>项目与账户</h3><label>当前项目 <select aria-label="选择工作区" id="workspace-picker" value={current.workspace_id} onChange={e=>switchProject(e.target.value)} disabled={saving||projects.isFetching||!projects.data}>{projects.data&&!projects.data.workspaces.some(p=>p.workspace_id===current.workspace_id)&&<option value={current.workspace_id}>{current.name}</option>}{projects.data?.workspaces.map(p=><option value={p.workspace_id} key={p.workspace_id}>{p.name}</option>)}</select></label></div>
  <p>{current.display_name} · {current.department} · {current.roles.map(r=>roles[r]??r).join('、')} · 密级上限 L{current.clearance}</p>
  {projects.isPending&&<p role="status">正在读取可访问项目</p>}
  {projects.data?.workspaces.length===0&&<p>本页没有可访问项目</p>}
  {projects.data&&(projectPages.length>0||projects.data.next_cursor)&&<div className="access-actions"><span className="access-page-state" id="project-page-state">{saving?'正在保存，暂不能翻页':projects.isFetching?'正在读取项目，暂不能翻页':`第 ${projectPages.length+1} 页${projectPages.length===0?' · 已是首页':''}${!projects.data.next_cursor?' · 已是末页':''}`}</span><button className="btn" aria-describedby="project-page-state" disabled={saving||projects.isFetching||projectPages.length===0} onClick={()=>setProjectPages(p=>p.slice(0,-1))}>上一页项目</button><button className="btn" aria-describedby="project-page-state" disabled={saving||projects.isFetching||!projects.data.next_cursor} onClick={()=>setProjectPages(p=>[...p,projects.data!.next_cursor!])}>下一页项目</button></div>}
  <button className="btn" disabled={saving||projects.isFetching} onClick={()=>void projects.refetch()}>刷新可访问项目</button>
  {resourceId&&(resource.isFetching?<p role="status">正在读取资源权限</p>:resource.data?<div className="notice"><b>{resource.data.title}</b><p>类型：{resource.data.kind}</p><small>{resource.data.id}</small></div>:null)}
  {current.operations.includes('membership:manage')?<button className="btn" onClick={()=>{setAdmin(!admin);setEditing(null)}}>{admin?'关闭成员管理':'成员与权限'}</button>:<p className="access-muted">当前角色不允许管理成员权限</p>}
  {admin&&<section className="access-admin"><aside>用户、角色与范围</aside><div>
   {!members.isFetching&&members.data?.members.length===0&&<p role="status">当前没有可显示的成员</p>}
   {members.isFetching?<p role="status">正在读取当前成员策略</p>:members.data&&<table><caption>项目成员权限</caption><thead><tr><th>成员</th><th>角色</th><th>密级</th><th>状态</th><th>操作</th></tr></thead><tbody>{members.data.members.map(m=><tr key={m.identity_id}><td>{m.display_name}</td><td>{m.roles.map(r=>roles[r]??r).join('、')}</td><td>L{m.clearance}</td><td>{m.active?'启用':'停用'}</td><td><button className="btn" onClick={()=>{setEditing({...m});setMessage('')}}>编辑权限</button></td></tr>)}</tbody></table>}
   {members.data&&<div className="access-actions"><span className="access-page-state" id="member-page-state">{saving?'正在保存，暂不能翻页':members.isFetching?'正在读取成员，暂不能翻页':`第 ${memberPages.length+1} 页${memberPages.length===0?' · 已是首页':''}${!members.data.next_cursor?' · 已是末页':''}`}</span><button className="btn" aria-describedby="member-page-state" disabled={saving||members.isFetching||memberPages.length===0} onClick={()=>{setEditing(null);setMemberPages(p=>p.slice(0,-1))}}>上一页成员</button><button className="btn" aria-describedby="member-page-state" disabled={saving||members.isFetching||!members.data.next_cursor} onClick={()=>{setEditing(null);setMemberPages(p=>[...p,members.data!.next_cursor!])}}>下一页成员</button></div>}
   {editing&&<form className="access-editor" onSubmit={e=>{e.preventDefault();void save()}} onKeyDown={e=>{if(e.key==='Escape'&&!saving)setEditing(null)}}>
    <h4>编辑 {editing.display_name}</h4>
    <label className="access-toggle"><input type="checkbox" checked={editing.active} disabled={saving} onChange={e=>setEditing({...editing,active:e.target.checked})}/> 允许成员访问</label>
    <fieldset disabled={saving}><legend>操作角色</legend>{Object.entries(roles).map(([key,label])=><label key={key}><input type="checkbox" checked={editing.roles.includes(key)} onChange={e=>setEditing({...editing,roles:e.target.checked?[...editing.roles,key]:editing.roles.filter(r=>r!==key)})}/>{label}</label>)}</fieldset>
    {(['project_scope','customer_scope','product_scope','department_scope'] as const).map((key,i)=><fieldset disabled={saving} key={key}><legend>{['项目范围','客户范围','产品范围','部门范围'][i]}</legend>{editing[key].map((value,index)=><div className="access-scope-row" key={index}><label>第 {index+1} 项<textarea rows={1} maxLength={128} required aria-label={`${['项目范围','客户范围','产品范围','部门范围'][i]}第${index+1}项`} value={value} onChange={e=>setEditing({...editing,[key]:editing[key].map((old,n)=>n===index?e.target.value:old)})}/></label><button className="btn" type="button" onClick={()=>setEditing({...editing,[key]:editing[key].filter((_,n)=>n!==index)})}>移除</button></div>)}<button className="btn" type="button" disabled={editing[key].length>=100} onClick={()=>setEditing({...editing,[key]:[...editing[key],'']})}>添加{['项目范围','客户范围','产品范围','部门范围'][i]}</button></fieldset>)}
    <label>密级上限<select disabled={saving} value={editing.clearance} onChange={e=>setEditing({...editing,clearance:Number(e.target.value)})}>{[0,1,2,3].map(n=><option key={n} value={n}>L{n}</option>)}</select></label>
    <label>所有者范围<select disabled={saving} value={editing.owner_scope} onChange={e=>setEditing({...editing,owner_scope:e.target.value as 'self'|'any'})}><option value="self">仅本人</option><option value="any">范围内任意所有者</option></select></label>
    <fieldset disabled={saving}><legend>允许审批状态</legend>{['draft','in_review','approved','rejected'].map((s,i)=><label key={s}><input type="checkbox" checked={editing.approval_states.includes(s)} onChange={e=>setEditing({...editing,approval_states:e.target.checked?[...editing.approval_states,s]:editing.approval_states.filter(x=>x!==s)})}/>{['草稿','审查中','已批准','已拒绝'][i]}</label>)}</fieldset>
    <label>生效时间（含时区）<input disabled={saving} required value={editing.valid_from} onChange={e=>setEditing({...editing,valid_from:e.target.value})}/></label>
    <label>失效时间（可留空）<input disabled={saving} value={editing.valid_until??''} onChange={e=>setEditing({...editing,valid_until:e.target.value||null})}/></label>
    <div className="access-actions"><button className="btn" type="button" disabled={saving} onClick={()=>setEditing(null)}>取消</button><button className="btn primary" disabled={saving}>{saving?'正在保存':'保存权限'}</button></div>
   </form>}
  </div></section>}
  {message&&<p role="status">{message}</p>}
 </div>
}
