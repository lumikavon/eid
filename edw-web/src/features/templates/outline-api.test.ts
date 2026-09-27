import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {
 confirmOutline,getOutline,getOutlineVersion,getOutlineVersions,
 saveOutline,validateOutline,
} from './outline-api';

const auth=vi.hoisted(()=>({value:'memory-only'}));
vi.mock('../../auth/oidc',()=>({token:()=>auth.value}));

const workspace='00000000-0000-4000-8000-000000000001';
const actor='00000000-0000-4000-8000-000000000002';
const documentId='00000000-0000-4000-8000-000000000003';
const documentVersion='00000000-0000-4000-8000-000000000004';
const contextVersion='00000000-0000-4000-8000-000000000005';
const templateVersion='00000000-0000-4000-8000-000000000006';
const outlineVersion='00000000-0000-4000-8000-000000000007';
const sectionId='00000000-0000-4000-8000-000000000008';
const requiredId='00000000-0000-4000-8000-000000000009';
const current={workspace_id:workspace,actor_id:actor,policy_epoch:[4,2,4],name:'项目',slug:'project',display_name:'作者',department:'工程部',roles:['author'],clearance:1,operations:['document:edit']};
const required={id:requiredId,title:'概述',mandatory:true};
const snapshot={sections:[{id:sectionId,title:'概述',template_section_id:requiredId}]};
const pending={version_id:outlineVersion,revision:1,base_version_id:null,document_version_id:documentVersion,
 document_revision:1,context_version_id:contextVersion,template_version_id:templateVersion,
 development_only:true,template_sections:[required],required_sections:[required],snapshot,
 content_hash:'a'.repeat(64),created_by:actor,created_at:'2026-09-27T12:00:00Z',
 confirmed_by:null,confirmed_at:null,state:'OUTLINE_PENDING',
 reasons:[{code:'HUMAN_CONFIRMATION_REQUIRED',path:'confirmation'}]};
const ready={...pending,confirmed_by:actor,confirmed_at:'2026-09-27T12:01:00Z',state:'OUTLINE_READY',reasons:[]};
const command={base_outline_version_id:null,outline_revision:0,document_version_id:documentVersion,
 document_revision:1,context_version_id:contextVersion,template_version_id:templateVersion,snapshot};
const confirm={version_id:outlineVersion,document_version_id:documentVersion,document_revision:1,
 context_version_id:contextVersion,template_version_id:templateVersion};
const respond=(value:unknown,status=200)=>vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:value}),{status}));
const refuse=(status:number,code:string,details?:unknown)=>vi.mocked(fetch).mockResolvedValue(
 new Response(JSON.stringify({error:{code,message:'private server text',details}}),{status}));

beforeEach(()=>{auth.value='memory-only';vi.stubGlobal('fetch',vi.fn())});
afterEach(()=>vi.unstubAllGlobals());

test('response contract accepts exact human confirmation and rejects fabricated readiness',()=>{
 expect(validateOutline(pending).state).toBe('OUTLINE_PENDING');
 expect(validateOutline(ready).state).toBe('OUTLINE_READY');
 expect(()=>validateOutline({...pending,state:'OUTLINE_READY',reasons:[]})).toThrow();
 expect(()=>validateOutline({...ready,confirmed_by:null})).toThrow();
 expect(()=>validateOutline({...ready,required_sections:[{...required,id:actor}]})).toThrow();
 expect(()=>validateOutline({...ready,snapshot:{sections:[{...snapshot.sections[0],template_section_id:null}]}})).toThrow();
});

test('scoped reads use bearer token, no body, and reject malformed protected response',async()=>{
 respond(pending);
 expect((await getOutline(current,documentId)).version_id).toBe(outlineVersion);
 const [path,options]=vi.mocked(fetch).mock.calls[0];
 expect(path).toBe(`/api/v1/workspaces/${workspace}/documents/${documentId}/outline`);
 expect(options?.headers).toMatchObject({Authorization:'Bearer memory-only'});
 expect(options?.method).toBe('GET');expect(options?.body).toBeUndefined();
 respond({...pending,document_version_id:'foreign-document'});
 await expect(getOutline(current,documentId)).rejects.toMatchObject({failure:'invalid-response'});
});

test('eligibility state and immutable version history stay scoped to this document',async()=>{
 respond(pending);
 expect((await getOutline(current,documentId)).state).toBe('OUTLINE_PENDING');
 expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain(`/documents/${documentId}/outline`);
 respond({items:[{version_id:outlineVersion,revision:1,document_version_id:documentVersion,
  context_version_id:contextVersion,template_version_id:templateVersion,
  created_by:actor,created_at:pending.created_at,confirmed_by:null,confirmed_at:null}],more:false});
 expect((await getOutlineVersions(current,documentId)).items).toHaveLength(1);
 expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain('/outline/versions');
 respond({...ready,state:'OUTLINE_PENDING',reasons:[{code:'OUTLINE_SUPERSEDED',path:'version_id'}]});
 expect((await getOutlineVersion(current,documentId,outlineVersion)).state).toBe('OUTLINE_PENDING');
 expect(String(vi.mocked(fetch).mock.calls.at(-1)?.[0])).toContain(`/outline/versions/${outlineVersion}`);
});

