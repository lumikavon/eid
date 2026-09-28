import {describe,it,expect} from 'vitest';
import {inspectConflict} from './knowledge-api';
import type {WorkspaceAccess} from '../../app/access-api';

describe('governance guard',()=>{
 it('rejects invalid conflict IDs before protected requests',async()=>{
  await expect(inspectConflict({workspace_id:'invalid'} as WorkspaceAccess,'bad','bad',new AbortController().signal)).rejects.toThrow('来源无效');
 });
});
