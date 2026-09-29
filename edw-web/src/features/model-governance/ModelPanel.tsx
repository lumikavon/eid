import {useEffect,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import {getModelPolicy,ModelError,type PolicyView} from './model-api';

export default function ModelPanel({current,onReject}:{current:WorkspaceAccess;onReject:(error:unknown)=>void}){
 const [view,setView]=useState<PolicyView|null>(null);const [message,setMessage]=useState('正在核验模型配置');
 const allowed=current.roles.includes('system_admin');
 useEffect(()=>{
  if(!allowed){setView(null);setMessage('仅受权管理员可查看模型配置');return}
  const controller=new AbortController();setView(null);setMessage('正在核验模型配置');
  void getModelPolicy(current,controller.signal).then(value=>{if(!controller.signal.aborted){setView(value);setMessage('')}}).catch(error=>{
   if(controller.signal.aborted)return;setView(null);setMessage(error instanceof Error?error.message:'模型配置不可用');
   if(error instanceof ModelError&&error.status===401)onReject(error);
  });
  return()=>controller.abort();
 },[allowed,current.actor_id,current.workspace_id,current.policy_epoch.join(':'),onReject]);
 return <section aria-label="X-20 受控模型配置" className="notice"><header className="page-header"><h1>受控模型配置 · X-20</h1></header>
  {!allowed?<p role="status">仅受权管理员可查看模型配置；不展示密钥、Prompt 原文或生成内容。</p>:<>
   {message&&<p role="status">{message}</p>}
   {view&&!view.active&&<p role="status">模型已禁用；生成调用不可用。</p>}
   {view?.active&&<div><p>当前版本 {view.active.version} · {view.active.provider==='internal'?'内部路由':'外发策略（生成暂不可用）'} · 模型 {view.active.model_id}</p>
    {view.active.provider==='external'&&<p role="status">外发来源证明尚未接入；此版本不会触发外发调用。</p>}
    <p>Prompt 引用 {view.active.prompt_ref} · SHA-256 {view.active.prompt_sha256}</p>
    <p>允许密级上限 L{view.active.max_classification} · 输出上限 {view.active.max_output_tokens} tokens · 超时 {view.active.timeout_seconds} 秒</p>
    <p>只显示受权版本元数据。密钥和 Prompt 原文仅保留在服务端。</p></div>}
  </>}
 </section>;
}
