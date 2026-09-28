import {describe,it,expect} from 'vitest';
import {searchKnowledge} from './knowledge-api';
import type {WorkspaceAccess} from '../../app/access-api';

describe('authorized knowledge',()=>{
 it('rejects invalid scope before fetch',async()=>{
  await expect(searchKnowledge({workspace_id:'invalid'} as WorkspaceAccess,
   {query:'ABC-123',context_document_id:'invalid',category:'all',limit:10},new AbortController().signal)).rejects.toThrow('有效的文档范围');
 });
});
