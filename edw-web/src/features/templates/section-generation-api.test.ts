import {describe,expect,it} from 'vitest';
import type {SectionInputs,SectionJob} from './section-generation-api';

describe('section generation response shape',()=>{
 it('keeps missing evidence separate from a generated proposal',()=>{
  const inputs:SectionInputs={section_id:'section',document_version_id:'version',document_revision:1,pack_id:null,pack_job_id:null,gaps:['EVIDENCE_PACK_REQUIRED']};
  const job:SectionJob={id:'job',section_id:'section',state:'BLOCKED_BY_MISSING_INFO',stage:'blocked',attempt:1,error_code:'SECTION_MISSING_SUPPORT',missing:['NO_CURRENT_SUPPORT'],proposal_hash:null,updated_at:'2026-09-28T00:00:00Z'};
  expect(inputs.pack_id).toBeNull();expect(job.proposal).toBeUndefined();expect(job.missing).toContain('NO_CURRENT_SUPPORT');
 });
});
