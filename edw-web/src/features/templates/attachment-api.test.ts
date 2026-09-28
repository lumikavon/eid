import {describe,it,expect} from 'vitest';
import {inspectAttachment} from './attachment-api';
import type {WorkspaceAccess} from '../../app/access-api';

const current={actor_id:'11111111-1111-4111-8111-111111111111',workspace_id:'22222222-2222-4222-8222-222222222222',policy_epoch:[1,1,1]} as WorkspaceAccess;
const id='33333333-3333-4333-8333-333333333333';

describe('attachment response boundary',()=>{
 it('rejects forged source identifiers before network use',async()=>{
  await expect(inspectAttachment(current,id,'../../object-key')).rejects.toThrow('附件响应无效');
 });
});
