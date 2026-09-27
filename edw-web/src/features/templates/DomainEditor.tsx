import {useCallback,useEffect,useRef,useState} from 'react';
import {EditorContent,useEditor,type Editor} from '@tiptap/react';
import {StarterKit} from '@tiptap/starter-kit';
import {TableKit} from '@tiptap/extension-table';
import {TextAlign} from '@tiptap/extension-text-align';
import {TextStyleKit} from '@tiptap/extension-text-style';
import type {WorkspaceAccess} from '../../app/access-api';
import {getDocument,getImage,saveDocument,uploadImage,TemplateError,type DocumentData,type SaveTiming} from './template-api';
import {sameDomainValue} from './domain-merge';
import VersionHistory from './VersionHistory';
import ProjectContext from './ProjectContext';
import {registerDocumentHistoryGuard} from './navigation-guard';
import {DomainAtom,DomainHeading,DomainParagraph,DomainTable,domainToEditor,editorToDomain,type DomainAst,type DomainSection} from './domain-adapter';

const extensions=[StarterKit.configure({paragraph:false,heading:false,blockquote:false,codeBlock:false,horizontalRule:false,strike:false,code:false,link:{openOnClick:false,autolink:false}}),DomainParagraph,DomainHeading,DomainAtom,TableKit.configure({table:false}),DomainTable,TextAlign.configure({types:['paragraph','heading']}),TextStyleKit];
const uuid=()=>crypto.randomUUID();
function SectionCanvas({section,onChange,onEditor,onValidityChange,editable}: {section:DomainSection;onChange:(value:DomainSection)=>void;onEditor:(editor:Editor|null)=>void;onValidityChange:(valid:boolean)=>void;editable:boolean}){
 const source=useRef(section);source.current=section;
 const update=useRef(onChange);update.current=onChange;
 const validity=useRef(onValidityChange);validity.current=onValidityChange;
 const [message,setMessage]=useState('');
 const editor=useEditor({extensions,content:domainToEditor(section),immediatelyRender:false,
  onUpdate:({editor:instance})=>{
   const tr=instance.state.tr;const seen=new Set<string>();
   instance.state.doc.descendants((node,pos)=>{
    if(node.type.name==='table'||node.type.name==='paragraph'||node.type.name==='heading'){
     const id=typeof node.attrs.blockId==='string'?node.attrs.blockId:'';
     if(!id||seen.has(id)){const replacement=uuid();tr.setNodeMarkup(pos,undefined,{...node.attrs,blockId:replacement});seen.add(replacement)}
     else seen.add(id);
    }
    if(node.type.name==='table')return false;
    return true;
   });
   if(tr.docChanged){instance.view.dispatch(tr);return}
   try{update.current(editorToDomain(source.current,instance.getJSON()));setMessage('');validity.current(true)}
   catch(error){setMessage(error instanceof Error?error.message:'编辑器结构无法保存');validity.current(false)}
  },
 });
 useEffect(()=>{onEditor(editor);return()=>onEditor(null)},[editor,onEditor]);
 useEffect(()=>{editor?.setEditable(editable)},[editor,editable]);
 return <><EditorContent editor={editor} aria-label={`${section.title}正文编辑区`} className="domain-editor-content"/>{message&&<p className="template-form-error" role="alert">{message}</p>}</>;
}

function ImagePreview({current,documentId,resourceId,alt}: {current:WorkspaceAccess;documentId:string;resourceId:string;alt:string}){
 const [url,setUrl]=useState('');const [error,setError]=useState('');
 useEffect(()=>{
  let active=true;let objectUrl='';const controller=new AbortController();
  void getImage(current,documentId,resourceId,controller.signal).then(blob=>{
   if(!active)return;objectUrl=URL.createObjectURL(blob);setUrl(objectUrl);setError('');
  }).catch(problem=>{if(active)setError(problem instanceof Error?problem.message:'无法读取图片')});
  return()=>{active=false;controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl)};
 },[current,documentId,resourceId]);
 return <div>{url?<img src={url} alt={alt} style={{maxWidth:'100%',height:'auto'}}/>:<p role="status">{error||'正在核验图片权限…'}</p>}</div>;
}

