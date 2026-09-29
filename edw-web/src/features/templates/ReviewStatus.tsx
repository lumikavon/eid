import {useEffect,useState} from 'react';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import type {WorkspaceAccess} from '../../app/access-api';
import type {DocumentData} from './template-api';

const categories=['structure','fact','requirement','technical','quality','consistency','style','safety'] as const;
const labels=['结构','事实','需求','技术','质量','一致性','风格','安全'];
type Issue={id:string;category:string;rule_id:string;severity:string;status:string;section_id:string|null;section_title:string|null;block_id:string|null;block_type:string|null;claim_id:string|null;source_id:string|null;quote:string;impact:string;suggestion:string;source_state:string;trace:{source_id:string;version:string;locator:string;quoted_text:string}[]};
type Run={id:string;state:string;document_version_id:string;document_revision:number;current_eligible:boolean;error_code:string|null;results?:{category:string;state:string;execution_kind:string}[];issues?:Issue[];issue_count?:number;returned_count?:number;offset?:number;page_size?:number;source_state?:string;sections?:{id:string;title:string}[];metrics?:{score:{state:string};coverage:{state:string}};version?:{id:string;revision:number;current_id:string;current_revision:number;comparison:{added_blocks:number;removed_blocks:number;changed_blocks:number}}};
type Filters={severity:string;section_id:string;status:string;keyword:string};
const initial:Filters={severity:'',section_id:'',status:'',keyword:''};
const tabs=['结果','追溯','版本比较','历史'] as const;

