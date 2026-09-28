import {useEffect,useRef,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import {bindClaim,declareClaim,extractClaims,getClaims,getTrace,type Bookmark,type Claim,type Trace} from './claim-api';

export default function ClaimPanel({current,documentId,bookmark,onCite,onBindReady}:{current:WorkspaceAccess;documentId:string;bookmark?:Bookmark|null;onCite?:(claimId:string,linkId:string,quote:string)=>Promise<void>;onBindReady?:(handler:((packId:string,index:number,excerpt:string,relation:'supports'|'conflicts'|'contextual')=>void)|null)=>void}){
 const [claims,setClaims]=useState<Claim[]>([]);const [selected,setSelected]=useState('');const [trace,setTrace]=useState<Trace|null>(null);
 const [version,setVersion]=useState('');const [revision,setRevision]=useState(0);const [message,setMessage]=useState('');
 const [kind,setKind]=useState('unknown');const [value,setValue]=useState('');const [conditions,setConditions]=useState('');const [unit,setUnit]=useState('');const request=useRef<AbortController|null>(null);const generation=useRef(0);
 const clear=()=>{request.current?.abort();generation.current++;setTrace(null);setClaims([]);setSelected('');setMessage('')};
 const load=()=>{clear();const controller=new AbortController();request.current=controller;const seq=generation.current;
  void getClaims(current,documentId,controller.signal).then(data=>{if(seq===generation.current&&!controller.signal.aborted){setVersion(data.version_id);setRevision(data.revision);setClaims(data.items)}}).catch(()=>{if(seq===generation.current){clear();setMessage('Claim 访问失效；请重新核对')}});
 };
 useEffect(()=>{load();const focus=()=>{if(document.visibilityState!=='hidden')load()};window.addEventListener('focus',focus);const timer=setInterval(focus,30000);return()=>{window.removeEventListener('focus',focus);clearInterval(timer);request.current?.abort();generation.current++}},[current.actor_id,current.workspace_id,documentId,...current.policy_epoch]);
 useEffect(()=>{request.current?.abort();generation.current++;setTrace(null);
  if(!selected)return;const controller=new AbortController();request.current=controller;const seq=generation.current;
  void getTrace(current,documentId,selected,controller.signal).then(data=>{if(seq===generation.current&&!controller.signal.aborted)setTrace(data)}).catch(()=>{if(seq===generation.current){setTrace(null);setMessage('来源失权或版本变化；受控摘录已清空')}});
  return()=>{controller.abort();generation.current++};
 },[selected,current.actor_id,current.workspace_id,documentId,...current.policy_epoch]);
 const bind=(packId:string,index:number,excerpt:string,relation:'supports'|'conflicts'|'contextual')=>{
  const claim=claims.find(item=>item.id===selected);if(!claim||!revision||claim.document_version_id!==version){setMessage('请先选择当前版本 Claim');return}
  request.current?.abort();generation.current++;setTrace(null);const controller=new AbortController();request.current=controller;
  void bindClaim(current,documentId,selected,{base_version_id:version,revision,pack_id:packId,item_ordinal:index,relation,quoted_text:excerpt},controller.signal)
   .then(()=>{if(!controller.signal.aborted){setMessage('已记录关系，仍须人工核查；重新选择 Claim 查看当前追溯');setSelected('');load()}})
   .catch(()=>{setTrace(null);setMessage('绑定未确认或来源失权；请重新选择')});
 };
 useEffect(()=>{onBindReady?.(bind);return()=>onBindReady?.(null)});
 const declare=()=>{if(!bookmark||!kind.trim()||!value.trim()||version!==bookmark.base_version_id){setMessage('先固定当前版本选区并填写类型和值');return}
  const controller=new AbortController();request.current?.abort();request.current=controller;setTrace(null);
  void declareClaim(current,documentId,{...bookmark,claim_type:kind.trim(),conditions:conditions.trim(),value:value.trim(),unit:unit.trim(),critical:true},controller.signal).then(()=>load()).catch(()=>{setMessage('声明未保存，选区或版本可能已变化')});
 };
 const scan=()=>{const controller=new AbortController();request.current?.abort();request.current=controller;setTrace(null);
  void extractClaims(current,documentId,controller.signal).then(()=>load()).catch(()=>{setMessage('无法扫描当前版本 Claim')});
 };
 const choose=(id:string)=>{request.current?.abort();generation.current++;setTrace(null);setMessage('');setSelected(id)};
 return <section aria-label="可核查 Claim 与追溯"><h3>可核查 Claim · 当前版本</h3><p>确定性候选与旧判定不是事实证明；关键缺口与冲突待确认。</p>
  {bookmark&&<p role="status">已固定选区：{bookmark.selected_text}（版本 {bookmark.revision}）</p>}
  <button onClick={scan}>扫描本版确定性候选</button>{bookmark&&<div className="knowledge-controls"><label>声明类型（可保留未知类型）<input value={kind} maxLength={80} onChange={event=>setKind(event.target.value)}/></label><label>条件<input value={conditions} maxLength={512} onChange={event=>setConditions(event.target.value)}/></label><label>值<input value={value} maxLength={256} onChange={event=>setValue(event.target.value)}/></label><label>单位<input value={unit} maxLength={64} onChange={event=>setUnit(event.target.value)}/></label><button onClick={declare}>声明所选 Claim · 待确认</button></div>}
  <label>选择 Claim / 问题<select aria-label="选择 Claim" value={selected} onChange={event=>choose(event.target.value)}><option value="">清空追溯</option>{claims.map(item=><option key={item.id} value={item.id}>{item.claim_type} · {item.statement} · {item.status}{item.needs_review?' · 待复核':''}</option>)}</select></label>
  {message&&<p role="alert">{message}</p>}{selected&&<div aria-label="当前 Claim 追溯">{trace?.state==='unavailable'&&<p>来源当前不可用；旧快照不授权。</p>}{trace?.links.map(link=><article key={link.id} className="knowledge-viewer"><p>{link.quoted_text}</p><small>{link.relation} · {link.source_id} · 版本 {link.version} · {link.locator} · chunk {link.chunk_hash}</small>{bookmark&&onCite&&link.relation==='supports'&&<button disabled={claims.find(x=>x.id===selected)?.block_id!==bookmark.block_id} onClick={()=>{request.current?.abort();generation.current++;setTrace(null);void onCite(selected,link.id,link.quoted_text).then(()=>load()).catch(()=>{setMessage('引用未确认；请核对版本并重新选择');load()})}}>确认插入当前选区</button>}</article>)}</div>}
 </section>;
}
