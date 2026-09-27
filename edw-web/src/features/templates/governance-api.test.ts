import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {deprecateVersion,getCandidate,getOperation,getReferences,getVersion,listCandidates,publishCandidate,uploadCandidate} from './governance-api';
const auth=vi.hoisted(()=>({value:'memory-token'}));vi.mock('../../auth/oidc',()=>({token:()=>auth.value}));
const wid='00000000-0000-4000-8000-000000000001',actor='00000000-0000-4000-8000-000000000002',cid='00000000-0000-4000-8000-000000000003',fid='00000000-0000-4000-8000-000000000004',vid='00000000-0000-4000-8000-000000000005';
const current={workspace_id:wid,actor_id:actor,policy_epoch:[4,2,4],name:'项目',slug:'p',display_name:'管理员',department:'工程',roles:['template_admin'],clearance:1,operations:['template:publish']};
const section={id:'00000000-0000-4000-8000-000000000006',title:'概述',mandatory:true};
const manifest={schema_version:'1.0',name:'模板',description:'说明',category:'技术',document_type:'technical_solution',sections:[section],rules:{retrieval_profile_id:null,prompt_version_id:null,reviewer_rule_version_id:null,render_theme_version_id:null,approval_policy_version_id:null},assets:[]};
const preview={manifest,manifest_sha256:'a'.repeat(64),assets:[],formal_ready:false,formal_blockers:['未配置正式字体']};
const candidate={id:cid,template_id:fid,workspace_id:wid,version_label:'v2',scope:'project',classification:1,base_version_id:null,created_at:'2026-09-26T00:00:00Z',updated_at:'2026-09-26T00:00:00Z',state:'VALIDATED',error_code:null,attempt:1,development_only:true,published_version_id:null,head_version_id:null,preview};
const version={id:vid,template_id:fid,version_label:'v2',name:'模板',scope:'project',classification:1,structure:{sections:[{title:'概述'}]},status:'active',rule_refs:manifest,manifest_sha256:'a'.repeat(64),candidate_id:cid,published_at:'2026-09-26T00:00:00Z',published_by:actor,development_only:true};
const respond=(v:unknown,status=200)=>vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:v}),{status}));
beforeEach(()=>{auth.value='memory-token';vi.stubGlobal('fetch',vi.fn())});afterEach(()=>vi.unstubAllGlobals());
test('bounded upload sends scoped query and original idempotency key; never formal flags',async()=>{
 respond(candidate,201);const file=new File([new Uint8Array([0x50,0x4b])],'safe.zip',{type:'application/zip'});
 expect((await uploadCandidate(current,{version_label:'v2',scope:'project',classification:1},file,'original')).id).toBe(cid);
 const [url,init]=vi.mocked(fetch).mock.calls[0];expect(String(url)).toContain(`/workspaces/${wid}/template-governance/candidates?version_label=v2&scope=project&classification=1`);
 expect(init?.headers).toMatchObject({'Idempotency-Key':'original',Authorization:'Bearer memory-token','Content-Type':'application/zip'});expect(init?.body).toBe(file);
 await expect(uploadCandidate(current,{version_label:'v2',scope:'project',classification:1},new File([new Uint8Array(5*1024*1024+1)],'big.zip'),'original')).rejects.toMatchObject({failure:'validation'});
});
test('candidate and cursor must be in current workspace; no foreign response accepted',async()=>{
 respond({...candidate,workspace_id:actor});await expect(getCandidate(current,cid)).rejects.toMatchObject({failure:'invalid-response'});
 respond({items:[candidate],next_cursor:null});expect((await listCandidates(current)).items[0].preview?.manifest.sections[0]).toEqual(section);
 respond({items:[{...candidate,preview:{...preview,formal_ready:true}}],next_cursor:null});await expect(listCandidates(current)).rejects.toMatchObject({failure:'invalid-response'});
});
test('unknown operation lookup stays unresolved and a committed receipt is reauthorized',async()=>{
 respond({kind:'unresolved'});expect((await getOperation(current,'original')).kind).toBe('unresolved');
 respond({kind:'candidate',candidate});const result=await getOperation(current,'original');
 expect(result.kind).toBe('candidate');
 respond({kind:'candidate',candidate:{...candidate,workspace_id:actor}});
 await expect(getOperation(current,'original')).rejects.toMatchObject({failure:'invalid-response'});
});
test('publishing pins digest and explicitly confirms only development mode',async()=>{
 respond(version,201);expect((await publishCandidate(current,cid,'a'.repeat(64),'same-operation')).id).toBe(vid);
 const [,init]=vi.mocked(fetch).mock.calls[0];expect(init?.headers).toMatchObject({'Idempotency-Key':'same-operation'});
 expect(JSON.parse(String(init?.body))).toEqual({manifest_sha256:'a'.repeat(64),mode:'development',confirmed:true});
 respond({...version,candidate_id:fid},201);await expect(publishCandidate(current,cid,'a'.repeat(64),'same-operation')).rejects.toMatchObject({failure:'invalid-response'});
});
test('deprecate requires explicit reason; references include only authorized scope and exact version',async()=>{
 respond(version);expect((await getVersion(current,vid)).status).toBe('active');
 respond({...version,status:'deprecated'});expect((await deprecateVersion(current,vid,'不再使用','same-operation')).status).toBe('deprecated');
 expect(JSON.parse(String(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.body))).toEqual({reason:'不再使用',confirmed:true});
 respond({items:[{document_id:cid,name:'可见文档',template_version_id:vid}],next_cursor:null,scope:'currently_authorized_documents_only'});
 expect((await getReferences(current,vid)).items).toHaveLength(1);
 respond({items:[{document_id:cid,name:'其他版本',template_version_id:fid}],next_cursor:null,scope:'currently_authorized_documents_only'});
 await expect(getReferences(current,vid)).rejects.toMatchObject({failure:'invalid-response'});
});
test.each([[401,'authentication'],[403,'forbidden'],[404,'missing']])('protected HTTP %i never returns stale payload',async(status,failure)=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{code:'HIDDEN',message:'secret'}}),{status}));
 await expect(getCandidate(current,cid)).rejects.toMatchObject({failure});
});
test('network failure and HTTP timeout retain the original operation key',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{code:'REQUEST_TIMEOUT'}}),{status:408}));
 await expect(publishCandidate(current,cid,'a'.repeat(64),'same-operation')).rejects.toMatchObject({failure:'unavailable',status:408});
});
test('network failure is unknown, while explicit conflict is definitive',async()=>{
 vi.mocked(fetch).mockRejectedValue(new TypeError('network'));await expect(publishCandidate(current,cid,'a'.repeat(64),'same-operation')).rejects.toMatchObject({failure:'unavailable'});
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{code:'FORMAL_TEMPLATE_NOT_CONFIGURED'}}),{status:409}));
 await expect(publishCandidate(current,cid,'a'.repeat(64),'same-operation')).rejects.toMatchObject({failure:'conflict',status:409});
});
