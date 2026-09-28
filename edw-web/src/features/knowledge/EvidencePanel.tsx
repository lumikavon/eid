import {useEffect,useRef,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import {getOutline,type OutlineData} from '../templates/outline-api';
import {evidenceOrdinal,getEvidenceJob,requestEvidence,similarDocuments,type EvidenceJob,type SimilarDoc} from './evidence-api';

const gapLabels:Record<string,string>={SOURCE_SCAN_LIMIT:'来源扫描预算已耗尽',ENTERPRISE_UNAVAILABLE:'企业链路不可用',SEMANTIC_UNAVAILABLE:'语义链路不可用',ITEM_BUDGET_EXHAUSTED:'片段预算已耗尽',SOURCE_REVOKED_OR_CHANGED:'来源撤权或版本变动',SOURCE_EXPIRED:'来源已过期',NO_CURRENT_SUPPORT:'无当前可核验支撑',SOURCE_CONFLICT_REQUIRES_REVIEW:'来源冲突待复核',KEY_FACT_SUPPORT_NOT_VERIFIED:'关键事实尚未逐条核证'};
export default function EvidencePanel({current,documentId,onReject,onRefresh,onSelectionChange,onBind}:{current:WorkspaceAccess;documentId:string;onReject:(error:unknown)=>void;onRefresh:()=>void;onSelectionChange:()=>void;onBind?:(packId:string,index:number,excerpt:string,relation:'supports'|'conflicts'|'contextual')=>void}){
 const [outline,setOutline]=useState<OutlineData|null>(null);const [section,setSection]=useState('');const [job,setJob]=useState<EvidenceJob|null>(null);
 const [similar,setSimilar]=useState<SimilarDoc[]>([]);const [similarLimited,setSimilarLimited]=useState(false);const [similarError,setSimilarError]=useState(false);const [error,setError]=useState('');const [loading,setLoading]=useState(false);
 const request=useRef<AbortController|null>(null);const serial=useRef(0);
 const clear=()=>{request.current?.abort();serial.current++;setJob(null);setSimilar([]);setSimilarLimited(false);setSimilarError(false);setError('');setLoading(false)};
 const fail=(problem:unknown)=>{try{if(jobKey)sessionStorage.removeItem(jobKey)}catch{/* storage disabled */}setJob(null);setSimilar([]);setSimilarLimited(false);setSimilarError(false);setError(problem instanceof Error?problem.message:'证据访问失败');onRefresh();if(problem instanceof Error&&problem.message.includes('登录'))onReject(problem)};
 useEffect(()=>{clear();setOutline(null);setSection('');const controller=new AbortController();request.current=controller;const generation=serial.current;
  void getOutline(current,documentId,controller.signal).then(next=>{if(!controller.signal.aborted&&generation===serial.current)setOutline(next)}).catch(problem=>{if(!controller.signal.aborted&&generation===serial.current)fail(problem)});
  return()=>{controller.abort();serial.current++};
 },[current.actor_id,current.workspace_id,documentId,...current.policy_epoch]);
 const selected=outline?.snapshot?.sections.find(s=>s.id===section);
 const jobKey=selected&&outline?['evidence-job',current.workspace_id,current.actor_id,documentId,
  ...current.policy_epoch,selected.id,outline.version_id,outline.document_version_id,outline.document_revision].join(':'):'';
 const select=(id:string)=>{clear();onSelectionChange();setSection(id)};
 useEffect(()=>{if(!jobKey||job)return;
  let id='';try{id=sessionStorage.getItem(jobKey)??''}catch{return}
  if(!/^[0-9a-f-]{36}$/i.test(id))return;
  const controller=new AbortController();request.current=controller;const generation=serial.current;
  void getEvidenceJob(current,documentId,id,controller.signal).then(next=>{if(!controller.signal.aborted&&generation===serial.current)setJob(next)})
   .catch(()=>{try{sessionStorage.removeItem(jobKey)}catch{/* storage disabled */}});
  return()=>controller.abort();
 },[jobKey,documentId]);
 const build=()=>{if(!outline||outline.state!=='OUTLINE_READY'||!selected||!outline.version_id||!outline.context_version_id)return;
  clear();let requestKey:string=crypto.randomUUID();try{
   if(job?.state==='FAILED'||job?.state==='BLOCKED')sessionStorage.removeItem(`${jobKey}:request`);
   requestKey=sessionStorage.getItem(`${jobKey}:request`)??requestKey;
   sessionStorage.setItem(`${jobKey}:request`,requestKey);
   sessionStorage.removeItem(jobKey);
  }catch{/* storage disabled */}const controller=new AbortController();request.current=controller;const generation=serial.current;setLoading(true);
  const selection={section_id:selected.id,outline_version_id:outline.version_id,context_version_id:outline.context_version_id,document_version_id:outline.document_version_id};
  void requestEvidence(current,documentId,{...selection,document_revision:outline.document_revision,request_key:requestKey},controller.signal).then(next=>{if(!controller.signal.aborted&&generation===serial.current){setJob(next);try{sessionStorage.setItem(jobKey,next.id)}catch{/* storage disabled */}}}).catch(problem=>{if(!controller.signal.aborted&&generation===serial.current)fail(problem)}).finally(()=>{if(generation===serial.current)setLoading(false)});
  void similarDocuments(current,documentId,selection,controller.signal).then(docs=>{if(!controller.signal.aborted&&generation===serial.current){setSimilar(docs.items);setSimilarLimited(docs.limited);setSimilarError(false)}}).catch(()=>{if(!controller.signal.aborted&&generation===serial.current)setSimilarError(true)});
 };
 useEffect(()=>{if(!job||!['QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED'].includes(job.state))return;
  const generation=serial.current;const timer=setTimeout(()=>{const controller=new AbortController();request.current=controller;
   void getEvidenceJob(current,documentId,job.id,controller.signal).then(next=>{if(!controller.signal.aborted&&generation===serial.current)setJob(next)}).catch(problem=>{if(!controller.signal.aborted&&generation===serial.current)fail(problem)});
  },job.state==='SUCCEEDED'?30000:1500);return()=>clearTimeout(timer);
 },[current,documentId,job]);
 useEffect(()=>{const refresh=()=>{if(document.visibilityState==='hidden')return;clear();setOutline(null);setSection('');const controller=new AbortController();request.current=controller;const generation=serial.current;
   void getOutline(current,documentId,controller.signal).then(next=>{if(!controller.signal.aborted&&generation===serial.current)setOutline(next)}).catch(problem=>{if(!controller.signal.aborted&&generation===serial.current)fail(problem)});
  };window.addEventListener('focus',refresh);return()=>window.removeEventListener('focus',refresh)},[current,documentId]);
 return <section aria-label="章节 Evidence Pack"><h3>章节 Evidence Pack</h3><p>固定确认大纲的精确章节；片段仅为候选，不等于事实核证或发布批准。</p>
  {outline?.state==='OUTLINE_PENDING'&&<p role="status">OUTLINE_READY 尚未满足：{outline.reasons.map(r=>r.code).join('、')}</p>}
  {outline?.state==='OUTLINE_READY'&&<><label>已确认章节<select aria-label="已确认章节" value={section} onChange={e=>select(e.target.value)}><option value="">选择章节</option>{outline.snapshot?.sections.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}</select></label><button className="btn primary" disabled={!selected||loading} onClick={build}>构建当前章节证据</button></>}
  {loading&&<p role="status">正在提交证据任务…</p>}{error&&<p role="alert">{error}</p>}
  {job&&<div role="status">任务 {job.state} · 阶段 {job.stage} · 尝试 {job.attempt}{job.error_code?` · ${job.error_code}`:''}</div>}
  {job?.pack&&<><p role="status">支撑不足 · 未逐条核证关键事实 · 查询 {job.pack.queries.length} 条 · 策略 {job.pack.policy_hash} · 旧快照散列 {job.pack.snapshot_hash} · 当前视图散列 {job.pack.view_hash} · {job.pack.retrieval_version}</p>
   <ul>{job.pack.gaps.map(g=><li key={g}>{gapLabels[g]??g}</li>)}</ul>
   <details><summary>查询与链路预算</summary><ul>{job.pack.queries.map((q,i)=><li key={i}>{q}</li>)}</ul><p>{JSON.stringify(job.pack.chains)}</p></details>
   {job.pack.items.map((hit,i)=><article key={`${hit.chain}:${hit.source_id}:${hit.version}:${hit.chunk_hash}:${i}`} className="knowledge-viewer"><b>{hit.chain==='enterprise'?'企业知识':'受控附件'}</b><p>{hit.excerpt}</p><small>来源 {hit.source_id} · 版本 {hit.version} · {hit.locator}{hit.page?` · 页 ${hit.page}`:''} · chunk {hit.chunk_hash} · 查询 {hit.queries.join(' / ')} · 语义 {hit.semantic_score??'不可用'} · 重排 {hit.rerank_score??'不可用'} · 权威 {hit.governance?.map(g=>g.authority).join('/')??'未登记'}</small>{onBind&&<div><button onClick={()=>onBind(job.pack!.id,evidenceOrdinal(hit),hit.excerpt,'supports')}>绑定支持（核查原文）</button><button onClick={()=>onBind(job.pack!.id,evidenceOrdinal(hit),hit.excerpt,'conflicts')}>绑定冲突</button><button onClick={()=>onBind(job.pack!.id,evidenceOrdinal(hit),hit.excerpt,'contextual')}>绑定背景</button></div>}</article>)}
   <p>冲突：{job.pack.conflict_ids.length?job.pack.conflict_ids.join('、'):'无已登记冲突'}；不同版本：{job.pack.version_conflicts.length?job.pack.version_conflicts.join('、'):'无'}</p></>}
  {similarError&&<p role="status">相似文档推荐暂不可用；证据任务仍可继续查询。</p>}
  {(similar.length>0||similarLimited)&&<section aria-label="同项目可定位文档"><h4>同项目受权文档（不代表内容相似或事实支持）</h4>{similar.map(doc=><p key={doc.document_id}>{doc.document_id} · 版本 {doc.version} · {doc.locator}</p>)}{similarLimited&&<p>推荐扫描预算已耗尽，结果不完整。</p>}</section>}
 </section>;
}
