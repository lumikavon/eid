// Local browser fixture: real App and read clients, synthetic data, no OIDC navigation.
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {token} from '../auth/oidc';
import App from './App';

const workspaceId='00000000-0000-4000-8000-000000000001';
const actorId='00000000-0000-4000-8000-000000000002';
const context={actor_id:actorId,workspace_id:workspaceId,policy_epoch:[4,2,4]};
const account={actor_id:actorId,subject:'session-test-subject',display_name:'迟到回调测试作者',department:'测试部门',workspace_id:workspaceId,workspace_slug:'session-test-project',workspace_name:'迟到回调测试项目'};
const workspace={...context,name:account.workspace_name,slug:account.workspace_slug,display_name:account.display_name,department:account.department,roles:['author'],clearance:1,operations:['workspace:read']};
const item={id:'00000000-0000-4000-8000-000000000003',workspace_id:workspaceId,title:'退出后不可恢复的记录',kind:'document',document_type:'technical',lifecycle:'DRAFT',visibility:'visible',created_by:actorId,created_at:'2026-09-18T00:00:00Z',updated_at:'2026-09-18T00:00:00Z',version_label:null,revision:1,resource_epoch:4,favorite:false,favorite_revision:0,participating:false};
const storage={metadata_bytes:123,measured_at:'2026-09-18T00:00:00Z',scope:'authorized_filtered_record_metadata',definition:'pg_column_size(discovery_record)+pg_column_size(access_resource.title)',visibility:'visible',attachment_bytes:null,quota_bytes:null};
type Stage='account'|'workspace';
type Outcome='success'|'failure';
const requests:{path:string;bearer:string|null}[]=[];
const settled:{stage:Stage;outcome:Outcome}[]=[];
const unexpected:string[]=[];
let held:{stage:Stage;outcome:Outcome;requested:boolean;released:boolean;responseReturned:boolean}|null=null;
let release:()=>void=()=>{};
let gate:Promise<void>=Promise.resolve();
const cache=new QueryClient({defaultOptions:{queries:{retry:false}}});
const root=createRoot(document.getElementById('root')!);
const documentId=crypto.randomUUID();

// Never call native fetch. Deliberately ignore AbortSignal: a successful client
// read must actually finish after logout, so cancellation cannot mask a stale callback.
window.fetch=async(input,init={})=>{
 const path=new URL(String(input),window.location.origin).pathname;
 requests.push({path,bearer:new Headers(init.headers).get('Authorization')});
 const stage=path==='/api/v1/me'?'account':path===`/api/v1/access/workspaces/${workspaceId}`?'workspace':null;
 const pending=held?.stage===stage&&!held.requested?held:null;
 if(pending){pending.requested=true;await gate;pending.responseReturned=true}
 if(pending?.outcome==='failure')return new Response(JSON.stringify({error:{message:'delayed account failure'}}),{status:503});
 let body:unknown;
 if(stage==='account')body={data:account};
 else if(stage==='workspace')body={data:workspace};
 else if(path==='/health/ready')body={status:'ready',checks:Object.fromEntries(['postgres','redis','rabbitmq','s3','keycloak','worker'].map(name=>[name,'ready']))};
 else if(path===`/api/v1/workspaces/${workspaceId}/discovery`)body={data:{items:[item],total_count:1,next_cursor:null,context,storage}};
 else{unexpected.push(path);throw new Error(`Unexpected local request: ${path}`)}
 return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
};

const harness={
 mount(){root.render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={[`/workspaces/${workspaceId}/documents`]}><App/></MemoryRouter></QueryClientProvider>)},
 arm(stage:Stage,outcome:Outcome){held={stage,outcome,requested:false,released:false,responseReturned:false};gate=new Promise<void>(resolve=>{release=resolve})},
 release(){if(held)held.released=true;release()},
 observeRead(stage:Stage,outcome:Outcome){settled.push({stage,outcome})},
 async flushCallbacks(){await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())))},
 snapshot(){return {documentId,hasToken:Boolean(token()),held:held?{...held}:null,requests:[...requests],settled:[...settled],unexpected:[...unexpected],controlledQueries:cache.getQueryCache().findAll().filter(query=>['access','discovery'].includes(String(query.queryKey[0]))).length}},
};
declare global{interface Window{appSessionTest:typeof harness}}
window.appSessionTest=harness;
