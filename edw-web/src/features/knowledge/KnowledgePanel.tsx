import {useEffect,useRef,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import {KnowledgeError,searchKnowledge,inspectConflict,decideConflict,registerAssertion,type ConflictView,type Category,type Hit,type SearchInput,type SearchResult} from './knowledge-api';
import './knowledge.css';
import EvidencePanel from './EvidencePanel';
import ClaimPanel from './ClaimPanel';
import type {Bookmark} from './claim-api';

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const labels:Record<Category,string>={all:'全部',attachment:'附件',enterprise:'企业',golden:'Golden'};
export default function KnowledgePanel({current,documentId,onReject,onRefresh,compact=false,bookmark,onCite}:{current:WorkspaceAccess;documentId?:string;onReject:(error:unknown)=>void;onRefresh:()=>void;compact?:boolean;bookmark?:Bookmark|null;onCite?:(claimId:string,linkId:string,quote:string)=>Promise<void>}){
 const [contextId,setContextId]=useState(documentId??'');const [query,setQuery]=useState('');const [category,setCategory]=useState<Category>('all');
 const [classification,setClassification]=useState('');const [version,setVersion]=useState('');const [contextVersion,setContextVersion]=useState('');
 const [result,setResult]=useState<SearchResult|null>(null);const [selected,setSelected]=useState<Hit|null>(null);
 const [conflict,setConflict]=useState<ConflictView|null>(null);const [reason,setReason]=useState('');const [decision,setDecision]=useState<'accepted_left'|'accepted_right'|'unresolved'>('unresolved');
 const [topic,setTopic]=useState('');const [value,setValue]=useState('');const [statement,setStatement]=useState('');const [authority,setAuthority]=useState(7);const [expiry,setExpiry]=useState('');
 const manager=current.operations.includes('knowledge:manage');
 const [claimGeneration,setClaimGeneration]=useState(0);
 const binder=useRef<((packId:string,index:number,excerpt:string,relation:'supports'|'conflicts'|'contextual')=>void)|null>(null);
 const [error,setError]=useState('');const [loading,setLoading]=useState(false);const request=useRef<AbortController|null>(null);const serial=useRef(0);const last=useRef<SearchInput|null>(null);
 const reset=()=>{request.current?.abort();serial.current++;setResult(null);setSelected(null);setConflict(null);setError('');setLoading(false)};
 useEffect(()=>()=>{request.current?.abort();serial.current++},[]);
 useEffect(()=>{reset();setContextId(documentId??'')},[documentId,current.actor_id,current.workspace_id,...current.policy_epoch]);
 const run=async(input:SearchInput,select?:Hit)=>{
  reset();const controller=new AbortController();request.current=controller;const generation=serial.current;setLoading(true);
  try{
   const next=await searchKnowledge(current,input,controller.signal);
   if(controller.signal.aborted||generation!==serial.current)return;
   last.current=input;setResult(next);
   if(select)setSelected(next.items.find(item=>item.chain===select.chain&&item.source_id===select.source_id&&item.version===select.version&&item.chunk_hash===select.chunk_hash)??null);
  }catch(problem){if(controller.signal.aborted||generation!==serial.current)return;
   setResult(null);setSelected(null);setError(problem instanceof Error?problem.message:'检索失败');
   if(problem instanceof KnowledgeError&&problem.failure==='authentication')onReject(problem);
   else if(problem instanceof KnowledgeError&&problem.failure==='forbidden')onRefresh();
  }finally{if(generation===serial.current)setLoading(false)}
 };
 const submit=()=>{if(!uuid.test(contextId)||query.trim().length<2||version&&!/^[0-9a-f]{64}$/.test(version)||contextVersion&&!uuid.test(contextVersion)){reset();setError('请输入有效的范围、版本和至少两个字符的查询');return}
  void run({query:query.trim(),context_document_id:contextId,category,limit:10,...(version?{source_sha256:version}:{}),...(contextVersion?{context_version_id:contextVersion}:{}),...(classification?{classification:Number(classification)}:{})});};
 const inspect=(item:Hit)=>{if(last.current)void run(last.current,item)};
 const guarded=async(action:(signal:AbortSignal)=>Promise<void>)=>{
  reset();const controller=new AbortController();request.current=controller;const generation=serial.current;setLoading(true);
  try{await action(controller.signal)}catch(problem){if(controller.signal.aborted||generation!==serial.current)return;
   setError(problem instanceof Error?problem.message:'来源已失效');if(problem instanceof KnowledgeError&&problem.failure==='authentication')onReject(problem);else if(problem instanceof KnowledgeError&&problem.failure==='forbidden')onRefresh();
  }finally{if(generation===serial.current)setLoading(false)}
 };
 const openConflict=(id:string)=>{if(!uuid.test(contextId))return;void guarded(async signal=>{const next=await inspectConflict(current,id,contextId,signal);if(!signal.aborted)setConflict(next)})};
 const submitDecision=()=>{if(!conflict||!manager||reason.trim().length<3)return;
  const previous=conflict;const visible=previous.sides;if(visible.some(s=>s.state!=='current'))return;
  void guarded(async signal=>{const next=await decideConflict(current,previous.id,{context_document_id:contextId,expected_revision:previous.revision,left_id:visible[0].state==='current'?visible[0].id:'',right_id:visible[1].state==='current'?visible[1].id:'',status:decision,reason:reason.trim()},signal);if(!signal.aborted){setConflict(next);setReason('')}})};
 const addAssertion=()=>{if(!selected||!manager||!uuid.test(contextId)||!topic.trim()||!value.trim()||!statement.trim()||!selected.project_id)return;
  const hit=selected;void guarded(async signal=>{await registerAssertion(current,{context_document_id:contextId,chain:hit.chain,source_id:hit.source_id,...(hit.chain==='attachment'?{document_id:hit.document_id,page:hit.page,ordinal:hit.ordinal}:{}),version:hit.version,chunk_hash:hit.chunk_hash,locator:hit.locator,classification:hit.classification,project_id:hit.project_id,product_id:hit.product_id??null,customer_id:hit.customer_id??null,authority,effective_from:new Date().toISOString(),effective_until:expiry?new Date(expiry).toISOString():hit.valid_until??null,topic:topic.trim(),statement:statement.trim(),value:value.trim()},signal);if(!signal.aborted)setError('来源已登记；重新检索以核查权威与冲突')})};
 // Clear controlled passages BEFORE background permission rechecks or a tab regains focus.
 useEffect(()=>{const recheck=()=>{if(!last.current||document.visibilityState==='hidden')return;const input=last.current;reset();void run(input)};
  const focus=()=>recheck();window.addEventListener('focus',focus);const timer=setInterval(recheck,30000);
  return()=>{window.removeEventListener('focus',focus);clearInterval(timer)}},[current]);
 return <section className={`knowledge-panel${compact?' compact':''}`} aria-label="授权知识检索" data-testid="knowledge-panel">
  {!compact&&<header className="page-header"><h1>知识库 · 授权检索</h1></header>}
  {documentId&&<EvidencePanel key={`${documentId}:${current.actor_id}:${current.policy_epoch.join(':')}`} current={current} documentId={documentId} onReject={onReject} onRefresh={onRefresh} onSelectionChange={()=>{reset();setClaimGeneration(n=>n+1)}} onBind={(packId,index,excerpt,relation)=>binder.current?.(packId,index,excerpt,relation)}/>}
  {documentId&&<ClaimPanel key={`${documentId}:${claimGeneration}`} current={current} documentId={documentId} bookmark={bookmark} onCite={onCite} onBindReady={handler=>{binder.current=handler}}/>}
  <p>仅查询当前项目内有权的真实来源；发现页标题和模型常识不是证据。检索可能不完整。</p>
  <div className="knowledge-controls"><label>上下文文档 ID<input aria-label="上下文文档 ID" value={contextId} readOnly={!!documentId} onChange={e=>{reset();setContextId(e.target.value)}} placeholder="当前项目文档 UUID"/></label>
   <label>关键词或精确标识符<input aria-label="知识查询" value={query} maxLength={128} onChange={e=>{reset();setQuery(e.target.value)}} onKeyDown={e=>{if(e.key==='Enter')submit()}}/></label>
   <label>来源版本 SHA-256<input aria-label="来源版本筛选" value={version} maxLength={64} onChange={e=>{reset();setVersion(e.target.value)}} placeholder="可选"/></label>
   <label>上下文版本 ID<input aria-label="上下文版本筛选" value={contextVersion} onChange={e=>{reset();setContextVersion(e.target.value)}} placeholder="可选"/></label>
   <label>最高密级<select aria-label="密级筛选" value={classification} onChange={e=>{reset();setClassification(e.target.value)}}><option value="">当前许可</option>{[0,1,2,3].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
   <div className="seg-tabs" role="tablist" aria-label="来源类别">{(Object.keys(labels) as Category[]).map(name=><button key={name} role="tab" aria-selected={category===name} className={category===name?'active':''} onClick={()=>{reset();setCategory(name)}}>{labels[name]}</button>)}</div>
   <button className="btn primary" disabled={loading} onClick={submit}>检索当前授权来源</button></div>
  {loading&&<p role="status">正在核验来源权限与版本…</p>}{error&&<p role="alert">{error}</p>}
  {result&&<><p role="status">非全量搜索 · {result.scope} · {result.retrieval_version}{result.limited?' · 范围已截断':''}</p>
   <div className="knowledge-chains" aria-label="检索链路">{Object.entries(result.chains).map(([name,state])=><span key={name}>{name}：{state==='available'?'可用':'不可用'}</span>)}</div>
   {!result.items.length&&<p role="status">当前范围没有可核验的命中，或相应链路不可用；不代表不存在来源。</p>}
   <div className="knowledge-results">{result.items.map((item,index)=><article key={`${item.chain}:${item.source_id}:${item.chunk_hash}:${index}`}><b>{item.category==='golden'?'Golden':item.chain==='enterprise'?'企业知识':'受控附件'}</b><p>{item.excerpt}</p><small>版本 {item.version} · {item.locator} {item.page?`· 页 ${item.page}`:''} · 密级 {item.classification} · {item.keyword_version}{item.embedding_version?` · ${item.embedding_version}`:''} · {item.governance?.length?item.governance.map(g=>`${g.authority_label} (${g.authority}/9) · 有效至 ${g.effective_until??'未设置'}`).join('；'):'权威/时效待登记'}</small><button className="btn" onClick={()=>inspect(item)}>重新核验并查看片段</button>{item.governance?.map(g=>g.conflict_id&&<button className="btn" key={g.assertion_id} onClick={()=>openConflict(g.conflict_id!)}>查看冲突与历史</button>)}</article>)}</div></>}
  {selected&&result?.items.some(item=>item.source_id===selected.source_id&&item.version===selected.version&&item.chunk_hash===selected.chunk_hash)&&<aside className="knowledge-viewer" aria-label="核验后的来源片段"><h3>来源查看器 · 当前核验</h3><p>{selected.excerpt}</p><small>{selected.chain} · {selected.source_id} · 版本 {selected.version} · {selected.locator} · chunk {selected.chunk_hash} · {selected.policy}</small><button className="btn" onClick={()=>setSelected(null)}>关闭</button>{manager&&<div className="knowledge-controls" aria-label="登记来源断言"><label>权威等级<select value={authority} onChange={e=>setAuthority(Number(e.target.value))}>{['法律','公司','项目','产品','批准历史','部门','内部','允许外部'].map((label,i)=><option value={i+1} key={label}>{i+1} · {label}</option>)}</select></label><label>主题<input value={topic} maxLength={256} onChange={e=>setTopic(e.target.value)}/></label><label>断言原文<input value={statement} maxLength={4000} onChange={e=>setStatement(e.target.value)}/></label><label>值<input value={value} maxLength={256} onChange={e=>setValue(e.target.value)}/></label><label>有效至<input type="datetime-local" value={expiry} onChange={e=>setExpiry(e.target.value)}/></label><button className="btn" onClick={addAssertion}>登记当前来源版本</button></div>}</aside>}
  {conflict&&<aside className="knowledge-viewer" aria-label="来源冲突与历史"><h3>X-11 · 来源冲突</h3><p>裁定状态：{conflict.status} · 版本 {conflict.revision}（人工裁定不修改原文）</p>{conflict.sides.map((s,i)=><article key={i}><h4>{i===0?'来源 A':'来源 B'}</h4>{s.state==='forbidden'?<p>禁止访问或来源失效</p>:<><p>{s.statement}</p><small>{s.authority_label} · {s.value} {s.unit} · {s.conditions} · {s.source_id} · {s.version} · {s.locator} · 有效至 {s.effective_until??'未设置'}</small></>}</article>)}{conflict.history.map(h=><p key={h.revision}>版本 {h.revision} · {h.status} · {h.reason} · {h.actor_id} · {h.decided_at}</p>)}{manager&&conflict.sides.every(s=>s.state==='current')&&<div className="knowledge-controls"><label>裁定<select value={decision} onChange={e=>setDecision(e.target.value as typeof decision)}><option value="unresolved">未解决</option><option value="accepted_left">采用 A</option><option value="accepted_right">采用 B</option></select></label><label>裁定理由<input value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)}/></label><button className="btn" disabled={loading||reason.trim().length<3} onClick={submitDecision}>提交版本化裁定</button></div>}<button className="btn" onClick={reset}>关闭并清除</button></aside>}
 </section>;
}
