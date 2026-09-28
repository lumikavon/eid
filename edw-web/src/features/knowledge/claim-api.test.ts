import {afterEach,describe,expect,it,vi} from 'vitest';
import type {WorkspaceAccess} from '../../app/access-api';
import {getTrace,citeClaim} from './claim-api';

vi.mock('../../auth/oidc',()=>({token:()=> 'current-access'}));
const current={workspace_id:'11111111-1111-4111-8111-111111111111',actor_id:'22222222-2222-4222-8222-222222222222',policy_epoch:[1,1,1]} as WorkspaceAccess;
const doc='33333333-3333-4333-8333-333333333333';
const claim='44444444-4444-4444-8444-444444444444';
const link='55555555-5555-4555-8555-555555555555';
afterEach(()=>vi.unstubAllGlobals());
describe('controlled citation boundary',()=>{
 it('stale bookmark or quote conflict requests reselection and no optimistic document update',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{code:'CITATION_RESELECT'}}),{status:409,headers:{'Content-Type':'application/json'}})));
  await expect(citeClaim(current,doc,{base_version_id:doc,revision:2,section_id:doc,block_id:doc,
   start_offset:2,end_offset:5,selected_text:'旧文',claim_id:claim,link_id:link,quoted_text:'旧引文'},new AbortController().signal)).rejects.toThrow('重新选择正文');
 });
 it('revoked trace rejects without returning a cached previous claim excerpt',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:404})));
  await expect(getTrace(current,doc,claim,new AbortController().signal)).rejects.toThrow('受控摘录已清空');
 });
 it('trace response is tied to the newly selected claim',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({data:{claim_id:link,state:'current',links:[]}}),{status:200})));
  await expect(getTrace(current,doc,claim,new AbortController().signal)).rejects.toThrow('来源追溯无效');
 });
});
