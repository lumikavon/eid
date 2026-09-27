import {useEffect,useRef,useState,type KeyboardEvent} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import type {DocumentData} from './template-api';
import {TemplateError} from './template-api';
import {getContext} from './context-api';
import {confirmOutline,getOutline,getOutlineVersion,getOutlineVersions,OutlineError,saveOutline,type OutlineData,type OutlineReason,type OutlineSnapshot,type OutlineVersion} from './outline-api';

const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
const empty=():OutlineSnapshot=>({sections:[]});
const initial=(data:OutlineData):OutlineSnapshot=>data.snapshot??{sections:data.template_sections.map(section=>({id:crypto.randomUUID(),title:section.title,template_section_id:section.id}))};
const reasonLabels:Record<string,string>={OUTLINE_MISSING:'尚无大纲版本',CONTEXT_NOT_READY:'项目上下文尚未确认',DOCUMENT_CHANGED:'正文版本已变化',TEMPLATE_CHANGED:'固定模板版本已变化',CONTEXT_CHANGED:'上下文版本已变化',DOCUMENT_NOT_DRAFT:'文档当前不可编辑',HUMAN_CONFIRMATION_REQUIRED:'需要人工确认精确大纲版本',CONFIRMATION_NOT_READY:'该版本确认时未满足前置条件',CURRENT_EDIT_DENIED:'当前无文档编辑权限',OUTLINE_SUPERSEDED:'已有较新的大纲版本',REQUIRED_SECTION_MISSING:'缺少必选章节',REQUIRED_SECTION_TITLE_CHANGED:'必选章节标题已变化',TEMPLATE_SECTION_TITLE_CHANGED:'模板章节标题已变化',DUPLICATE_SECTION_ID:'章节 ID 重复',DUPLICATE_TEMPLATE_SECTION:'模板章节重复',UNKNOWN_TEMPLATE_SECTION:'模板章节身份无效',TEMPLATE_SECTION_ID_CHANGED:'模板章节的稳定 ID 已变化'};
function localReasons(draft:OutlineSnapshot,data:OutlineData):OutlineReason[]{
 const reasons:OutlineReason[]=[];const seen=new Set<string>();const templates=new Set<string>();
 draft.sections.forEach((section,index)=>{
  if(!section.title.trim())reasons.push({code:'TITLE_REQUIRED',path:`sections[${index}].title`});
  if(seen.has(section.id))reasons.push({code:'DUPLICATE_SECTION_ID',path:`sections[${index}].id`});seen.add(section.id);
  if(section.template_section_id){templates.add(section.template_section_id);const rule=data.template_sections.find(x=>x.id===section.template_section_id);if(!rule)reasons.push({code:'UNKNOWN_TEMPLATE_SECTION',path:`sections[${index}].template_section_id`});else if(section.title!==rule.title)reasons.push({code:'REQUIRED_SECTION_TITLE_CHANGED',path:`sections[${index}].title`,template_section_id:rule.id,expected_title:rule.title})}
 });
 data.required_sections.forEach(rule=>{if(!templates.has(rule.id))reasons.push({code:'REQUIRED_SECTION_MISSING',path:'sections',template_section_id:rule.id,expected_title:rule.title})});
 if(draft.sections.length<1||draft.sections.length>128)reasons.push({code:'SECTION_COUNT_INVALID',path:'sections'});
 return reasons;
}
type UnknownSave={kind:'save';snapshot:OutlineSnapshot;base:string|null;revision:number;documentVersion:string;contextVersion:string};
type UnknownConfirm={kind:'confirm';version:string};
type Unknown=UnknownSave|UnknownConfirm;

