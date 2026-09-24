// Browser fixture is bundled in memory by TemplateWorkspace.interaction.test.ts.
import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter,useLocation} from 'react-router-dom';
import TemplateWorkspace from './TemplateWorkspace';
import type {WorkspaceAccess} from '../../app/access-api';

const wid='00000000-0000-4000-8000-000000000001';
const actor='00000000-0000-4000-8000-000000000002';
const templateId='00000000-0000-4000-8000-000000000003';
const versionId='00000000-0000-4000-8000-000000000004';
const documentId='00000000-0000-4000-8000-000000000005';
const documentVersionId='00000000-0000-4000-8000-000000000006';
const sectionId='00000000-0000-4000-8000-000000000007';
const current:WorkspaceAccess={actor_id:actor,workspace_id:wid,policy_epoch:[4,2,4],name:'真实项目',slug:'actual-project',display_name:'当前作者',department:'工程部',roles:['author'],clearance:1,operations:['document:create']};
const typeIds=['technical_solution','bid','prd','test_plan','project_summary','technical_requirements','quality_outline','project_plan','functional_test_outline','performance_test_outline','production_form'];
const catalog={types:typeIds.map(id=>({id,label:id,workflow_state:'catalog_only'})),knowledge_scopes:[{id:'project_only',label:'仅当前项目',available:true},{id:'project_enterprise_quality',label:'企业与质量库',available:false},{id:'all_authorized',label:'全部',available:false}]};
const card={template_id:templateId,version_id:versionId,name:'项目技术方案',description:'受控开发样例',scope:'project',category:'方案',document_type:'technical_solution',version_label:'v1',development_only:true,outline:['项目概述','实施计划']};
type CreateCall={key:string;body:Record<string,unknown>;signal?:AbortSignal;resolve:(value:Response)=>void};
const calls:CreateCall[]=[];
const cache=new QueryClient({defaultOptions:{queries:{retry:false}}});
const root=createRoot(document.getElementById('root')!);
let routePath='';let refreshes=0;let rejections=0;let denyWorkspaceOnRefresh=false;
const response=(value:unknown,status=200)=>new Response(JSON.stringify({data:value}),{status,headers:{'Content-Type':'application/json'}});

// All HTTP responses are in memory; POST is deliberately deferred to inspect the live form.
window.fetch=async(input,init)=>{
 const url=new URL(String(input),'https://templates.invalid');
 if(init?.method==='POST'&&url.pathname===`/api/v1/workspaces/${wid}/documents`){
  return new Promise<Response>(resolve=>calls.push({key:new Headers(init.headers).get('Idempotency-Key')??'',body:JSON.parse(String(init.body)) as Record<string,unknown>,signal:init.signal??undefined,resolve}));
 }
 if(url.pathname.endsWith('/document-types'))return response(catalog);
 if(url.pathname.endsWith('/templates')){
  const type=url.searchParams.get('document_type');
  const scope=url.searchParams.get('scope');
  const category=url.searchParams.get('category');
  const query=url.searchParams.get('query');
  return response({items:(!type||type===card.document_type)&&(!scope||scope===card.scope)&&(!category||category===card.category)&&(!query||card.name.includes(query)||card.description.includes(query))?[card]:[]});
 }
 if(url.pathname.endsWith(`/templates/${versionId}`))return response({...card,structure:{sections:card.outline.map(title=>({title}))}});
 throw new Error(`Unexpected fixture request: ${url.pathname}`);
};

export default function Harness(){
 const location=useLocation();const [workspace,setWorkspace]=useState<WorkspaceAccess|null>(current);
 routePath=location.pathname;
 return workspace?<TemplateWorkspace key={`${workspace.actor_id}:${workspace.workspace_id}:${workspace.policy_epoch.join(':')}`} current={workspace} onReject={()=>{rejections++}} onRefresh={()=>{refreshes++;if(denyWorkspaceOnRefresh)setWorkspace(null)}}/>:<p role="alert">工作区访问被拒绝</p>;
}
const harness={
 mount(quick=false){root.render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={[{pathname:`/workspaces/${wid}/templates`,state:quick?{createType:'technical_solution'}:null}]}><Harness/></MemoryRouter></QueryClientProvider>)},
 denyWorkspaceOnRefresh(){denyWorkspaceOnRefresh=true},
 settle(index:number,status:201|401|403|404|503){
  const call=calls[index];if(!call)throw new Error('Missing create request');
  if(status!==201){call.resolve(new Response(JSON.stringify({error:{code:'SAFE_REJECTION',message:'secret server detail'}}),{status}));return}
  const body=call.body;
  call.resolve(response({id:documentId,workspace_id:wid,name:body.name,document_type:body.document_type,knowledge_scope:body.knowledge_scope,template_version_id:body.template_version_id,version_id:documentVersionId,base_version_id:null,content_hash:'a'.repeat(64),revision:1,replayed:index>0,ast:{schema_version:'1.0',document:{metadata:{title:body.name,document_type:body.document_type,knowledge_scope:body.knowledge_scope,template_version_id:body.template_version_id},sections:[{id:sectionId,title:'项目概述',blocks:[]}],claims:[],citations:[],review_state:{status:'not_reviewed'}}}},201));
 },
 snapshot(){return {calls:calls.map(call=>({key:call.key,body:call.body,aborted:call.signal?.aborted})),routePath,refreshes,rejections,queryCount:cache.getQueryCache().findAll({queryKey:['template-detail']}).length}},
};
declare global{interface Window{templateTest:typeof harness}}
window.templateTest=harness;
