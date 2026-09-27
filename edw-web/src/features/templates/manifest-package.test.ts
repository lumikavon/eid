import {describe,expect,it,vi} from 'vitest';
import {manifestFromDraft,newManifestDraft,packageManifest} from './manifest-package';

describe('development template manifest package (source only; not executed in this iteration)',()=>{
 it('emits a bounded stored ZIP with one manifest entry and null policy references',async()=>{
  vi.stubGlobal('crypto',{randomUUID:()=> 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'});
  try{
   const draft={...newManifestDraft(),name:'交付模板',category:'技术',sections:[{id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',title:'概述',mandatory:true}]};
   const file=packageManifest(draft),bytes=new Uint8Array(await file.arrayBuffer());
   expect(file.name).toBe('template-manifest.zip');expect(new DataView(bytes.buffer).getUint32(0,true)).toBe(0x04034b50);
   expect(new TextDecoder().decode(bytes)).toContain('"approval_policy_version_id":null');
   expect(manifestFromDraft(draft).sections[0].mandatory).toBe(true);
  }finally{vi.unstubAllGlobals()}
 });
 it('rejects unsafe titles, missing sections and oversized descriptions before any submission',()=>{
  const base={...newManifestDraft(),name:'Template',category:'Technical',sections:[{id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',title:'Overview',mandatory:true}]};
  expect(()=>packageManifest({...base,sections:[]})).toThrow();
  expect(()=>packageManifest({...base,name:'\u0000unsafe'})).toThrow();
  expect(()=>packageManifest({...base,description:'a'.repeat(1025)})).toThrow();
 });
});
