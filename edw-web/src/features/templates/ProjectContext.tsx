import {useEffect,useRef,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import type {DocumentData} from './template-api';
import {TemplateError} from './template-api';
import AttachmentInspector from './AttachmentInspector';
import {blankContext,confirmContext,getContext,getContextVersion,getContextVersions,saveContext,type ContextData,type ContextSnapshot} from './context-api';

const stable=(value:unknown):string=>JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a<b?-1:a>b?1:0)):item);
const reasonLabels:Record<string,string>={CONTEXT_MISSING:'尚无上下文版本',INTENT_REQUIRED:'请填写项目意图',CURRENT_EDIT_DENIED:'当前无文档编辑权限',DOCUMENT_CHANGED:'文档正文版本已变化',DOCUMENT_NOT_DRAFT:'文档不再是草稿',FACTS_REQUIRED:'请填写事实或显式声明无项目事实',FACT_UNCONFIRMED:'事实尚未确认',REQUIRED_MISSING:'必需缺项尚未解决',HUMAN_CONFIRMATION_REQUIRED:'需要人工确认精确上下文版本',CONFIRMATION_NOT_READY:'该版本确认时未满足条件'};
const normalize=(data:ContextSnapshot):ContextSnapshot=>({
 ...data,intent:data.intent.trim(),facts:data.facts.map(f=>({...f,key:f.key.trim(),value:f.value.trim(),unit:f.unit?.trim()||null,source:{...f.source,locator:f.source.locator.trim(),resource_id:f.source.resource_id?.trim()||null}})),
 glossary:data.glossary.map(g=>({term:g.term.trim(),definition:g.definition.trim()})),
 constraints:data.constraints.map(c=>({...c,text:c.text.trim(),source:{locator:c.source.locator.trim(),resource_id:c.source.resource_id?.trim()||null}})),
 missing:data.missing.map(m=>({...m,key:m.key.trim()})),
});
export default function ProjectContext({current,document,documentDirty,onPending,onContextObserved,onReject,onRefresh}:{current:WorkspaceAccess;document:DocumentData;documentDirty:boolean;onPending:(pending:boolean)=>void;onContextObserved:()=>void;onReject:(e:unknown)=>void;onRefresh:()=>void}){
 const [saved,setSaved]=useState<ContextData|null>(null);const [draft,setDraft]=useState<ContextSnapshot>(blankContext);const [dirty,setDirty]=useState(false);
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [blocked,setBlocked]=useState(false);const [adoptable,setAdoptable]=useState(false);const [unknown,setUnknown]=useState<{snapshot:ContextSnapshot;base:string|null;revision:number}|null>(null);
 const [zeroAck,setZeroAck]=useState(false);const [loading,setLoading]=useState(true);const [status,setStatus]=useState('');
 const [versions,setVersions]=useState<{version_id:string;revision:number}[]>([]);const [historical,setHistorical]=useState<ContextData|null>(null);
 const draftRef=useRef(draft);draftRef.current=draft;const dirtyRef=useRef(dirty);dirtyRef.current=dirty;
 const inFlight=useRef<AbortController|null>(null);const accessKey=`${current.actor_id}:${current.workspace_id}:${current.policy_epoch.join(':')}`;
 const keyRef=useRef(accessKey);const docRef=useRef(`${document.version_id}:${document.revision}`);const scope=`${accessKey}:${document.id}:${document.version_id}:${document.revision}`;const scopeRef=useRef(scope);scopeRef.current=scope;
 useEffect(()=>()=>inFlight.current?.abort(),[]);
 useEffect(()=>{onPending(dirty||!!unknown);return()=>onPending(false)},[dirty,unknown,onPending]);
 useEffect(()=>{
  if(keyRef.current!==accessKey){keyRef.current=accessKey;inFlight.current?.abort();setSaved(null);setHistorical(null);setVersions([]);if(!dirtyRef.current)setDraft(blankContext());setBlocked(true);setAdoptable(false);setError('当前权限已变化；输入保留，请重新核对上下文。');onRefresh()}
 },[accessKey,onRefresh]);
 useEffect(()=>{
  const next=`${document.version_id}:${document.revision}`;
  if(docRef.current!==next){docRef.current=next;inFlight.current?.abort();setSaved(null);setHistorical(null);setVersions([]);setStatus('正文版本已变化；原上下文确认不再有效，输入已保留。');setBlocked(true);setAdoptable(false)}
 },[document.version_id,document.revision]);
 const protectedError=(problem:unknown)=>{
  if(problem instanceof TemplateError&&['authentication','forbidden','missing'].includes(problem.failure)){
   setSaved(null);setHistorical(null);setVersions([]);if(!dirtyRef.current)setDraft(blankContext());setBlocked(true);setAdoptable(false);if(problem.failure==='authentication')onReject(problem);else onRefresh();return true
  }return false;
 };
 const refresh=async()=>{
  if(busy)return;const requestScope=scope;const controller=new AbortController();inFlight.current?.abort();inFlight.current=controller;setLoading(true);setError('');
  try{const result=await getContext(current,document.id,controller.signal);if(controller.signal.aborted||scopeRef.current!==requestScope)return;const changed=!!saved&&(saved.version_id!==result.version_id||saved.document_version_id!==result.document_version_id||saved.document_revision!==result.document_revision);setSaved(result);onContextObserved();setBlocked(!!unknown||dirtyRef.current&&(changed||blocked));setAdoptable(!unknown&&dirtyRef.current&&(changed||blocked));if(!dirtyRef.current&&!unknown){setDraft(result.snapshot??blankContext());setZeroAck(false)}setStatus(result.state==='CONTEXT_READY'?'精确版本已确认':'上下文尚未满足全部前置条件')}
  catch(problem){if(controller.signal.aborted||scopeRef.current!==requestScope)return;setSaved(null);setHistorical(null);setVersions([]);if(!dirtyRef.current)setDraft(blankContext());setBlocked(true);setError(problem instanceof Error?problem.message:'无法读取上下文');protectedError(problem)}
  finally{if(!controller.signal.aborted)setLoading(false)}
 };
 useEffect(()=>{void refresh(); /* on mount and explicit refresh only; never overwrite an unsaved form */ // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 const loadVersions=async()=>{const requestScope=scope;setError('');try{const page=await getContextVersions(current,document.id);if(scopeRef.current!==requestScope)return;setVersions(page.items);setStatus(page.more?'仅显示最新 100 个版本':'版本列表已重新核对')}catch(problem){if(scopeRef.current!==requestScope)return;setHistorical(null);setVersions([]);setError(problem instanceof Error?problem.message:'历史版本读取失败');protectedError(problem)}};
 const inspect=async(versionId:string)=>{const requestScope=scope;setError('');setHistorical(null);try{const result=await getContextVersion(current,document.id,versionId);if(scopeRef.current!==requestScope)return;setHistorical(result)}catch(problem){if(scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'版本不可读');protectedError(problem)}};
 const change=(next:ContextSnapshot)=>{setDraft(next);dirtyRef.current=true;setDirty(true);setZeroAck(false);setStatus('本地上下文输入尚未保存')};
 const save=async()=>{
  if(busy||blocked||unknown||!saved)return;const requestScope=scope;
  const body=normalize(draftRef.current);const controller=new AbortController();inFlight.current=controller;setBusy(true);setError('');
  try{const result=await saveContext(current,document.id,{base_context_version_id:saved.version_id,context_revision:saved.revision,document_version_id:document.version_id,document_revision:document.revision,snapshot:body},controller.signal);
   if(controller.signal.aborted||scopeRef.current!==requestScope)return;setSaved(result);onContextObserved();if(stable(normalize(draftRef.current))===stable(body)){setDraft(result.snapshot??body);setDirty(false);dirtyRef.current=false}else setStatus('保存期间有后续修改；输入仍未保存');setZeroAck(false);setStatus('上下文版本已保存；仍需明确确认')}
  catch(problem){if(controller.signal.aborted||scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'保存失败');const denied=protectedError(problem);if(!denied&&problem instanceof TemplateError&&problem.failure==='conflict'){setBlocked(true);setAdoptable(false);setStatus('版本冲突；本地输入保留，请重新核对服务端基线后人工处理')}else if(!denied&&problem instanceof TemplateError&&['timeout','unavailable','cancelled','invalid-response'].includes(problem.failure)&&(!problem.status||problem.status===408||problem.status>=500)){setUnknown({snapshot:body,base:saved.version_id,revision:saved.revision});setStatus('保存结果未知，禁止盲目重试')}}
  finally{setBusy(false)}
 };
 const reconcile=async()=>{
  if(!unknown||busy)return;const requestScope=scope;setBusy(true);setError('');
  try{const result=await getContext(current,document.id);if(scopeRef.current!==requestScope)return;setSaved(result);onContextObserved();setBlocked(false);
   if(result.revision===unknown.revision+1&&stable(result.snapshot)===stable(unknown.snapshot)){
    if(stable(normalize(draftRef.current))===stable(unknown.snapshot)){setDraft(result.snapshot!);setDirty(false);dirtyRef.current=false}setUnknown(null);setStatus('已核对原保存结果；如有后续编辑仍需另存')
   }else if(result.version_id===unknown.base&&result.revision===unknown.revision){setUnknown(null);setStatus('原提交未观察到；可明确重试保存')}else{setUnknown(null);setBlocked(true);setStatus('服务端已有另一版本；输入保留，请人工合并后重新读取版本基线')}
  }catch(problem){if(scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'核对失败');protectedError(problem)}finally{setBusy(false)}
 };
 const confirm=async()=>{
  if(!saved?.version_id||busy||dirty||unknown||blocked)return;const requestScope=scope;
  setBusy(true);setError('');try{const result=await confirmContext(current,document.id,{version_id:saved.version_id,document_version_id:document.version_id,document_revision:document.revision,zero_facts_acknowledged:saved.snapshot?.zero_facts===true&&zeroAck});if(scopeRef.current!==requestScope)return;setSaved(result);onContextObserved();setStatus(result.state==='CONTEXT_READY'?'人工确认完成':'前置条件失效，请重新检查')}
  catch(problem){if(scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'确认失败');if(!protectedError(problem)&&problem instanceof TemplateError&&['timeout','unavailable','cancelled','invalid-response'].includes(problem.failure)&&(!problem.status||problem.status===408||problem.status>=500)){setBlocked(true);setStatus('确认结果未知；请重新核对当前版本')}else if(problem instanceof TemplateError&&problem.failure==='conflict')setBlocked(true)}finally{setBusy(false)}
 };
 const conflict=()=>{if(!adoptable||!saved)return;setAdoptable(false);setBlocked(false);setStatus('输入仍保留；请核对并决定是否以当前服务端版本为 base 保存')};
 return <section className="project-context" aria-label="X-15 项目上下文检查器"><h3>项目上下文 · X-15</h3><p>上下文仅手工录入；附件解析结果不自动成为已确认项目事实。</p>
  <AttachmentInspector current={current} document={document} onReject={onReject}/>
  <p role="status">{loading?'正在核对权限与上下文…':blocked?'当前版本不可用于操作':saved?.state==='CONTEXT_READY'&&!dirty&&!documentDirty?'CONTEXT_READY':'CONTEXT_PENDING'} · {status}</p>
  {saved&&!blocked&&<p>上下文版本 {saved.revision} · {saved.version_id??'尚未保存'}{saved.confirmed_at&&<> · 确认人 {saved.confirmed_by} · <time dateTime={saved.confirmed_at}>{saved.confirmed_at}</time></>}</p>}
  {versions.length>0&&<section aria-label="上下文版本历史">{versions.map(v=><button key={v.version_id} onClick={()=>void inspect(v.version_id)}>版本 {v.revision}</button>)}</section>}
  {historical&&!blocked&&<section aria-label="只读历史上下文"><h4>历史版本 {historical.revision} · {historical.state}</h4><p>仅用于核对，不会替换当前输入。</p><pre>{JSON.stringify(historical.snapshot,null,2)}</pre><button onClick={()=>setHistorical(null)}>关闭历史核对</button></section>}
  {documentDirty&&<p role="status">正文有未保存修改；保存正文后将使旧上下文确认失效。请先保存正文再确认。</p>}
  {saved?.reasons.map((r,i)=><p key={`${r.code}:${r.path}:${i}`} className="context-reason">{reasonLabels[r.code]??r.code} · {r.path}</p>)}
  {error&&<p role="alert" className="template-form-error">{error}</p>}
  <button className="btn" disabled={busy} onClick={()=>void refresh()}>重新核对当前版本</button><button className="btn" disabled={busy||blocked} onClick={()=>void loadVersions()}>读取上下文版本历史</button>{unknown&&<button className="btn" disabled={busy} onClick={()=>void reconcile()}>核对未知提交</button>}{blocked&&adoptable&&saved&&!unknown&&<button className="btn" onClick={conflict}>保留输入并采用已核对的版本基线</button>}
  <p>工作区：{current.workspace_id} · 固定模板版本：{document.template_version_id} · 文种：{document.document_type} · 知识范围：{document.knowledge_scope}</p>
  <fieldset disabled={busy||loading||!!unknown}>
   <legend>手工项目上下文</legend><label>项目意图<textarea value={draft.intent} maxLength={2048} onChange={e=>change({...draft,intent:e.target.value})}/></label><label><input type="checkbox" checked={draft.zero_facts} onChange={e=>change({...draft,zero_facts:e.target.checked,facts:e.target.checked?[]:draft.facts})}/>显式声明无项目事实</label>
   {!draft.zero_facts&&<><button type="button" className="btn" disabled={draft.facts.length>=100} onClick={()=>change({...draft,facts:[...draft.facts,{key:'',value:'',unit:null,source:{locator:'',resource_id:null},owner_id:current.actor_id,confirmed:false}]})}>添加事实</button>{draft.facts.map((f,i)=><div className="context-item" key={i}><label>名称<input value={f.key} maxLength={128} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,key:e.target.value}:x)})}/></label><label>值<input value={f.value} maxLength={2048} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,value:e.target.value}:x)})}/></label><label>单位<input value={f.unit??''} maxLength={64} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,unit:e.target.value||null}:x)})}/></label><label>来源定位（manual: 手工文本）<input value={f.source.locator} maxLength={512} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,source:{...x.source,locator:e.target.value}}:x)})}/></label><label>已授权来源资源 ID（可选）<input value={f.source.resource_id??''} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,source:{...x.source,resource_id:e.target.value||null}}:x)})}/></label><label>负责人 ID<input value={f.owner_id} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,owner_id:e.target.value}:x)})}/></label><label><input type="checkbox" checked={f.confirmed} onChange={e=>change({...draft,facts:draft.facts.map((x,j)=>j===i?{...x,confirmed:e.target.checked}:x)})}/>此事实已人工核实</label><button type="button" onClick={()=>change({...draft,facts:draft.facts.filter((_,j)=>j!==i)})}>移除事实</button></div>)}</>}
   <h4>术语</h4><button type="button" disabled={draft.glossary.length>=100} onClick={()=>change({...draft,glossary:[...draft.glossary,{term:'',definition:''}]})}>添加术语</button>{draft.glossary.map((g,i)=><div className="context-item" key={i}><label>术语<input value={g.term} maxLength={128} onChange={e=>change({...draft,glossary:draft.glossary.map((x,j)=>j===i?{...x,term:e.target.value}:x)})}/></label><label>解释<input value={g.definition} maxLength={2048} onChange={e=>change({...draft,glossary:draft.glossary.map((x,j)=>j===i?{...x,definition:e.target.value}:x)})}/></label><button type="button" onClick={()=>change({...draft,glossary:draft.glossary.filter((_,j)=>j!==i)})}>移除</button></div>)}
   <h4>约束</h4><button type="button" disabled={draft.constraints.length>=100} onClick={()=>change({...draft,constraints:[...draft.constraints,{text:'',source:{locator:'',resource_id:null}}]})}>添加约束</button>{draft.constraints.map((c,i)=><div className="context-item" key={i}><label>约束<input value={c.text} maxLength={2048} onChange={e=>change({...draft,constraints:draft.constraints.map((x,j)=>j===i?{...x,text:e.target.value}:x)})}/></label><label>来源定位（manual: 手工文本）<input value={c.source.locator} maxLength={512} onChange={e=>change({...draft,constraints:draft.constraints.map((x,j)=>j===i?{...x,source:{...x.source,locator:e.target.value}}:x)})}/></label><label>已授权来源资源 ID（可选）<input value={c.source.resource_id??''} onChange={e=>change({...draft,constraints:draft.constraints.map((x,j)=>j===i?{...x,source:{...x.source,resource_id:e.target.value||null}}:x)})}/></label><button type="button" onClick={()=>change({...draft,constraints:draft.constraints.filter((_,j)=>j!==i)})}>移除</button></div>)}
   <h4>缺项与待办</h4><button type="button" disabled={draft.missing.length>=100} onClick={()=>change({...draft,missing:[...draft.missing,{key:'',required:true,resolved:false}]})}>添加缺项</button>{draft.missing.map((m,i)=><div className="context-item" key={i}><label>缺项<input value={m.key} maxLength={128} onChange={e=>change({...draft,missing:draft.missing.map((x,j)=>j===i?{...x,key:e.target.value}:x)})}/></label><label><input type="checkbox" checked={m.required} onChange={e=>change({...draft,missing:draft.missing.map((x,j)=>j===i?{...x,required:e.target.checked}:x)})}/>必需</label><label><input type="checkbox" checked={m.resolved} onChange={e=>change({...draft,missing:draft.missing.map((x,j)=>j===i?{...x,resolved:e.target.checked}:x)})}/>已解决</label><button type="button" onClick={()=>change({...draft,missing:draft.missing.filter((_,j)=>j!==i)})}>移除</button></div>)}
  </fieldset>
  {saved?.snapshot?.zero_facts&&!dirty&&<label><input type="checkbox" checked={zeroAck} onChange={e=>setZeroAck(e.target.checked)}/>我明确确认此版本无项目事实</label>}
  <div className="context-actions"><button className="btn" disabled={!dirty||busy||blocked||!!unknown||!saved} onClick={()=>void save()}>保存上下文版本</button><button className="btn primary" disabled={!saved?.version_id||dirty||documentDirty||busy||blocked||!!unknown||saved?.state==='CONTEXT_READY'||!!saved?.snapshot?.zero_facts&&!zeroAck} onClick={()=>void confirm()}>人工确认精确版本</button></div>
 </section>;
}
