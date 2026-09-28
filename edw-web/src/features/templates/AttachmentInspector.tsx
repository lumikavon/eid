import {useEffect,useRef,useState} from 'react';
import type {WorkspaceAccess} from '../../app/access-api';
import {TemplateError,type DocumentData} from './template-api';
import {listAttachments,uploadAttachment,inspectAttachment,type Attachment,type AttachmentDetail} from './attachment-api';

const labels:Record<Attachment['state'],string>={QUEUED:'隔离待解析',RUNNING:'隔离解析中',PARTIAL:'部分完成',SUCCEEDED:'解析完成（未经人工核实）',FAILED:'解析失败',BLOCKED:'授权失效'};
export default function AttachmentInspector({current,document,onReject}:{current:WorkspaceAccess;document:DocumentData;onReject:(error:unknown)=>void}){
 const scope=`${current.actor_id}:${current.workspace_id}:${current.policy_epoch.join(':')}:${document.id}`;
 const live=useRef(scope);live.current=scope;
 const [items,setItems]=useState<Attachment[]>([]);const [detail,setDetail]=useState<AttachmentDetail|null>(null);
 const [file,setFile]=useState<File|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const abort=useRef<AbortController|null>(null);
 useEffect(()=>{setItems([]);setDetail(null);setFile(null);setError('');abort.current?.abort();return()=>abort.current?.abort()},[scope]);
 useEffect(()=>{const clear=()=>setDetail(null);const timer=window.setInterval(clear,15000);
  window.addEventListener('blur',clear);globalThis.document.addEventListener('visibilitychange',clear);
  return()=>{window.clearInterval(timer);window.removeEventListener('blur',clear);globalThis.document.removeEventListener('visibilitychange',clear)};
 },[scope]);
 const denied=(problem:unknown)=>{setDetail(null);if(problem instanceof TemplateError&&['authentication','forbidden','missing'].includes(problem.failure)){setItems([]);setFile(null);onReject(problem)}};
 const refresh=async()=>{const key=scope;abort.current?.abort();const controller=new AbortController();abort.current=controller;setDetail(null);setBusy(true);setError('');
  try{const rows=await listAttachments(current,document.id,controller.signal);if(live.current===key&&!controller.signal.aborted)setItems(rows)}
  catch(problem){if(live.current===key&&!controller.signal.aborted){denied(problem);setError('附件列表不可读取；请核对当前权限')}}finally{if(live.current===key)setBusy(false)}
 };
 const upload=async()=>{if(!file||busy)return;const key=scope;const controller=new AbortController();abort.current=controller;setBusy(true);setError('');setDetail(null);
  try{await uploadAttachment(current,document.id,file,controller.signal);if(live.current===key){setFile(null);setItems(await listAttachments(current,document.id,controller.signal))}}
  catch(problem){if(live.current===key){denied(problem);setError('上传未确认；请刷新列表核对，勿盲目重复上传')}}finally{if(live.current===key)setBusy(false)}
 };
 const inspect=async(id:string)=>{const key=scope;setDetail(null);setBusy(true);setError('');
  try{const result=await inspectAttachment(current,document.id,id);if(live.current===key)setDetail(result)}
  catch(problem){if(live.current===key){denied(problem);setError('来源不可读取；内容已清除')}}finally{if(live.current===key)setBusy(false)}
 };
 return <section aria-label="X-15 附件隔离解析" className="project-context"><h3>附件 · 隔离解析</h3><p>仅接受 PDF、DOCX、XLSX、PNG、JPEG（最大 10 MB）；解析内容不代表已核实证据。</p>
  <label>选择附件<input type="file" accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,image/png,image/jpeg" onChange={event=>{setFile(event.target.files?.[0]??null);setDetail(null)}}/></label>
  <button className="btn" disabled={busy||!file} onClick={()=>void upload()}>隔离上传</button><button className="btn" disabled={busy} onClick={()=>void refresh()}>刷新逐页状态</button>
  {busy&&<p role="status">正在核对当前授权…</p>}{error&&<p role="alert">{error}</p>}
  {items.map(item=><p key={item.id}><button className="btn" disabled={busy} onClick={()=>void inspect(item.id)}>{item.kind.toUpperCase()} · {item.id.slice(0,8)}</button> {labels[item.state]}{item.error_code?' · 无安全解析结果':''}</p>)}
  {detail&&<section aria-label="受权来源详情"><h4>附件 {detail.id.slice(0,8)} · {labels[detail.state]}</h4><p>SHA-256：{detail.sha256} · 解析器：{detail.parser_version}</p>
   {detail.pages.map(page=><div key={page.page_number}><h5>页/章节 {page.page_number} · {page.section||'未标记'} · {page.state==='FAILED'?'失败':page.state==='OCR'?'OCR':'已解析'}</h5>
    {page.state==='FAILED'&&<p>本页没有可用片段：{page.error_code}</p>}
    {detail.chunks.filter(chunk=>chunk.page_number===page.page_number).map(chunk=><p key={chunk.ordinal}><small>{chunk.locator} · {chunk.content_hash.slice(0,12)}</small><br/>{chunk.content}</p>)}</div>)}
  </section>}
 </section>;
}
