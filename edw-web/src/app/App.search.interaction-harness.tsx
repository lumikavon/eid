// Browser-only fixture bundled in memory by App.search.interaction.test.ts.
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import App from './App';

const workspaceId='00000000-0000-4000-8000-000000000001';
const actorId='00000000-0000-4000-8000-000000000002';
let context={actor_id:actorId,workspace_id:workspaceId,policy_epoch:[4,2,4]};
const storage={metadata_bytes:0,measured_at:'2026-09-18T00:00:00Z',scope:'authorized_filtered_record_metadata',definition:'pg_column_size(discovery_record)+pg_column_size(access_resource.title)',visibility:'visible',attachment_bytes:null,quota_bytes:null};
const requests:{url:string;method:string;body:unknown}[]=[];
const root=createRoot(document.getElementById('root')!);

// The real discovery client validates and serializes this response. Every
// browser fetch is retained in memory; the surrounding test aborts all routes.
window.fetch=async(input,init={})=>{
 const url=String(input);const method=init.method??'GET';const body=init.body===undefined?null:JSON.parse(String(init.body));
 requests.push({url,method,body});
 return new Response(JSON.stringify({data:{items:[],total_count:0,next_cursor:null,context,storage, ...(url.endsWith('/search')?{functions:[]}:{})}}),{status:200,headers:{'Content-Type':'application/json'}});
};

const harness={
 mount(path=`/workspaces/${workspaceId}/documents`){
  root.render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>);
 },
 snapshot(){return {requests:[...requests]};},
 context(){return {...context,policy_epoch:[...context.policy_epoch]};},
 advanceContext(){context={...context,policy_epoch:[5,2,5]};},
};
declare global{interface Window{appSearchTest:typeof harness}}
window.appSearchTest=harness;