export default function ReviewStatus({current,document}: {current:WorkspaceAccess;document:DocumentData}){
 const [runs,setRuns]=useState<Run[]>([]);const [runId,setRunId]=useState('');const [run,setRun]=useState<Run|null>(null);
 const [filters,setFilters]=useState<Filters>(initial);const [selected,setSelected]=useState('');const [tab,setTab]=useState<(typeof tabs)[number]>('结果');
 const [offset,setOffset]=useState(0);
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const base=`/api/v1/workspaces/${current.workspace_id}/documents/${document.id}/reviews`;
 const scope=[base,current.actor_id,...current.policy_epoch,document.version_id,document.revision].join(':');
 const query=new URLSearchParams(Object.entries(filters).filter(([,value])=>value));
 query.set('offset',String(offset));const filterKey=query.toString();
 useEffect(()=>{let disposed=false;const controller=new AbortController();setRuns([]);setRunId('');setRun(null);setSelected('');setFilters(initial);setOffset(0);
  const load=async()=>{try{const access=token();if(!access)throw new Error();const response=await fetch(base,{signal:controller.signal,headers:{Authorization:`Bearer ${access}`}});
   if(!response.ok)throw new Error();const body=await boundedJson(response,262144,'审校响应无效',controller.signal) as {data:{items:Run[]}};
   if(!disposed){setRuns(body.data.items);setRunId(body.data.items[0]?.id??'');setError('')}}catch{if(!disposed){setRun(null);setError('无法读取当前授权审校历史')}}};
  void load();return()=>{disposed=true;controller.abort()};
 },[scope]);
 useEffect(()=>{setSelected('');setRun(null);if(!runId)return;
  let disposed=false;const controller=new AbortController();let timer:ReturnType<typeof setInterval>|undefined;
  const refresh=async()=>{try{const access=token();if(!access)throw new Error();const response=await fetch(`${base}/${runId}?${filterKey}`,{signal:controller.signal,headers:{Authorization:`Bearer ${access}`}});
   if(!response.ok)throw new Error();const body=await boundedJson(response,1048576,'审校响应无效',controller.signal) as {data:Run};
   if(!disposed){setRun(body.data);setError('');if(['QUEUED','RUNNING'].includes(body.data.state)&&!timer)timer=setInterval(()=>void refresh(),3000);else if(!['QUEUED','RUNNING'].includes(body.data.state)&&timer){clearInterval(timer);timer=undefined}}}
   catch{if(!disposed){setRun(null);setSelected('');setError('审校结果不可访问；请刷新当前权限')}}};
  void refresh();return()=>{disposed=true;controller.abort();if(timer)clearInterval(timer)};
 },[scope,runId,filterKey]);
 const change=(patch:Partial<Filters>)=>{setSelected('');setOffset(0);setFilters(old=>({...old,...patch}))};
 const chooseTab=(value:(typeof tabs)[number])=>{setTab(value);setSelected('')};
 const issues=run?.id===runId?run.issues??[]:[];
 const issue=issues.find(item=>item.id===selected);
 const sections=run?.sections??[];
 const start=async()=>{setBusy(true);setError('');try{const access=token();if(!access)throw new Error('请重新登录');
  const response=await fetch(base,{method:'POST',headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},body:JSON.stringify({request_key:crypto.randomUUID(),document_version_id:document.version_id,document_revision:document.revision})});
  if(!response.ok)throw new Error(response.status===403||response.status===404?'当前无审校权限':'无法发起审校，请核对版本');
  const body=await boundedJson(response,32768,'审校回执无效') as {data:Run};setRuns(old=>[body.data,...old.filter(item=>item.id!==body.data.id)]);setSelected('');setFilters(initial);setOffset(0);setRunId(body.data.id);
 }catch(reason){setError(reason instanceof Error?reason.message:'审校请求未确认')}finally{setBusy(false)}};
 return <section className="template-state review-inspection" aria-label="版本审校"><h2>版本审校</h2>
  <p>当前文档版本 {document.revision} · 审校完成不代表批准或发布</p>
  <button className="btn" disabled={busy||!current.operations.includes('document:review')} onClick={()=>void start()}>{busy?'正在提交…':'重新审校当前版本'}</button>
  {error&&<p role="alert">{error}</p>}
  <label>选择审校运行<select value={runId} onChange={event=>{setSelected('');setOffset(0);setRunId(event.target.value)}}><option value="">无审校运行</option>{runs.map(item=><option key={item.id} value={item.id}>版本 {item.document_revision} · {item.state} · {item.id}</option>)}</select></label>
  <div className="seg-tabs" role="tablist" aria-label="审校视图">{tabs.map(value=><button key={value} role="tab" aria-selected={tab===value} onClick={()=>chooseTab(value)}>{value}</button>)}</div>
  {!runId?<p>尚无审校运行。请先审校当前版本。</p>:!run?<p role="status">正在读取选定运行或当前访问已失效…</p>:<>
   <p>运行 {run.id} · 固定版本 {run.document_revision} · {run.state} {run.error_code??''} · {run.current_eligible?'当前可用':'历史或未完成，不可证明当前版本已审校'}</p>
   {run.source_state==='denied'&&<p role="alert">来源失权或待复核；受保护引文与追溯已隐藏。</p>}
   {tab==='结果'&&<><ul>{categories.map((category,index)=><li key={category}>{labels[index]}：{run.results?.find(item=>item.category===category)?.state??'未评估'}</li>)}</ul>
    <div className="review-filters"><label>严重级别<select value={filters.severity} onChange={event=>change({severity:event.target.value})}><option value="">全部</option>{['critical','high','medium','low'].map(value=><option key={value}>{value}</option>)}</select></label>
     <label>章节<select value={filters.section_id} onChange={event=>change({section_id:event.target.value})}><option value="">全部</option>{sections.map(section=><option key={section.id} value={section.id}>{section.title}</option>)}</select></label>
     <label>状态<select value={filters.status} onChange={event=>change({status:event.target.value})}><option value="">全部</option><option value="OPEN">未处理</option></select></label>
     <label>关键词<input value={filters.keyword} maxLength={128} onChange={event=>change({keyword:event.target.value})}/></label></div>
    <p>匹配问题 {run.issue_count??0} 条 · 当前显示 {Math.min(offset+1,run.issue_count??0)}–{offset+(run.returned_count??0)} · 质量评分：未评估（无定义分子/分母） · 覆盖率：未评估（无定义分子/分母）</p>
    {(run.issue_count??0)>100&&<div><button disabled={offset===0} onClick={()=>{setSelected('');setOffset(Math.max(0,offset-100))}}>上一页</button><button disabled={offset+100>=(run.issue_count??0)} onClick={()=>{setSelected('');setOffset(offset+100)}}>下一页</button></div>}
    {issues.length===0?<p>当前组合筛选无匹配问题。</p>:<div className="review-columns"><div className="review-issues">{issues.map(item=><button className="issue" key={item.id} onClick={()=>setSelected(item.id)} aria-pressed={selected===item.id}>{item.severity} · {item.section_title??'全篇'} · {item.rule_id} · {item.id}</button>)}</div>
     <aside className="detail-panel" aria-label="问题详情">{issue?<><h3>{issue.rule_id} · {issue.severity}</h3><p>ID：{issue.id} · 状态：{issue.status}</p><p>位置：{issue.section_title??'全篇'} / {issue.section_id??'—'} / {issue.block_id??'—'} · Claim：{issue.claim_id??'—'}</p><p>引文：{issue.quote}</p><p>影响：{issue.impact}</p><p>建议：{issue.suggestion}</p><p>来源：{issue.source_id??'无当前授权来源'} · {issue.source_state}</p>{issue.trace.map((link,index)=><p key={index}>追溯：{link.source_id} · {link.version} · {link.locator} · {link.quoted_text}</p>)}</>:<p>选择问题查看当前筛选集合的详情。</p>}</aside></div>}</>}
   {tab==='追溯'&&<><h3>来源追溯</h3>{run.source_state==='denied'?<p>当前来源不可访问，历史引文不能用作授权。</p>:issues.some(item=>item.trace.length)?issues.flatMap(item=>item.trace.map((link,index)=><p key={`${item.id}:${index}`}>{item.id} → {link.source_id} · {link.version} · {link.locator} · {link.quoted_text}</p>)):<p>选定运行没有可展示的授权来源追溯。</p>}</>}
   {tab==='版本比较'&&<><h3>版本比较</h3><p>审校固定版本 {run.version?.revision}（{run.version?.id}）→ 当前版本 {run.version?.current_revision}（{run.version?.current_id}）</p><p>区块新增 {run.version?.comparison.added_blocks??0} · 删除 {run.version?.comparison.removed_blocks??0} · 变化 {run.version?.comparison.changed_blocks??0}</p><p>{run.current_eligible?'版本与当前权限一致':'历史运行不可证明当前版本；需要重新审校。'}</p></>}
   {tab==='历史'&&<><h3>审校历史</h3>{runs.map(item=><button key={item.id} className="issue" onClick={()=>{setSelected('');setOffset(0);setRunId(item.id);setTab('结果')}}>版本 {item.document_revision} · {item.state} · {item.id}</button>)}</>}
  </>}
 </section>;
}