test('save sends full CAS and confirmation names the exact saved prerequisite versions',async()=>{
 respond({...pending,version_id:outlineVersion,revision:1});
 expect((await saveOutline(current,documentId,command)).state).toBe('OUTLINE_PENDING');
 const [savePath,saveOptions]=vi.mocked(fetch).mock.calls[0];
 expect(savePath).toBe(`/api/v1/workspaces/${workspace}/documents/${documentId}/outline`);
 expect(saveOptions?.method).toBe('PUT');
 expect(saveOptions?.headers).toMatchObject({Authorization:'Bearer memory-only'});
 expect(JSON.parse(String(saveOptions?.body))).toEqual(command);
 expect(saveOptions?.headers).not.toHaveProperty('Idempotency-Key');
 respond(ready);
 expect((await confirmOutline(current,documentId,confirm)).state).toBe('OUTLINE_READY');
 const [confirmPath,confirmOptions]=vi.mocked(fetch).mock.calls[1];
 expect(confirmPath).toBe(`/api/v1/workspaces/${workspace}/documents/${documentId}/outline/confirm`);
 expect(confirmOptions?.method).toBe('POST');
 expect(confirmOptions?.headers).toMatchObject({Authorization:'Bearer memory-only'});
 expect(JSON.parse(String(confirmOptions?.body))).toEqual(confirm);
});

test('save and confirm reject mismatched success receipts instead of trusting a stale write',async()=>{
 respond({...pending,revision:2});
 await expect(saveOutline(current,documentId,command)).rejects.toMatchObject({failure:'invalid-response'});
 respond({...pending,snapshot:{sections:[{...snapshot.sections[0],title:'已改写'}]}});
 await expect(saveOutline(current,documentId,command)).rejects.toMatchObject({failure:'invalid-response'});
 respond({...pending,version_id:null});
 await expect(saveOutline(current,documentId,command)).rejects.toMatchObject({failure:'invalid-response'});
 respond(pending);
 await expect(confirmOutline(current,documentId,confirm)).rejects.toMatchObject({failure:'invalid-response'});
 respond({...ready,version_id:actor});
 await expect(confirmOutline(current,documentId,confirm)).rejects.toMatchObject({failure:'invalid-response'});
 respond({...ready,context_version_id:actor});
 await expect(confirmOutline(current,documentId,confirm)).rejects.toMatchObject({failure:'invalid-response'});
});

test.each([[401,'authentication'],[403,'forbidden'],[404,'missing'],[409,'conflict'],[422,'validation']])(
 'HTTP %s error envelope maps to safe %s failure',async(status,expected)=>{
  const reasons=[{code:'REQUIRED_SECTION_MISSING',path:'sections',template_section_id:requiredId}];
  refuse(Number(status),'OUTLINE_VERSION_CONFLICT',{reasons});
  await expect(saveOutline(current,documentId,command)).rejects.toMatchObject({failure:expected,status:Number(status),reasons});
 });

test('known HTTP refusal differs from an unknown network outcome',async()=>{
 refuse(503,'OUTLINE_STORAGE_UNAVAILABLE');
 await expect(saveOutline(current,documentId,command)).rejects.toMatchObject({failure:'unavailable',status:503});
 vi.mocked(fetch).mockRejectedValue(new TypeError('socket closed after PUT'));
 await expect(saveOutline(current,documentId,command)).rejects.toMatchObject({
  failure:'unavailable',message:expect.stringContaining('结果未知')});
 // A lost PUT response requires a fresh GET reconciliation before confirming a version.
 respond(pending);
 expect((await getOutline(current,documentId)).version_id).toBe(outlineVersion);
});

test('invalid scope and absent token fail before protected network access',async()=>{
 await expect(getOutline({...current,policy_epoch:[5,2,4]},documentId)).rejects.toMatchObject({failure:'context'});
 await expect(getOutline(current,'foreign-document')).rejects.toMatchObject({failure:'context'});
 auth.value='';
 await expect(getOutline(current,documentId)).rejects.toMatchObject({failure:'authentication'});
 expect(fetch).not.toHaveBeenCalled();
});

test('history rejects malformed row and malformed version ID before protected read',async()=>{
 respond({items:[{version_id:'foreign-document'}],more:false});
 await expect(getOutlineVersions(current,documentId)).rejects.toMatchObject({failure:'invalid-response'});
 await expect(getOutlineVersion(current,documentId,'foreign-version')).rejects.toMatchObject({failure:'validation'});
 expect(fetch).toHaveBeenCalledTimes(1);
});

test('malformed success envelope and revoked token do not create a trusted confirmation',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({value:ready}),{status:200}));
 await expect(confirmOutline(current,documentId,confirm)).rejects.toMatchObject({failure:'invalid-response'});
 vi.mocked(fetch).mockImplementation(async()=>{auth.value='changed';return new Response(JSON.stringify({data:ready}))});
 await expect(confirmOutline(current,documentId,confirm)).rejects.toMatchObject({failure:'cancelled'});
});
