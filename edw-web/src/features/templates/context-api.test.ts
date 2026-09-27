import {describe,expect,it} from 'vitest';
import {blankContext,validateContext} from './context-api';

const id='11111111-1111-4111-8111-111111111111';
const pending={version_id:null,revision:0,document_version_id:id,document_revision:1,snapshot:null,content_hash:null,created_by:null,created_at:null,confirmed_by:null,confirmed_at:null,state:'CONTEXT_PENDING',reasons:[{code:'CONTEXT_MISSING',path:'snapshot'}]};
describe('X-15 fail-closed response contract',()=>{
 it('requires explicit human confirmation for ready',()=>{
  expect(validateContext(pending).state).toBe('CONTEXT_PENDING');
  expect(()=>validateContext({...pending,state:'CONTEXT_READY'})).toThrow();
  expect(()=>validateContext({...pending,version_id:id,state:'CONTEXT_READY',reasons:[]})).toThrow();
 });
 it('rejects malformed historical snapshot or fabricated ready without reason-free confirmation',()=>{
  const version={...pending,version_id:id,revision:1,content_hash:'a'.repeat(64),created_by:id,created_at:'2026-09-26T00:00:00Z',snapshot:{...blankContext(),intent:'Manual purpose',facts:[{key:'Capacity',value:'42',unit:'kW',source:{locator:'   ',resource_id:id},owner_id:id,confirmed:true}]}};
  expect(()=>validateContext(version)).toThrow();
  expect(()=>validateContext({...version,snapshot:{...blankContext(),intent:'Manual purpose'},state:'CONTEXT_READY',reasons:[],confirmed_by:id,confirmed_at:'2026-09-26T00:00:00Z'})).toThrow();
  expect(()=>validateContext({...version,snapshot:{...blankContext(),intent:'Manual purpose',zero_facts:true},state:'CONTEXT_READY',reasons:[],confirmed_by:id,confirmed_at:'2026-09-26T00:00:00Z'})).not.toThrow();
 });
 it('does not silently declare an empty draft ready',()=>{
  expect(blankContext()).toEqual({intent:'',facts:[],glossary:[],constraints:[],missing:[],zero_facts:false});
 });
});
