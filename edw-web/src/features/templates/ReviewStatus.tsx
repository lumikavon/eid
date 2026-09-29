import {useEffect,useState} from 'react';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';
import type {WorkspaceAccess} from '../../app/access-api';
import type {DocumentData} from './template-api';

const categories=['structure','fact','requirement','technical','quality','consistency','style','safety'] as const;
const labels=['结构','事实','需求','技术','质量','一致性','风格','安全'];
type Run={id:string;state:string;current_eligible:boolean;error_code:string|null;results?:{category:string;state:string;execution_kind:string}[]};

export default function ReviewStatus({current,document}: {current:WorkspaceAccess;document:DocumentData}){
 const [run,setRun]=useState<Run|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const base=`/api/v1/workspaces/${current.workspace_id}/documents/${document.id}/reviews`;
 useEffect(()=>{let disposed=false;const controller=new AbortController();const load=async()=>{
  try{const access=token();if(!access)return;const response=await fetch(base,{signal:controller.signal,headers:{Authorization:`Bearer ${access}`}});
   if(!response.ok)throw new Error('审校状态不可访问');const body=await boundedJson(response,262144,'审校响应无效',controller.signal) as {data:{items:Run[]}};
   if(!disposed)setRun(body.data.items[0]??null);
  }catch{if(!disposed)setError('无法读取当前审校状态');}};
  void load();return()=>{disposed=true;controller.abort()};
  },[base,current.actor_id,current.policy_epoch.join(':'),document.version_id,document.revision]);
 useEffect(()=>{if(!run?.id||!['QUEUED','RUNNING'].includes(run.state))return;
  let disposed=false;const controller=new AbortController();const refresh=async()=>{try{const access=token();if(!access)return;
   const response=await fetch(`${base}/${run.id}`,{signal:controller.signal,headers:{Authorization:`Bearer ${access}`}});
   if(!response.ok)throw new Error('审校状态不可访问');const body=await boundedJson(response,262144,'审校响应无效',controller.signal) as {data:Run};
   if(!disposed)setRun(body.data);}catch{if(!disposed)setError('审校状态不可访问，请刷新权限')}};
  void refresh();const timer=setInterval(()=>void refresh(),3000);return()=>{disposed=true;clearInterval(timer);controller.abort()};
 },[base,run?.id,run?.state]);
 const start=async()=>{setBusy(true);setError('');try{const access=token();if(!access)throw new Error('请重新登录');
  const response=await fetch(base,{method:'POST',headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},body:JSON.stringify({request_key:crypto.randomUUID(),document_version_id:document.version_id,document_revision:document.revision})});
  if(!response.ok)throw new Error(response.status===403||response.status===404?'当前无审校权限':'无法发起审校，请核对版本');
  const body=await boundedJson(response,32768,'审校回执无效') as {data:Run};setRun(body.data);
 }catch(reason){setError(reason instanceof Error?reason.message:'审校请求未确认')}finally{setBusy(false)}};
  return <section className="template-state" aria-label="版本审校"><h2>版本审校</h2><p>当前版本 {document.revision} · {run?.current_eligible?'八类本地检查完成（不代表模型质量认证）':'八类本地检查未完成或已失效'}</p>
  {run&&<><p>运行状态：{run.state}{run.error_code?` · ${run.error_code}`:''}</p><ul>{categories.map((category,index)=><li key={category}>{labels[index]}：{run.results?.find(item=>item.category===category)?.state??'排队或尚未评估'}</li>)}</ul></>}
  {error&&<p role="alert">{error}</p>}<button className="btn" disabled={busy||!current.operations.includes('document:review')} onClick={()=>void start()}>{busy?'正在提交…':run?'重新审校':'开始审校'}</button>
 </section>;
}