export default function OutlineEditor({current,document,documentDirty,contextPending,contextEpoch,onPending,onReject,onRefresh}:{current:WorkspaceAccess;document:DocumentData;documentDirty:boolean;contextPending:boolean;contextEpoch:number;onPending:(pending:boolean)=>void;onReject:(error:unknown)=>void;onRefresh:()=>void}){
 const [saved,setSaved]=useState<OutlineData|null>(null);const [draft,setDraft]=useState<OutlineSnapshot>(empty);const draftRef=useRef(draft);draftRef.current=draft;
 const [contextVersion,setContextVersion]=useState<string|null>(null);
 const [checkedContextEpoch,setCheckedContextEpoch]=useState(-1);const contextEpochRef=useRef(contextEpoch);
 const [dirty,setDirty]=useState(false);const dirtyRef=useRef(dirty);dirtyRef.current=dirty;
 const [blocked,setBlocked]=useState(false);const [adoptable,setAdoptable]=useState(false);const [busy,setBusy]=useState(false);const [loading,setLoading]=useState(true);
 const [unknown,setUnknown]=useState<Unknown|null>(null);const [error,setError]=useState('');const [status,setStatus]=useState('');const [serverReasons,setServerReasons]=useState<OutlineReason[]>([]);
 const [versions,setVersions]=useState<OutlineVersion[]>([]);const [historical,setHistorical]=useState<OutlineData|null>(null);
 const requestRef=useRef<AbortController|null>(null);const accessKey=`${current.actor_id}:${current.workspace_id}:${current.policy_epoch.join(':')}`;
 const keyRef=useRef(accessKey);const documentKey=`${document.id}:${document.version_id}:${document.revision}:${document.template_version_id}`;const documentRef=useRef(documentKey);
 const scope=`${accessKey}:${documentKey}:${contextEpoch}`;const scopeRef=useRef(scope);scopeRef.current=scope;
 useEffect(()=>()=>requestRef.current?.abort(),[]);
 useEffect(()=>{onPending(dirty||!!unknown);return()=>onPending(false)},[dirty,unknown,onPending]);
 useEffect(()=>{
  if(keyRef.current===accessKey)return;keyRef.current=accessKey;requestRef.current?.abort();setSaved(null);setContextVersion(null);setHistorical(null);setVersions([]);setServerReasons([]);if(!dirtyRef.current)setDraft(empty());setBlocked(true);setAdoptable(false);setStatus('当前权限已变化；未提交输入保留，请重新核对');onRefresh();
 },[accessKey,onRefresh]);
 useEffect(()=>{
  if(documentRef.current===documentKey)return;documentRef.current=documentKey;requestRef.current?.abort();setSaved(null);setContextVersion(null);setHistorical(null);setVersions([]);setServerReasons([]);if(!dirtyRef.current)setDraft(empty());setBlocked(true);setAdoptable(false);setStatus('正文或固定模板版本已变化；请重新核对大纲，输入已保留');
 },[documentKey]);
 const protectedError=(problem:unknown)=>{
  if(problem instanceof TemplateError&&['authentication','forbidden','missing'].includes(problem.failure)){
   setSaved(null);setContextVersion(null);setHistorical(null);setVersions([]);setServerReasons([]);if(!dirtyRef.current)setDraft(empty());setBlocked(true);setAdoptable(false);
   if(problem.failure==='authentication')onReject(problem);else onRefresh();return true;
  }return false;
 };
 const load=async(force=false)=>{
  if(busy&&!force)return;const requestScope=scope;const controller=new AbortController();requestRef.current?.abort();requestRef.current=controller;setLoading(true);setError('');
  try{
   const result=await getOutline(current,document.id,controller.signal);const context=await getContext(current,document.id,controller.signal);if(controller.signal.aborted||scopeRef.current!==requestScope)return;
   const changed=!!saved&&(saved.version_id!==result.version_id||saved.document_version_id!==result.document_version_id||saved.context_version_id!==result.context_version_id||saved.template_version_id!==result.template_version_id);
   setSaved(result);setContextVersion(context.state==='CONTEXT_READY'?context.version_id:null);setCheckedContextEpoch(contextEpoch);setServerReasons([]);setBlocked(!!unknown||dirtyRef.current&&(force||changed||blocked));setAdoptable(!unknown&&dirtyRef.current&&(force||changed||blocked));
   if(!dirtyRef.current&&!unknown){const next=initial(result);draftRef.current=next;setDraft(next);setBlocked(false)}
   setStatus(result.state==='OUTLINE_READY'&&context.state==='CONTEXT_READY'&&result.context_version_id===context.version_id?'精确大纲版本已确认':'大纲尚未满足全部生成前置条件');
  }catch(problem){if(controller.signal.aborted||scopeRef.current!==requestScope)return;setSaved(null);setContextVersion(null);setHistorical(null);setVersions([]);setServerReasons([]);if(!dirtyRef.current)setDraft(empty());setBlocked(true);setError(problem instanceof Error?problem.message:'读取大纲失败');protectedError(problem)}
  finally{if(!controller.signal.aborted)setLoading(false)}
 };
 useEffect(()=>{void load(); // Initial read only; later reads require an explicit user action.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 useEffect(()=>{
  if(contextEpochRef.current===contextEpoch)return;contextEpochRef.current=contextEpoch;requestRef.current?.abort();setSaved(null);setContextVersion(null);setCheckedContextEpoch(-1);setHistorical(null);setVersions([]);setServerReasons([]);setBlocked(true);setAdoptable(false);setStatus('上下文版本或确认状态已变化；正在重新核对大纲资格');void load(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[contextEpoch]);
 const revise=(next:OutlineSnapshot)=>{draftRef.current=next;setDraft(next);dirtyRef.current=true;setDirty(true);setServerReasons([]);setStatus('本地大纲尚未保存')};
 const move=(index:number,delta:number)=>{const target=index+delta;if(target<0||target>=draft.sections.length)return;const sections=[...draft.sections];[sections[index],sections[target]]=[sections[target],sections[index]];revise({sections})};
 const onMoveKey=(event:KeyboardEvent<HTMLButtonElement>,index:number)=>{if(event.altKey&&(event.key==='ArrowUp'||event.key==='ArrowDown')){event.preventDefault();move(index,event.key==='ArrowUp'?-1:1)}};
 const structural=saved?localReasons(draft,saved):[];
 const save=async()=>{
  if(busy||loading||blocked||unknown||!saved||!dirty||structural.length||documentDirty||contextPending||!contextVersion||checkedContextEpoch!==contextEpoch)return;
  const requestScope=scope;const submittedDraft=draftRef.current;const snapshot:OutlineSnapshot={sections:submittedDraft.sections.map(section=>({...section,title:section.title.trim()}))};
  const controller=new AbortController();requestRef.current=controller;setBusy(true);setError('');setServerReasons([]);
  try{
   const result=await saveOutline(current,document.id,{base_outline_version_id:saved.version_id,outline_revision:saved.revision,document_version_id:document.version_id,document_revision:document.revision,context_version_id:contextVersion,template_version_id:document.template_version_id,snapshot},controller.signal);
   if(controller.signal.aborted||scopeRef.current!==requestScope)return;setSaved(result);setBlocked(false);setAdoptable(false);
   if(draftRef.current===submittedDraft){draftRef.current=result.snapshot!;setDraft(result.snapshot!);dirtyRef.current=false;setDirty(false);setStatus('大纲版本已保存；仍需明确人工确认')}
   else setStatus('大纲版本已保存；保存期间的后续输入仍未保存');
  }catch(problem){if(controller.signal.aborted||scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'保存失败，输入仍在本地');
   if(!protectedError(problem)&&problem instanceof OutlineError){setServerReasons(problem.reasons);if(problem.failure==='conflict'){setBlocked(true);setAdoptable(false);setStatus('版本冲突；请重新核对当前服务端版本')}else if(['timeout','unavailable','cancelled','invalid-response'].includes(problem.failure)&&(!problem.status||problem.status===408||problem.status>=500)){setUnknown({kind:'save',snapshot,base:saved.version_id,revision:saved.revision,documentVersion:document.version_id,contextVersion});setSaved(null);setContextVersion(null);setHistorical(null);setVersions([]);setBlocked(true);setStatus('保存结果未知；禁止盲目重试')}}
  }finally{setBusy(false)}
 };
 const confirm=async()=>{
  if(busy||loading||blocked||unknown||dirty||documentDirty||contextPending||checkedContextEpoch!==contextEpoch||!contextVersion||!saved?.version_id||saved.context_version_id!==contextVersion||saved.state==='OUTLINE_READY'||saved.reasons.some(r=>r.code!=='HUMAN_CONFIRMATION_REQUIRED'))return;
  const requestScope=scope;const version=saved.version_id;setBusy(true);setError('');
  try{const result=await confirmOutline(current,document.id,{version_id:version,document_version_id:document.version_id,document_revision:document.revision,context_version_id:saved.context_version_id,template_version_id:document.template_version_id});if(scopeRef.current!==requestScope)return;setSaved(result);setStatus('人工确认完成 · OUTLINE_READY')}
  catch(problem){if(scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'确认失败');if(!protectedError(problem)&&problem instanceof OutlineError){setServerReasons(problem.reasons);if(problem.failure==='conflict')setBlocked(true);else if(['timeout','unavailable','cancelled','invalid-response'].includes(problem.failure)&&(!problem.status||problem.status===408||problem.status>=500)){setUnknown({kind:'confirm',version});setSaved(null);setContextVersion(null);setHistorical(null);setVersions([]);setBlocked(true);setStatus('确认结果未知；请核对当前版本')}}}
  finally{setBusy(false)}
 };
 const reconcile=async()=>{
  if(!unknown||busy)return;const requestScope=scope;setBusy(true);setError('');
  try{const result=await getOutline(current,document.id);const context=await getContext(current,document.id);if(scopeRef.current!==requestScope)return;setSaved(result);setContextVersion(context.state==='CONTEXT_READY'?context.version_id:null);setCheckedContextEpoch(contextEpoch);
   if(unknown.kind==='save'&&result.base_version_id===unknown.base&&result.revision===unknown.revision+1&&result.document_version_id===unknown.documentVersion&&result.context_version_id===unknown.contextVersion&&same(result.snapshot,unknown.snapshot)){
    setUnknown(null);setBlocked(true);setAdoptable(true);setStatus('发现等价服务端版本，但无法确认由本次提交产生；输入保留，请人工核对并采用版本基线');
   }else if(unknown.kind==='confirm'&&result.version_id===unknown.version&&result.confirmed_at){setUnknown(null);setBlocked(false);setStatus('已核对精确版本的确认状态')}
   else if(unknown.kind==='save'&&result.version_id===unknown.base&&result.revision===unknown.revision){setUnknown(null);setBlocked(true);setAdoptable(true);setStatus('原保存未观察到；可人工采用已核对的版本基线后再保存')}
   else if(unknown.kind==='confirm'&&result.version_id===unknown.version&&!result.confirmed_at){setUnknown(null);setBlocked(false);setStatus('原确认未观察到；可明确再次确认')}
   else{setUnknown(null);setBlocked(true);setAdoptable(dirtyRef.current);setStatus('服务端版本或前置条件已变化；输入保留，请人工核对')}
  }catch(problem){if(scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'核对失败');protectedError(problem)}finally{setBusy(false)}
 };
 const loadVersions=async()=>{const requestScope=scope;setError('');try{const page=await getOutlineVersions(current,document.id);if(scopeRef.current!==requestScope)return;setVersions(page.items);setStatus(page.more?'仅显示最新 100 个版本':'历史版本列表已更新')}catch(problem){if(scopeRef.current!==requestScope)return;setHistorical(null);setVersions([]);setError(problem instanceof Error?problem.message:'历史读取失败');protectedError(problem)}};
 const inspect=async(versionId:string)=>{const requestScope=scope;setError('');setHistorical(null);try{const result=await getOutlineVersion(current,document.id,versionId);if(scopeRef.current!==requestScope)return;setHistorical(result)}catch(problem){if(scopeRef.current!==requestScope)return;setError(problem instanceof Error?problem.message:'版本不可读');protectedError(problem)}};
 const adopt=()=>{if(!adoptable||!saved||unknown)return;setAdoptable(false);setBlocked(false);setStatus('输入已保留；请核对后决定是否以当前服务端版本为基线保存')};
 const contextMatches=!!contextVersion&&saved?.context_version_id===contextVersion;
 const displayed=[...structural,...serverReasons,...(saved?.reasons??[])];
 return <section className="outline-editor" aria-label="X-15 生成前大纲"><h3>生成前完整大纲 · X-15</h3><p>大纲版本与正文 AST 分开保存；这里重排章节不会重排正文。</p>
  <p role="status">{loading?'正在核对当前权限和大纲…':blocked||checkedContextEpoch!==contextEpoch?'当前版本不可操作':saved?.state==='OUTLINE_READY'&&contextMatches&&!dirty&&!documentDirty&&!contextPending?'OUTLINE_READY':'OUTLINE_PENDING'} · {status}</p>
  {saved&&!blocked&&checkedContextEpoch===contextEpoch&&<p>大纲版本 {saved.revision} · {saved.version_id??'尚未保存'}{saved.confirmed_at&&<> · 确认人 {saved.confirmed_by} · <time dateTime={saved.confirmed_at}>{saved.confirmed_at}</time></>}</p>}
  {error&&<p role="alert" className="template-form-error">{error}</p>}
  {documentDirty&&<p role="status">正文有未保存修改；请先保存正文，再重新核对大纲前置版本。</p>}{contextPending&&<p role="status">项目上下文有未提交输入；请先核对上下文。</p>}
  {displayed.length>0&&<ul className="outline-reasons" aria-label="大纲缺项与前置原因">{displayed.map((item,index)=><li key={`${item.code}:${item.path}:${index}`}>{reasonLabels[item.code]??item.code} · {item.path}{item.expected_title&&` · ${item.expected_title}`}{item.context_reasons?.map(r=>` · ${r.code}: ${r.path}`)}</li>)}</ul>}
  <div className="outline-actions"><button type="button" disabled={busy} onClick={()=>void load()}>重新核对当前版本</button><button type="button" disabled={busy||blocked} onClick={()=>void loadVersions()}>读取大纲历史</button>{unknown&&<button type="button" disabled={busy} onClick={()=>void reconcile()}>核对未知结果</button>}{blocked&&adoptable&&saved&&!unknown&&<button type="button" onClick={adopt}>保留输入并采用已核对的版本基线</button>}</div>
  {versions.length>0&&<section aria-label="大纲版本历史"><h4>历史版本</h4>{versions.map(item=><button type="button" key={item.version_id} onClick={()=>void inspect(item.version_id)}>版本 {item.revision}{item.confirmed_at?' · 已确认':''}</button>)}</section>}
  {historical&&!blocked&&<section aria-label="只读历史大纲"><h4>版本 {historical.revision} · {historical.state}</h4><p>只读核对，不会替换当前输入。</p><ol>{historical.snapshot?.sections.map(section=><li key={section.id}>{section.title}</li>)}</ol><button type="button" onClick={()=>setHistorical(null)}>关闭历史核对</button></section>}
  <p>工作区：{current.workspace_id} · 固定模板版本：{document.template_version_id}</p>
  <fieldset disabled={busy||loading||!!unknown||blocked||!saved}><legend>手工大纲树</legend><ol className="outline-tree">{draft.sections.map((section,index)=>{const rule=saved?.template_sections.find(x=>x.id===section.template_section_id);return <li key={section.id}><div className="outline-row"><span className="outline-number">{index+1}.</span><label>{rule?.mandatory?'必选章节':'章节标题'}<input value={section.title} maxLength={256} readOnly={!!rule} aria-readonly={!!rule} onChange={event=>revise({sections:draft.sections.map(x=>x.id===section.id?{...x,title:event.target.value}:x)})}/></label>{rule?.mandatory&&<span className="outline-required">必选 · 标题固定</span>}<button type="button" aria-label={`上移 ${section.title}`} disabled={index===0} onKeyDown={event=>onMoveKey(event,index)} onClick={()=>move(index,-1)}>↑</button><button type="button" aria-label={`下移 ${section.title}`} disabled={index===draft.sections.length-1} onKeyDown={event=>onMoveKey(event,index)} onClick={()=>move(index,1)}>↓</button><button type="button" aria-label={`删除 ${section.title}`} disabled={!!rule?.mandatory} onClick={()=>revise({sections:draft.sections.filter(x=>x.id!==section.id)})}>删除</button></div></li>})}</ol><button type="button" disabled={draft.sections.length>=128} onClick={()=>revise({sections:[...draft.sections,{id:crypto.randomUUID(),title:'新章节',template_section_id:null}]})}>添加章节</button><p>可用按钮或在移动按钮上按 Alt + ↑ / ↓ 调整顺序。必选章节不能删除或改标题。</p></fieldset>
  <div className="outline-actions"><button className="btn" disabled={!dirty||busy||loading||blocked||!!unknown||!saved||!contextVersion||checkedContextEpoch!==contextEpoch||structural.length>0||documentDirty||contextPending} onClick={()=>void save()}>保存大纲版本</button><button className="btn primary" disabled={!saved?.version_id||dirty||busy||loading||blocked||!!unknown||!contextMatches||checkedContextEpoch!==contextEpoch||documentDirty||contextPending||saved.state==='OUTLINE_READY'||saved.reasons.some(r=>r.code!=='HUMAN_CONFIRMATION_REQUIRED')} onClick={()=>void confirm()}>人工确认精确版本</button></div>
 </section>;
}
