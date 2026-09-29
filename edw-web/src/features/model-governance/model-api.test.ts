import {describe,it,expect} from 'vitest';
import {getModelPolicy} from './model-api';
import type {WorkspaceAccess} from '../../app/access-api';

// Auth, permission and disabled-state rendering remain runtime not-run in this session.
describe('X-20 model governance boundaries',()=>{
 it('rejects malformed workspace identifiers before making a request',async()=>{
  await expect(getModelPolicy({workspace_id:'invalid'} as WorkspaceAccess)).rejects.toThrow('工作区无效');
 });
});
