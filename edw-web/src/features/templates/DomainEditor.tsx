import {useEffect,useRef,useState} from 'react';
import {EditorContent,useEditor,type Editor} from '@tiptap/react';
import {StarterKit} from '@tiptap/starter-kit';
import {TableKit} from '@tiptap/extension-table';
import {TextAlign} from '@tiptap/extension-text-align';
import {TextStyleKit} from '@tiptap/extension-text-style';
import type {WorkspaceAccess} from '../../app/access-api';
import {getImage,saveDocument,uploadImage,TemplateError,type DocumentData} from './template-api';
import {DomainAtom,DomainHeading,DomainParagraph,DomainTable,domainToEditor,editorToDomain,type DomainAst,type DomainSection} from './domain-adapter';

const extensions=[StarterKit.configure({paragraph:false,heading:false,blockquote:false,codeBlock:false,horizontalRule:false,strike:false,code:false,link:{openOnClick:false,autolink:false}}),DomainParagraph,DomainHeading,DomainAtom,TableKit.configure({table:false}),DomainTable,TextAlign.configure({types:['paragraph','heading']}),TextStyleKit];
const uuid=()=>crypto.randomUUID();
function SectionCanvas({section,onChange,onEditor,onValidityChange}: {section:DomainSection;onChange:(value:DomainSection)=>void;onEditor:(editor:Editor|null)=>void;onValidityChange:(valid:boolean)=>void}){
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

export default function DomainEditor({current,value,onReject,onRefresh}: {current:WorkspaceAccess;value:DocumentData;onReject:(error:unknown)=>void;onRefresh:()=>void}){
 const [draft,setDraft]=useState<DomainAst>(()=>structuredClone(value.ast) as DomainAst);
 const draftRef=useRef(draft);draftRef.current=draft;
 const [base,setBase]=useState({version_id:value.version_id,revision:value.revision});
 const [dirty,setDirty]=useState(false);const [status,setStatus]=useState('已加载，尚未修改');const [saving,setSaving]=useState(false);const [valid,setValid]=useState(true);
 const serverVersion=useRef(value.version_id);
 const [active,setActive]=useState(value.ast.document.sections[0]?.id??'');const [editor,setEditor]=useState<Editor|null>(null);
 const [link,setLink]=useState('');const [preview,setPreview]=useState('');const fileInput=useRef<HTMLInputElement|null>(null);const controller=useRef<AbortController|null>(null);
 const section=draft.document.sections.find(item=>item.id===active)??draft.document.sections[0];
 const figures=section?.blocks.filter(block=>block.type==='figure'&&typeof block.content?.resource_id==='string')??[];
 const selectedFigure=figures.find(block=>block.content.resource_id===preview);
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{
  if(serverVersion.current===value.version_id)return;
  serverVersion.current=value.version_id;
  if(dirty){setStatus('服务端版本已变化，本地草稿未被替换；保存将检查版本冲突');return}
  const refreshed=structuredClone(value.ast) as DomainAst;draftRef.current=refreshed;setDraft(refreshed);
  setBase({version_id:value.version_id,revision:value.revision});setActive(refreshed.document.sections[0]?.id??'');setPreview('');setStatus('已重新读取最新版本');
 },[value.version_id,value.revision,value.ast,dirty]);
 const revise=(next:DomainAst)=>{draftRef.current=next;setDraft(next);setDirty(true);setStatus('尚未保存')};
 const updateSection=(next:DomainSection)=>revise({...draft,document:{...draft.document,sections:draft.document.sections.map(item=>item.id===next.id?next:item)}});
 const changeTitle=(title:string)=>revise({...draft,document:{...draft.document,metadata:{...draft.document.metadata,title}}});
 const persist=async()=>{
  if(!dirty||saving||!valid)return;
  const title=String(draft.document.metadata.title??'').trim();if(!title||title.length>256){setStatus('文档名称必须为 1–256 字符');return}
  const sourceSerialized=JSON.stringify(draft);
  const sent={...draft,document:{...draft.document,metadata:{...draft.document.metadata,title}}};
  const request=new AbortController();controller.current=request;setSaving(true);setStatus('正在保存…');
  try{
   const result=await saveDocument(current,value.id,{base_version_id:base.version_id,revision:base.revision,ast:sent},request.signal);
   if(request.signal.aborted)return;
   setBase({version_id:result.version_id,revision:result.revision});
   if(JSON.stringify(draftRef.current)===sourceSerialized){draftRef.current=result.ast as DomainAst;setDraft(result.ast as DomainAst);setDirty(false);setStatus(`已保存 · 版本 ${result.revision}`)}else{setDirty(true);setStatus('保存期间又有编辑，仍需再次保存')}
  }catch(error){
   if(request.signal.aborted)return;
   if(error instanceof TemplateError&&error.failure==='conflict')setStatus('版本冲突：本地草稿未覆盖服务端。请保留内容并重新核对。');
   else {setStatus(error instanceof Error?error.message:'保存失败，本地草稿尚未保存');if(error instanceof TemplateError&&error.failure==='authentication')onReject(error);else if(error instanceof TemplateError&&['forbidden','missing'].includes(error.failure))onRefresh()}
  }finally{setSaving(false)}
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
 return <div className="editor-layout" data-testid="domain-editor"><section className="editor-main"><div className="doc-top"><b>领域 AST 草稿</b><span>文档版本 {base.version_id}</span><span>修订 {base.revision}</span><span role="status">{status}</span><button className="btn primary" disabled={!dirty||saving||!valid} onClick={()=>void persist()}>保存</button></div>
  <div className="doc-toolbar" aria-label="结构化编辑工具栏">
   <button onClick={()=>editor?.chain().focus().undo().run()} disabled={!editor}>撤销</button><button onClick={()=>editor?.chain().focus().redo().run()} disabled={!editor}>重做</button>
   <button onClick={()=>editor?.chain().focus().toggleBold().run()} disabled={!editor}>粗体</button><button onClick={()=>editor?.chain().focus().toggleItalic().run()} disabled={!editor}>斜体</button><button onClick={()=>editor?.chain().focus().toggleUnderline().run()} disabled={!editor}>下划线</button>
   <button onClick={()=>editor?.chain().focus().toggleBulletList().run()} disabled={!editor}>项目列表</button><button onClick={()=>editor?.chain().focus().toggleOrderedList().run()} disabled={!editor}>编号列表</button>
   <button onClick={()=>editor?.chain().focus().setTextAlign('left').run()} disabled={!editor}>左对齐</button><button onClick={()=>editor?.chain().focus().setTextAlign('center').run()} disabled={!editor}>居中</button><button onClick={()=>editor?.chain().focus().setTextAlign('right').run()} disabled={!editor}>右对齐</button>
   <label>颜色<input aria-label="文字颜色" type="color" onChange={event=>editor?.chain().focus().setColor(event.target.value).run()} disabled={!editor}/></label>
   <input aria-label="链接地址" type="url" value={link} onChange={event=>setLink(event.target.value)} placeholder="https://…"/><button onClick={applyLink} disabled={!editor}>设置链接</button>
   <button onClick={()=>editor?.chain().focus().insertTable({rows:2,cols:2,withHeaderRow:false}).run()} disabled={!editor}>插入表格</button>
   <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" style={{display:'none'}} aria-label="选择图片" onChange={event=>{void insertImage(event.target.files?.[0]??null);event.target.value=''}}/><button onClick={()=>fileInput.current?.click()} disabled={!editor}>插入图片</button>
  </div>
  <div className="doc-scroll"><article className="paper" aria-label="结构化文档编辑画布"><label htmlFor="docTitle">文档标题</label><input id="docTitle" value={String(draft.document.metadata.title??'')} onChange={event=>changeTitle(event.target.value)} maxLength={256}/>{section&&<section key={section.id}><h2>{section.title}</h2><SectionCanvas section={section} onChange={updateSection} onEditor={setEditor} onValidityChange={setValid}/></section>}</article></div>
 </section><aside className="ai-side"><div className="ai-tabs"><button className="active" disabled>文档结构</button></div><div className="ai-body"><p>内容保存为领域 AST；未知未来节点只读保留。图像仅使用当前授权资源。</p><nav id="docTree" aria-label="文档章节">{draft.document.sections.map(item=><button key={item.id} className={item.id===section?.id?'active':''} onClick={()=>{setActive(item.id);setPreview('');setValid(true)}} disabled={!valid&&item.id!==section?.id}>{item.title}</button>)}</nav><p>并发冲突比较与自动保存将在 Story 2.3 开放。</p>{figures.length>0&&<section aria-label="本节图片"><h3>受控图片</h3>{figures.map(block=><button key={block.id} onClick={()=>setPreview(String(block.content.resource_id))}>{String(block.content.alt)}</button>)}{selectedFigure&&<ImagePreview current={current} documentId={value.id} resourceId={preview} alt={String(selectedFigure.content.alt)}/>}</section>}</div></aside></div>;
}