export default function DomainEditor({current,value,onReject,onRefresh,onRegisterBack,onNavigateBack,onConfirmed,onRegisterNavigationGuard,onNavigateTo}: {current:WorkspaceAccess;value:DocumentData;onReject:(error:unknown)=>void;onRefresh:()=>void;onRegisterBack:(handler:()=>void)=>void;onNavigateBack:()=>void;onConfirmed:(value:DocumentData)=>void;onRegisterNavigationGuard?:(handler:((destination:string)=>void)|null)=>void;onNavigateTo?:(destination:string)=>void}){
 const [draft,setDraft]=useState<DomainAst>(()=>structuredClone(value.ast) as DomainAst);
 const draftRef=useRef(draft);draftRef.current=draft;
 const [confirmed,setConfirmed]=useState(value);const confirmedRef=useRef(value);
 const [base,setBase]=useState({version_id:value.version_id,revision:value.revision});const baseRef=useRef(base);
 const [dirty,setDirty]=useState(false);const dirtyRef=useRef(false);
 const [status,setStatus]=useState('已加载，尚未修改');const [saving,setSaving]=useState(false);const savingRef=useRef(false);const [valid,setValid]=useState(true);
 const [lastSavedAt,setLastSavedAt]=useState('');const [timing,setTiming]=useState<SaveTiming|null>(null);
 const [online,setOnline]=useState(()=>typeof navigator==='undefined'||navigator.onLine);
 const [historyMode,setHistoryMode]=useState<'history'|'conflict'|null>(null);
 const [contextOpen,setContextOpen]=useState(false);
 const [contextPending,setContextPending]=useState(false);const contextPendingRef=useRef(false);
 const onContextPending=useCallback((pending:boolean)=>{contextPendingRef.current=pending;setContextPending(pending)},[]);
 const [unknown,setUnknown]=useState<{sent:DomainAst;baseVersion:string;revision:number}|null>(null);const [autoBlocked,setAutoBlocked]=useState(false);const [leaveOpen,setLeaveOpen]=useState(false);const leaveDestination=useRef<string|null>(null);
 const serverVersion=useRef(value.version_id);
 const [active,setActive]=useState(value.ast.document.sections[0]?.id??'');const [editor,setEditor]=useState<Editor|null>(null);const [canvasGeneration,setCanvasGeneration]=useState(0);
 const [link,setLink]=useState('');const [preview,setPreview]=useState('');const fileInput=useRef<HTMLInputElement|null>(null);const controller=useRef<AbortController|null>(null);
 const section=draft.document.sections.find(item=>item.id===active)??draft.document.sections[0];
 const figures=section?.blocks.filter(block=>block.type==='figure'&&typeof block.content?.resource_id==='string')??[];
 const selectedFigure=figures.find(block=>block.content.resource_id===preview);
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{const change=()=>{const available=navigator.onLine;setOnline(available);if(!available)setStatus('离线 · 本地草稿未保存')};window.addEventListener('online',change);window.addEventListener('offline',change);return()=>{window.removeEventListener('online',change);window.removeEventListener('offline',change)}},[]);
 useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(!dirtyRef.current&&!contextPendingRef.current)return;event.preventDefault();event.returnValue='' };window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[]);
 useEffect(()=>{
  if(serverVersion.current===value.version_id)return;
  serverVersion.current=value.version_id;
  if(dirtyRef.current){setStatus('服务端版本已变化，本地草稿未被替换；请比较版本');setAutoBlocked(true);setHistoryMode('conflict');return}
  const refreshed=structuredClone(value.ast) as DomainAst;draftRef.current=refreshed;setDraft(refreshed);setCanvasGeneration(n=>n+1);
  const nextBase={version_id:value.version_id,revision:value.revision};baseRef.current=nextBase;setBase(nextBase);confirmedRef.current=value;setConfirmed(value);
  setActive(refreshed.document.sections[0]?.id??'');setPreview('');setStatus('已重新读取最新版本');
 },[value]);
 const revise=(next:DomainAst)=>{draftRef.current=next;setDraft(next);dirtyRef.current=true;setDirty(true);if(!unknown&&historyMode!=='conflict')setAutoBlocked(false);setStatus(online?'尚未保存 · 空闲 1000ms 后自动保存':'离线 · 本地草稿未保存')};
 const updateSection=(next:DomainSection)=>revise({...draft,document:{...draft.document,sections:draft.document.sections.map(item=>item.id===next.id?next:item)}});
 const changeTitle=(title:string)=>revise({...draft,document:{...draft.document,metadata:{...draft.document.metadata,title}}});
 const persist=async(mode:'auto'|'explicit'='explicit',debounceMs=0):Promise<boolean>=>{
  if(!dirtyRef.current||savingRef.current||!valid||unknown||historyMode)return false;
  if(!online){setStatus('离线 · 本地草稿未保存');return false}
  const source=draftRef.current;const title=String(source.document.metadata.title??'').trim();
  if(!title||title.length>256){setStatus('文档名称必须为 1–256 字符');setAutoBlocked(true);return false}
  const sent={...source,document:{...source.document,metadata:{...source.document.metadata,title}}};
  const expected=baseRef.current;const request=new AbortController();controller.current=request;savingRef.current=true;setSaving(true);setStatus(mode==='auto'?'正在自动保存…':'正在保存…');
  try{
   const result=await saveDocument(current,value.id,{base_version_id:expected.version_id,revision:expected.revision,ast:sent},request.signal,setTiming,debounceMs);
   if(request.signal.aborted)return false;
   serverVersion.current=result.version_id;const nextBase={version_id:result.version_id,revision:result.revision};baseRef.current=nextBase;setBase(nextBase);
   confirmedRef.current=result;setConfirmed(result);onConfirmed(result);setUnknown(null);setAutoBlocked(false);setLastSavedAt(new Date().toISOString());
   if(sameDomainValue(draftRef.current,source)){const saved=result.ast as DomainAst;if(!sameDomainValue(saved,source))setCanvasGeneration(n=>n+1);draftRef.current=saved;setDraft(saved);dirtyRef.current=false;setDirty(false);setStatus(`已保存 · 版本 ${result.revision}`);return true}
   dirtyRef.current=true;setDirty(true);setStatus('本次版本已确认；保存期间的后续编辑仍未保存');return false;
  }catch(error){
   if(request.signal.aborted)return false;
   setAutoBlocked(true);
   if(error instanceof TemplateError&&error.failure==='conflict'){setStatus('版本冲突 · 本地草稿保留，请逐块核对');setHistoryMode('conflict')}
   else if(error instanceof TemplateError&&['timeout','cancelled','invalid-response','unavailable'].includes(error.failure)&&!error.status){
    setUnknown({sent:sent as DomainAst,baseVersion:expected.version_id,revision:expected.revision});setStatus('保存结果未知 · 请先核对服务端，不得盲目重试');
   }else{setStatus(error instanceof Error?error.message:'保存失败，本地草稿尚未保存');if(error instanceof TemplateError&&error.failure==='authentication')onReject(error);else if(error instanceof TemplateError&&['forbidden','missing','readonly'].includes(error.failure))onRefresh()}
   return false;
  }finally{savingRef.current=false;setSaving(false)}
 };
 const saveRef=useRef(persist);saveRef.current=persist;
 useEffect(()=>{if(!dirty||!valid||saving||autoBlocked||unknown||historyMode||!online)return;const started=performance.now();const timer=setTimeout(()=>void saveRef.current('auto',Math.round(performance.now()-started)),1000);return()=>clearTimeout(timer)},[draft,dirty,valid,saving,autoBlocked,unknown,historyMode,online]);
 useEffect(()=>{const shortcut=(event:KeyboardEvent)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();void saveRef.current('explicit')}};window.addEventListener('keydown',shortcut);return()=>window.removeEventListener('keydown',shortcut)},[]);
 useEffect(()=>{onRegisterBack(()=>{leaveDestination.current=null;if(!dirtyRef.current&&!contextPendingRef.current&&!savingRef.current){onNavigateBack();return}setLeaveOpen(true)});return()=>onRegisterBack(onNavigateBack)},[onRegisterBack,onNavigateBack]);
 useEffect(()=>{if(!onRegisterNavigationGuard||!onNavigateTo)return;onRegisterNavigationGuard(destination=>{leaveDestination.current=destination;if(!dirtyRef.current&&!contextPendingRef.current&&!savingRef.current){onNavigateTo(destination);return}setLeaveOpen(true)});return()=>onRegisterNavigationGuard(null)},[onRegisterNavigationGuard,onNavigateTo]);
 useEffect(()=>registerDocumentHistoryGuard(destination=>{if(!dirtyRef.current&&!contextPendingRef.current&&!savingRef.current)return false;leaveDestination.current=destination;setLeaveOpen(true);return true}),[]);
 const leave=()=>{const destination=leaveDestination.current;if(destination&&onNavigateTo)onNavigateTo(destination);else onNavigateBack()};
 const reconcile=async()=>{
  if(!unknown)return;setStatus('正在核对原保存结果…');
  try{
   const actual=await getDocument(current,value.id);
   if(actual.base_version_id===unknown.baseVersion&&actual.revision===unknown.revision+1&&sameDomainValue(actual.ast,unknown.sent)){
    serverVersion.current=actual.version_id;const nextBase={version_id:actual.version_id,revision:actual.revision};baseRef.current=nextBase;setBase(nextBase);confirmedRef.current=actual;setConfirmed(actual);onConfirmed(actual);setLastSavedAt(new Date().toISOString());
    if(sameDomainValue(draftRef.current,unknown.sent)){const saved=actual.ast as DomainAst;if(!sameDomainValue(saved,draftRef.current))setCanvasGeneration(n=>n+1);draftRef.current=saved;setDraft(saved);dirtyRef.current=false;setDirty(false);setStatus('已核对服务端提交成功')}else setStatus('已核对上次保存；后续编辑仍未保存');
    setUnknown(null);setAutoBlocked(false);setHistoryMode(null);return;
   }
   setUnknown(null);setAutoBlocked(true);
   if(actual.version_id!==unknown.baseVersion){setStatus('服务端版本已变化 · 本地草稿保留');setHistoryMode('conflict')}
   else setStatus('未观察到原提交；请明确选择重新保存，不自动重试');
  }catch(error){setStatus(error instanceof Error?error.message:'无法核对原提交');if(error instanceof TemplateError&&['authentication','forbidden','missing'].includes(error.failure)){setHistoryMode(null);if(error.failure==='authentication')onReject(error);else onRefresh()}}
 };
 const merge=async(merged:DomainAst,latest:DocumentData):Promise<boolean>=>{
  if(savingRef.current||!online||!valid)return false;
  savingRef.current=true;setSaving(true);setStatus('正在检查合并版本…');
  try{
   const result=await saveDocument(current,value.id,{base_version_id:latest.version_id,revision:latest.revision,ast:merged},undefined,setTiming,0);
   serverVersion.current=result.version_id;const nextBase={version_id:result.version_id,revision:result.revision};baseRef.current=nextBase;setBase(nextBase);confirmedRef.current=result;setConfirmed(result);onConfirmed(result);
   const saved=result.ast as DomainAst;draftRef.current=saved;setDraft(saved);setCanvasGeneration(n=>n+1);dirtyRef.current=false;setDirty(false);setAutoBlocked(false);setUnknown(null);setLastSavedAt(new Date().toISOString());setStatus(`合并已保存 · 版本 ${result.revision}`);return true;
  }catch(error){
   if(error instanceof TemplateError&&['timeout','cancelled','invalid-response','unavailable'].includes(error.failure)&&!error.status){
    draftRef.current=merged;setDraft(merged);setCanvasGeneration(n=>n+1);dirtyRef.current=true;setDirty(true);
    setUnknown({sent:merged,baseVersion:latest.version_id,revision:latest.revision});setAutoBlocked(true);
    setStatus('合并保存结果未知 · 请核对原提交，不得盲目重试');throw error;
   }
   setStatus(error instanceof Error?error.message:'合并未保存，本地草稿保留');if(error instanceof TemplateError&&['authentication','forbidden','missing','readonly'].includes(error.failure)){setHistoryMode(null);if(error.failure==='authentication')onReject(error);else onRefresh()}return false;
  }finally{savingRef.current=false;setSaving(false)}
 };
 const insertImage=async(file:File|null)=>{
  if(!file||!section||!editor||saving)return;
  if(file.size>5*1024*1024){setStatus('图片超过 5MB');return}
  const alt=window.prompt('请输入图片替代文字（必填）')?.trim();if(!alt){setStatus('图片需要替代文字');return}
  setStatus('正在安全上传图片…');
  try{
   const image=await uploadImage(current,value.id,new Uint8Array(await file.arrayBuffer()),alt);
   const blockId=uuid();editor.chain().focus().insertContent({type:'domainAtom',attrs:{blockId,raw:{id:blockId,type:'figure',content:{resource_id:image.id,alt:image.alt,width:image.width,height:image.height}}}}).run();
   setStatus('图片已上传，文档仍需保存');
  }catch(error){setStatus(error instanceof Error?error.message:'图片上传失败');if(error instanceof TemplateError&&error.failure==='authentication')onReject(error);else if(error instanceof TemplateError&&['forbidden','missing'].includes(error.failure))onRefresh()}
 };
 const applyLink=()=>{if(!editor)return;try{const parsed=new URL(link);if(!['https:','http:'].includes(parsed.protocol)||parsed.username||parsed.password)throw new Error();editor.chain().focus().setLink({href:parsed.toString()}).run();setLink('')}catch{setStatus('仅支持安全的 HTTP(S) 链接')}};
 return <><div className="editor-layout" data-testid="domain-editor"><section className="editor-main"><div className="doc-top"><b>领域 AST 草稿</b><span>文档版本 {base.version_id}</span><span>修订 {base.revision}</span><span role="status">{status}</span>{lastSavedAt&&<time dateTime={lastSavedAt}>本机确认：{new Date(lastSavedAt).toLocaleTimeString()}</time>}{timing&&<span title="分层保存计时">空闲 {timing.debounce_ms}ms · 客户端请求 {Math.round(timing.client_request_ms)}ms · 服务端 {timing.server_processing_ms===null?'未提供':`${timing.server_processing_ms}ms`}</span>}{unknown&&<button onClick={()=>void reconcile()}>核对原提交</button>}<button onClick={()=>setHistoryMode('history')}>版本历史</button><button onClick={()=>setContextOpen(open=>!open)} aria-expanded={contextOpen} aria-controls="projectContextPanel">{contextOpen?'收起项目上下文':'检查项目上下文'}</button><button className="btn primary" disabled={!dirty||saving||!valid||!!unknown||historyMode!==null} onClick={()=>void persist('explicit')}>保存</button></div>
  <fieldset className="doc-toolbar" aria-label="结构化编辑工具栏" disabled={historyMode!==null}>
   <button onClick={()=>editor?.chain().focus().undo().run()} disabled={!editor}>撤销</button><button onClick={()=>editor?.chain().focus().redo().run()} disabled={!editor}>重做</button>
   <button onClick={()=>editor?.chain().focus().toggleBold().run()} disabled={!editor}>粗体</button><button onClick={()=>editor?.chain().focus().toggleItalic().run()} disabled={!editor}>斜体</button><button onClick={()=>editor?.chain().focus().toggleUnderline().run()} disabled={!editor}>下划线</button>
   <button onClick={()=>editor?.chain().focus().toggleBulletList().run()} disabled={!editor}>项目列表</button><button onClick={()=>editor?.chain().focus().toggleOrderedList().run()} disabled={!editor}>编号列表</button>
   <button onClick={()=>editor?.chain().focus().setTextAlign('left').run()} disabled={!editor}>左对齐</button><button onClick={()=>editor?.chain().focus().setTextAlign('center').run()} disabled={!editor}>居中</button><button onClick={()=>editor?.chain().focus().setTextAlign('right').run()} disabled={!editor}>右对齐</button>
   <label>颜色<input aria-label="文字颜色" type="color" onChange={event=>editor?.chain().focus().setColor(event.target.value).run()} disabled={!editor}/></label>
   <input aria-label="链接地址" type="url" value={link} onChange={event=>setLink(event.target.value)} placeholder="https://…"/><button onClick={applyLink} disabled={!editor}>设置链接</button>
   <button onClick={()=>editor?.chain().focus().insertTable({rows:2,cols:2,withHeaderRow:false}).run()} disabled={!editor}>插入表格</button>
   <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" style={{display:'none'}} aria-label="选择图片" onChange={event=>{void insertImage(event.target.files?.[0]??null);event.target.value=''}}/><button onClick={()=>fileInput.current?.click()} disabled={!editor}>插入图片</button>
  </fieldset>
  <div className="doc-scroll"><article className="paper" aria-label="结构化文档编辑画布"><label htmlFor="docTitle">文档标题</label><input id="docTitle" value={String(draft.document.metadata.title??'')} onChange={event=>changeTitle(event.target.value)} maxLength={256} disabled={historyMode!==null}/>{section&&<section key={`${section.id}:${canvasGeneration}`}><h2>{section.title}</h2><SectionCanvas section={section} onChange={updateSection} onEditor={setEditor} onValidityChange={setValid} editable={historyMode===null}/></section>}</article></div>
 </section><aside className="ai-side"><div className="ai-tabs"><button className="active" disabled>文档结构</button></div><div className="ai-body" hidden={contextOpen}><p>内容保存为领域 AST；未知未来节点只读保留。图像仅使用当前授权资源。</p><nav id="docTree" aria-label="文档章节">{draft.document.sections.map(item=><button key={item.id} className={item.id===section?.id?'active':''} onClick={()=>{setActive(item.id);setPreview('');setValid(true)}} disabled={!valid&&item.id!==section?.id}>{item.title}</button>)}</nav><p>保存使用 1000ms 空闲防抖；冲突需要逐项确认，不会自动覆盖。</p>{figures.length>0&&<section aria-label="本节图片"><h3>受控图片</h3>{figures.map(block=><button key={block.id} onClick={()=>setPreview(String(block.content.resource_id))}>{String(block.content.alt)}</button>)}{selectedFigure&&<ImagePreview current={current} documentId={value.id} resourceId={preview} alt={String(selectedFigure.content.alt)}/>}</section>}</div><div id="projectContextPanel" className="ai-body context-panel" hidden={!contextOpen}><ProjectContext current={current} document={confirmed} documentDirty={dirty} onPending={onContextPending} onReject={onReject} onRefresh={onRefresh}/></div></aside></div>{historyMode&&<VersionHistory current={current} documentId={value.id} base={confirmed} local={draft} mode={historyMode} onMerge={merge} blocked={!!unknown} onReconcile={reconcile} onClose={()=>setHistoryMode(null)} onProtected={error=>{if(error instanceof TemplateError&&error.failure==='authentication')onReject(error);else onRefresh()}}/>}{leaveOpen&&<div className="version-mask"><div role="dialog" aria-modal="true" aria-label="离开未保存草稿" className="version-dialog"><h2>本地草稿尚未保存</h2><p>离开将丢弃内存中的修改。可先保存，若保存失败仍留在此页。{contextPending?'项目上下文仍有未提交输入，请先在检查器保存或明确放弃。':''}{unknown?'原提交结果未知，离开不能撤销可能已在服务端完成的保存。':''}</p><button onClick={()=>setLeaveOpen(false)}>继续编辑</button><button disabled={saving||!!unknown||!valid||contextPending} onClick={()=>{void persist('explicit').then(ok=>{if(ok){setLeaveOpen(false);leave()}})}}>保存后离开</button><button disabled={saving} onClick={()=>{setLeaveOpen(false);leave()}}>{unknown?'放弃核对并离开（原提交结果未知）':'明确丢弃本地草稿并离开'}</button></div></div>}</>;
}
