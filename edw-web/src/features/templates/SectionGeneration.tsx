import {useEffect,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import type {DocumentData} from './template-api';
import {cancelSection,generationScope,listSectionJobs,observeSection,sectionInputs,startSection,type SectionInputs,type SectionJob,type SectionScope} from './section-generation-api';

export default function SectionGeneration({current,document,onReject}:{current:WorkspaceAccess;document:DocumentData;onReject:(error:unknown)=>void}){
 const [scope,setScope]=useState<SectionScope|null>(null);const [sectionId,setSectionId]=useState('');
 const [inputs,setInputs]=useState<SectionInputs|null>(null);const [job,setJob]=useState<SectionJob|null>(null);
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 useEffect(()=>{let live=true;setScope(null);setSectionId('');setInputs(null);setJob(null);setError('');void generationScope(current,document.id).then(value=>{if(live){setScope(value);setSectionId(value.sections[0]?.id??'')}}).catch(e=>{if(live)setError(String(e))});return()=>{live=false}},[current,document.id,document.version_id,onReject]);
 useEffect(()=>{if(!sectionId)return;let live=true;setInputs(null);setJob(null);void sectionInputs(current,document.id,sectionId).then(async value=>{if(live){setInputs(value);const history=await listSectionJobs(current,document.id);if(live)setJob(history.items.find(x=>x.section_id===sectionId)??null)}}).catch(e=>{if(live){setError(String(e));onReject(e)}});return()=>{live=false}},[current,document.id,sectionId,onReject]);
 useEffect(()=>{if(!job||!['QUEUED','RUNNING','RETRY_WAIT'].includes(job.state))return;let live=true;
  const timer=setTimeout(()=>{void observeSection(current,document.id,job.id).then(value=>{if(live)setJob(value)}).catch(e=>{if(live){setError(String(e));onReject(e)}})},2000);
  return()=>{live=false;clearTimeout(timer)}},[current,document.id,job,onReject]);
 const start=async()=>{if(!inputs?.pack_id||!inputs.pack_job_id||busy)return;setBusy(true);setError('');try{setJob(await startSection(current,document.id,{request_key:crypto.randomUUID(),section_id:inputs.section_id,document_version_id:inputs.document_version_id,document_revision:inputs.document_revision,pack_id:inputs.pack_id,pack_job_id:inputs.pack_job_id}))}catch(e){setError(String(e));onReject(e)}finally{setBusy(false)}};
 return <section className="context-panel" aria-label="章节生成提案"><h3>生成本章节 · 提案</h3><p>需要当前已确认大纲和授权证据；生成不会改动正文。</p>
  {scope&&<label>确认大纲章节<select value={sectionId} onChange={event=>setSectionId(event.target.value)}>{scope.sections.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label>}
  {error&&<p role="alert">{error}</p>}{inputs?.gaps.length?<p role="status">证据状态：{inputs.gaps.join('、')}</p>:null}
  <button type="button" data-ai="生成本章节" disabled={busy||!inputs?.pack_id||document.version_id!==inputs.document_version_id||document.revision!==inputs.document_revision||Boolean(job&&['QUEUED','RUNNING','RETRY_WAIT'].includes(job.state))} onClick={()=>void start()}>生成本章节</button>
  {job&&<div id="aiResponse" role="status"><p>任务 {job.id} · {job.state} / {job.stage} {job.error_code??''}</p>{job.missing.length>0&&<p>待补：{job.missing.join('、')}</p>}{job.proposal&&<>{job.proposal.ast.map((block,index)=><p key={index}>{block.content.text}</p>)}<p>来源 {job.proposal.claims.map(x=>`${x.source_id} · ${x.locator}`).join('、')} · 模型 {job.proposal.provenance.model_id}</p><small>只读提案；需逐项审阅后才能接受。</small></>}{['QUEUED','RUNNING','RETRY_WAIT'].includes(job.state)&&<button type="button" onClick={()=>void cancelSection(current,document.id,job.id).then(setJob).catch(e=>setError(String(e)))}>取消任务</button>}</div>}
 </section>;
}
