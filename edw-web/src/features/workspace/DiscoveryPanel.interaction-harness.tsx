// Browser-only fixture bundled in memory by DiscoveryPanel.interaction.test.ts.
import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,useNavigate} from 'react-router-dom';
import DiscoveryPanel from './DiscoveryPanel';
import {DiscoveryError,type Command,type Context,type Detail,type Receipt,type Storage} from '../../app/discovery-api';
import type {WorkspaceAccess} from '../../app/access-api';

const wid='00000000-0000-4000-8000-000000000001';
const actor='00000000-0000-4000-8000-000000000002';
const rid='00000000-0000-4000-8000-000000000003';
const nextId='00000000-0000-4000-8000-000000000004';
const operationId='00000000-0000-4000-8000-000000000005';
const current:WorkspaceAccess={actor_id:actor,workspace_id:wid,policy_epoch:[4,2,4],name:'真实项目',slug:'actual-project',display_name:'当前作者',department:'工程部',roles:['author'],clearance:1,operations:['workspace:read','document:edit']};
const storage:Storage={metadata_bytes:0,measured_at:'2026-09-18T00:00:00Z',scope:'authorized_filtered_record_metadata',definition:'pg_column_size(discovery_record)+pg_column_size(access_resource.title)',visibility:'visible',attachment_bytes:null,quota_bytes:null};
function detail(context:Context):Detail{
 return {context,resource_context:{...context,policy_epoch:[context.policy_epoch[0],context.policy_epoch[1],8]},item:{id:rid,workspace_id:context.workspace_id,title:'当前授权文档',kind:'document',document_type:'technical',lifecycle:'DRAFT',visibility:'visible',created_by:actor,created_at:'2026-09-14T00:00:00Z',updated_at:'2026-09-18T02:00:00Z',version_label:null,revision:1,resource_epoch:8,favorite:false,favorite_revision:0,participating:true},actions:{favorite:true,restore:false,restore_policy_version:null},content_state:'metadata_only'};
}
type Outcome='success'|'failure';
type Change='actor'|'workspace'|'epoch'|'route'|'unmount';
type Call={command:Command;context:Context;signal?:AbortSignal;resolve:(receipt:Receipt)=>void;reject:(error:unknown)=>void};
const calls:Call[]=[];
const requests:{url:string;body:unknown}[]=[];
const cache=new QueryClient({defaultOptions:{queries:{retry:false}}});
const root=createRoot(document.getElementById('root')!);
let denied=false;
let refreshes=0;
let rejections=0;
let activeContext:WorkspaceAccess=current;
let change:(kind:Change)=>void=()=>{throw new Error('Not mounted')};

// The real list/search client still validates and serializes requests. This
// response stub never contacts HTTP or reads/persists an authentication token.
window.fetch=async(input,init)=>{
 const url=String(input);requests.push({url,body:init?.body?JSON.parse(String(init.body)):null});
 const visibility=url.includes('visibility=recycled')?'recycled':'visible';
 const context:Context={actor_id:activeContext.actor_id,workspace_id:activeContext.workspace_id,policy_epoch:activeContext.policy_epoch};
 return new Response(JSON.stringify({data:{items:[],total_count:0,next_cursor:null,context,storage:{...storage,visibility},...(url.endsWith('/search')?{functions:[]}: {})}}));
};

export default function Harness(){
 const [value,setValue]=useState(current);const navigate=useNavigate();
 activeContext=value;
 change=kind=>{
  if(kind==='unmount'){root.unmount();return}
  if(kind==='route'){navigate(`/workspaces/${value.workspace_id}/documents`);return}
  const next={...value,...(kind==='actor'?{actor_id:nextId}:kind==='workspace'?{workspace_id:nextId}:{policy_epoch:[5,2,5]})};
  setValue(next);if(kind==='workspace')navigate(`/workspaces/${nextId}/records/${rid}`);
 };
 return <DiscoveryPanel current={value} search={{query:'参考',sequence:1}} onReject={()=>{rejections++}} onRefresh={()=>{refreshes++}}/>;
}

const harness={
 mount(path=`/workspaces/${wid}/records/${rid}`){root.render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={[path]}><Harness/></MemoryRouter></QueryClientProvider>)},
 getDetail(context:Context){return denied?Promise.reject(new DiscoveryError('forbidden','当前目标不可访问，受保护内容已清除',403)):Promise.resolve(detail(context))},
 executeCommand(context:Context,command:Command,signal?:AbortSignal){
  // Deliberately ignore abort so late callbacks exercise the component guard.
  return new Promise<Receipt>((resolve,reject)=>calls.push({context,command,signal,resolve,reject}));
 },
 async denyDetail(){denied=true;await cache.invalidateQueries({queryKey:['discovery']})},
 allowDetail(){denied=false},
 change(kind:Change){change(kind)},
 settle(index:number,outcome:Outcome){
  const call=calls[index];if(!call)throw new Error('Missing command');
  if(outcome==='failure')call.reject(new DiscoveryError('unavailable','结果尚待确认'));
  else call.resolve({operation_id:operationId,action:call.command.action,resource_id:call.command.resourceId,replayed:index>0,occurred_at:'2026-09-18T00:00:00Z',context:call.context,current:detail(call.context).item});
 },
 snapshot(){return {calls:calls.map(call=>({command:call.command,context:call.context,aborted:call.signal?.aborted})),requests,refreshes,rejections}},
};
declare global{interface Window{discoveryTest:typeof harness}}
window.discoveryTest=harness;
