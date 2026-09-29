import {useEffect,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import type {DocumentData} from './template-api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import {sectionInputs,type SectionInputs} from './section-generation-api';

type Operation={id:string;label:string;family:string;target:string;input_required:boolean};
type Target={id:string;title:string;hash:string;blocks:{id:string;type:string;hash:string}[]};
type Scope={document_version_id:string;document_revision:number;sections:Target[]};
type Evidence={source_id:string;locator:string;version:string;quote:string};
type Proposal={family:string;state?:string;answer?:string;evidence?:Evidence;patch?:{target_id:string;expected_hash:string;kind:string;after:{content:{text?:string;statement?:string}};evidence:Evidence;state:string}|null;items?:{target_id:string;reason:string;evidence:Evidence;state:string}[];reason?:string};
const original=['generate_section','continue','technical_requirements','check_facts','summarize','polish'];

async function read(current:WorkspaceAccess,documentId:string,suffix:string,body?:object):Promise<Record<string,unknown>>{
 const access=token();if(!access)throw new Error('请重新登录');
 const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${documentId}/copilot/${suffix}`,{
  method:body?'POST':'GET',cache:'no-store',headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json'},
  body:body?JSON.stringify(body):undefined});
 if(!response.ok)throw new Error(`Copilot 操作被拒绝 (${response.status})`);
 const value=await boundedJson(response,32768,'Copilot 响应无效');
 if(token()!==access||!value||typeof value!=='object'||!('data' in value)||!value.data||typeof value.data!=='object')throw new Error('Copilot 响应无效');
 return value.data as Record<string,unknown>;
}

export default function CopilotPanel({current,document}:{current:WorkspaceAccess;document:DocumentData}){
 const [operations,setOperations]=useState<Operation[]>([]);const [scope,setScope]=useState<Scope|null>(null);
 const [section,setSection]=useState('');const [block,setBlock]=useState('');const [selected,setSelected]=useState('generate_section');
 const [prompt,setPrompt]=useState('');const [result,setResult]=useState('');const [proposal,setProposal]=useState<Proposal|null>(null);const [busy,setBusy]=useState(false);const [more,setMore]=useState(false);
 const [evidence,setEvidence]=useState<SectionInputs|null>(null);const [runId,setRunId]=useState('');const [poll,setPoll]=useState(0);
  useEffect(()=>{let live=true;setScope(null);setSection('');setEvidence(null);setRunId('');setProposal(null);setResult('');void Promise.all([read(current,document.id,'catalog'),read(current,document.id,'targets')]).then(([catalog,targets])=>{
  if(!live)return;const items=catalog.items as Operation[];const currentScope=targets as Scope;setOperations(items);setScope(currentScope);setSection(currentScope.sections[0]?.id??'');
 }).catch(e=>{if(live)setResult(String(e))});return()=>{live=false}},[current,document.id,document.version_id]);
 const operation=operations.find(item=>item.id===selected);const target=scope?.sections.find(item=>item.id===section);const chosen=target?.blocks.find(item=>item.id===block);
  useEffect(()=>{let live=true;setEvidence(null);setRunId('');setProposal(null);if(section)void sectionInputs(current,document.id,section).then(value=>{if(live)setEvidence(value)}).catch(e=>{if(live)setResult(String(e))});return()=>{live=false}},[current,document.id,document.version_id,section]);
 useEffect(()=>{if(!runId)return;let live=true;const timer=setTimeout(()=>{void read(current,document.id,`runs/${runId}`).then(value=>{
   if(!live)return;const response=value.response as Proposal|undefined;
   setProposal(response??null);setResult(`${String(value.state)} · ${String(value.stage)}${response?.reason?` · ${response.reason}`:''}`);
  if(!['SUCCEEDED','BLOCKED','FAILED'].includes(String(value.state)))setPoll(count=>count+1);
  else setRunId('');
 }).catch(e=>{if(live){setResult(String(e));setRunId('')}})},2000);return()=>{live=false;clearTimeout(timer)}},[current,document.id,runId,poll]);
 const submit=async()=>{if(!operation||!scope||!target||!evidence?.pack_id||!evidence.pack_job_id||busy)return;setBusy(true);setResult('');setProposal(null);try{
   const value=await read(current,document.id,'execute',{operation:selected,document_version_id:scope.document_version_id,
    document_revision:scope.document_revision,section_id:target.id,block_id:operation.target==='selection'?chosen?.id:null,
    target_hash:operation.target==='selection'?chosen?.hash:target.hash,prompt,request_key:crypto.randomUUID(),
    pack_id:evidence.pack_id,pack_job_id:evidence.pack_job_id});
   setResult(`${String(value.state)} · ${String(value.family)}${value.reason?` · ${String(value.reason)}`:''}${value.id?` · 任务 ${String(value.id)}`:''}（未改动正文）`);
   if(value.id)setRunId(String(value.id));
 }catch(e){setResult(String(e))}finally{setBusy(false)}};
 return <section className="context-panel" data-aipanel="copilot" aria-label="AI Copilot"><h3>AI Copilot</h3>
  <div className="ai-tabs"><button data-aitab="copilot" aria-current="page">AI Copilot</button><button data-aitab="evidence" disabled>知识引用</button><button data-aitab="todo" disabled>待确认项</button></div>
  <label>目标章节<select value={section} onChange={e=>{setSection(e.target.value);setBlock('');setProposal(null)}}>{scope?.sections.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
  {operation?.target==='selection'&&<label>目标文本块<select value={block} onChange={e=>{setBlock(e.target.value);setProposal(null)}}><option value="">请选择</option>{target?.blocks.filter(item=>['paragraph','heading','requirement'].includes(item.type)).map(item=><option key={item.id} value={item.id}>{item.type} · {item.id.slice(0,8)}</option>)}</select></label>}
  <div>{original.map(id=>{const item=operations.find(value=>value.id===id);return <button key={id} type="button" data-ai={item?.label} disabled={!item||busy} aria-pressed={selected===id} onClick={()=>{setSelected(id);setProposal(null);setResult('')}}>{item?.label??id}</button>})}</div>
  <button type="button" onClick={()=>setMore(!more)} aria-expanded={more}>更多</button>{more&&<select aria-label="更多 Copilot 操作" value={original.includes(selected)?'':selected} onChange={e=>{setSelected(e.target.value);setProposal(null);setResult('')}}><option value="">选择操作</option>{operations.filter(item=>!original.includes(item.id)).map(item=><option key={item.id} value={item.id}>{item.label} · {item.family}</option>)}</select>}
  <p>操作：{operation?.label??'未选择'} · 效果：{operation?.family??'—'} · 目标：{target?.title??'—'}{operation?.target==='selection'?' / 文本块':''}</p>
  <textarea id="aiPrompt" aria-label="Copilot 输入" value={prompt} onChange={e=>{setPrompt(e.target.value);setProposal(null)}} maxLength={4000}/>
  <button id="sendAi" type="button" disabled={busy||!operation||!target||!evidence?.pack_id||operation.target==='selection'&&!chosen||scope?.document_version_id!==document.version_id} onClick={()=>void submit()}>发送</button>
  <div id="aiResponse" role="status">{result}</div>
  {proposal&&<div aria-label="Copilot 提案预览">
   <p>{proposal.family} · {proposal.state??proposal.patch?.state??'待人工审核'} · 不自动修改正文</p>
   {proposal.answer&&<p>{proposal.answer}</p>}
   {proposal.patch&&<div><p>目标 {proposal.patch.target_id.slice(0,8)} · {proposal.patch.kind} · 仅供 Diff 审阅</p><pre>{proposal.patch.after.content.text??proposal.patch.after.content.statement}</pre><p>依据：{proposal.patch.evidence.quote}</p></div>}
   {proposal.items?.map((item,index)=><div key={`${item.target_id}-${index}`}><p>{item.reason}</p><p>依据：{item.evidence.quote}</p></div>)}
   {proposal.evidence&&<p>依据：{proposal.evidence.quote}</p>}
  </div>}
 </section>;
}
