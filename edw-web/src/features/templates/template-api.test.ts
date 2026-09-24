import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {createDocument,getDocument,getTemplateDetail,getTemplates,getTypeCatalog,TemplateError,validateCreate,type CreateDocument} from './template-api';

const auth=vi.hoisted(()=>({value:'memory-only'}));
vi.mock('../../auth/oidc',()=>({token:()=>auth.value}));
const workspace='00000000-0000-4000-8000-000000000001';
const actor='00000000-0000-4000-8000-000000000002';
const version='00000000-0000-4000-8000-000000000003';
const template='00000000-0000-4000-8000-000000000004';
const documentId='00000000-0000-4000-8000-000000000005';
const documentVersion='00000000-0000-4000-8000-000000000006';
const current={workspace_id:workspace,actor_id:actor,policy_epoch:[4,2,4],name:'项目',slug:'project',display_name:'作者',department:'工程部',roles:['author'],clearance:1,operations:['document:create']};
const card={template_id:template,version_id:version,name:'技术方案开发样例',description:'开发结构',scope:'project',category:'技术',document_type:'technical_solution',version_label:'v1',development_only:true,outline:['概述','实施']};
const detail={...card,structure:{sections:[{title:'概述'},{title:'实施'}]}};
const input:CreateDocument={name:'  新方案  ',document_type:'technical_solution',knowledge_scope:'project_only',template_version_id:version};
const doc={id:documentId,workspace_id:workspace,name:'新方案',document_type:'technical_solution',knowledge_scope:'project_only',template_version_id:version,version_id:documentVersion,base_version_id:null,content_hash:'a'.repeat(64),revision:1,ast:{schema_version:'1.0',document:{metadata:{title:'新方案',document_type:'technical_solution',knowledge_scope:'project_only',template_version_id:version},sections:[{id:'00000000-0000-4000-8000-000000000007',title:'概述',blocks:[]}],claims:[],citations:[],review_state:{status:'not_reviewed'}}},replayed:false};
const respond=(value:unknown,status=200)=>vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:value}),{status}));
beforeEach(()=>{auth.value='memory-only';vi.stubGlobal('fetch',vi.fn());vi.stubGlobal('navigator',{onLine:true})});
afterEach(()=>vi.unstubAllGlobals());

test('catalog exposes all 11 types and disables unconfigured knowledge scopes',async()=>{
 const ids=['technical_solution','bid','prd','test_plan','project_summary','technical_requirements','quality_outline','project_plan','functional_test_outline','performance_test_outline','production_form'];
 respond({types:ids.map(id=>({id,label:id,workflow_state:'catalog_only'})),knowledge_scopes:[{id:'project_only',label:'仅当前项目',available:true},{id:'project_enterprise_quality',label:'企业与质量库',available:false},{id:'all_authorized',label:'全部',available:false}]});
 const result=await getTypeCatalog(current);expect(result.types).toHaveLength(11);expect(result.knowledge_scopes.filter(x=>x.available).map(x=>x.id)).toEqual(['project_only']);
 expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/v1/workspaces/${workspace}/document-types`);
});
test('scope, query, category and type are sent as one AND filter and mismatched cards are rejected',async()=>{
 respond({items:[card]});const filters={scope:'project' as const,query:'方案',category:'技术',document_type:'technical_solution' as const};
 expect(await getTemplates(current,filters)).toEqual([card]);
 expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('scope=project&query=%E6%96%B9%E6%A1%88&category=%E6%8A%80%E6%9C%AF&document_type=technical_solution');
 respond({items:[{...card,scope:'enterprise'}]});await expect(getTemplates(current,filters)).rejects.toMatchObject({failure:'invalid-response'});
});
test('detail outline must belong to the requested version structure',async()=>{
 respond(detail);expect((await getTemplateDetail(current,version)).structure.sections.map(x=>x.title)).toEqual(card.outline);
 respond({...detail,structure:{sections:[{title:'别的结构'},{title:'实施'}]}});await expect(getTemplateDetail(current,version)).rejects.toMatchObject({failure:'invalid-response'});
});
test('create uses one idempotency key, normalized name and checks its own initial AST',async()=>{
 respond(doc,201);expect((await createDocument(current,input,'same-key')).id).toBe(documentId);
 const [url,options]=vi.mocked(fetch).mock.calls[0];expect(url).toBe(`/api/v1/workspaces/${workspace}/documents`);expect(options?.headers).toMatchObject({'Idempotency-Key':'same-key',Authorization:'Bearer memory-only'});expect(JSON.parse(String(options?.body))).toEqual({...input,name:'新方案'});
 respond({...doc,ast:{...doc.ast,document:{...doc.ast.document,metadata:{...doc.ast.document.metadata,title:'其他方案'}}}},201);
 await expect(createDocument(current,input,'same-key')).rejects.toMatchObject({failure:'invalid-response'});
});
test('document route checks the requested ID and workspace before returning AST',async()=>{
 respond(doc);expect((await getDocument(current,documentId)).ast.document.sections[0].title).toBe('概述');
 respond({...doc,workspace_id:actor});await expect(getDocument(current,documentId)).rejects.toMatchObject({failure:'invalid-response'});
});
test('document response requires bounded revision, lowercase digest and nullable UUID base version on both routes',async()=>{
 respond({...doc,revision:Number.MAX_SAFE_INTEGER,base_version_id:documentVersion});
 expect((await getDocument(current,documentId)).revision).toBe(Number.MAX_SAFE_INTEGER);
 const malformed=[
  {revision:0},{revision:Number.MAX_SAFE_INTEGER+1},{revision:1.5},
  {content_hash:'A'.repeat(64)},{content_hash:'a'.repeat(63)},{content_hash:undefined},
  {base_version_id:'invalid-uuid'},{base_version_id:undefined},
 ];
 for(const patch of malformed){
  respond({...doc,...patch});await expect(getDocument(current,documentId)).rejects.toMatchObject({failure:'invalid-response'});
  respond({...doc,...patch},201);await expect(createDocument(current,input,'same-key')).rejects.toMatchObject({failure:'invalid-response'});
 }
});
test('document name accepts 256 Unicode code points and rejects 257 before sending',()=>{
 expect(validateCreate({...input,name:'😀'.repeat(256)}).name).toBe('😀'.repeat(256));
 expect(()=>validateCreate({...input,name:'😀'.repeat(257)})).toThrow(TemplateError);
});
test.each([[401,'authentication'],[403,'forbidden'],[404,'missing'],[422,'validation']])('HTTP %s maps to safe %s failure',async(status,expected)=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{code:'SECRET',message:'protected title'}}),{status:Number(status)}));
 await expect(getTemplateDetail(current,version)).rejects.toMatchObject({failure:expected});
});
test.each([['TEMPLATE_DEPRECATED','deprecated'],['IDEMPOTENCY_KEY_REUSED','idempotency']])('409 %s remains distinct',async(code,expected)=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{code}}),{status:409}));
 await expect(createDocument(current,input,'same-key')).rejects.toMatchObject({failure:expected});
});
test('invalid create input is rejected before any network write',async()=>{
 await expect(createDocument(current,{...input,name:'   '},'same-key')).rejects.toBeInstanceOf(TemplateError);
 expect(fetch).not.toHaveBeenCalled();
});
test('invalid workspace policy context fails closed before reading protected AST',async()=>{
 await expect(getDocument({...current,policy_epoch:[5,2,4]},documentId)).rejects.toMatchObject({failure:'context'});
 expect(fetch).not.toHaveBeenCalled();
});
