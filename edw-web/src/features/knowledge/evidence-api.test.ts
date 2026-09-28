import {describe,it,expect} from 'vitest';
import {evidenceOrdinal,evidenceRequest,similarDocuments,type EvidenceHit} from './evidence-api';
import type {WorkspaceAccess} from '../../app/access-api';

describe('section evidence boundaries',()=>{
 it('uses immutable Pack ordinal after an earlier source is revoked',()=>{
  const visible={ordinal:7} as EvidenceHit;
  expect(evidenceOrdinal(visible)).toBe(7);
  expect(()=>evidenceOrdinal({ordinal:0} as EvidenceHit)).toThrow('证据序号无效');
 });
 it('rejects an invalid document scope before requesting any passages',async()=>{
  await expect(evidenceRequest({workspace_id:'invalid'} as WorkspaceAccess,'invalid','/jobs',new AbortController().signal)).rejects.toThrow('文档范围无效');
 });
 it('rejects an invalid similarity context before requesting anything',async()=>{
  await expect(similarDocuments({workspace_id:'invalid'} as WorkspaceAccess,'invalid',{section_id:'invalid',outline_version_id:'invalid',context_version_id:'invalid',document_version_id:'invalid'},new AbortController().signal)).rejects.toThrow('文档范围无效');
 });
});
