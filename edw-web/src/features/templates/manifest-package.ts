import type {DocumentType} from './template-api';
import type {Manifest,Section} from './governance-api';

const MAX_MANIFEST=128*1024;
const invalid=(value:string)=>Array.from(value).some(char=>{const code=char.codePointAt(0)!;return code<32||code>=0xd800&&code<=0xdfff});
const types:DocumentType[]=['technical_solution','bid','prd','test_plan','project_summary','technical_requirements','quality_outline','project_plan','functional_test_outline','performance_test_outline','production_form'];
const emptyRules=()=>({retrieval_profile_id:null,prompt_version_id:null,reviewer_rule_version_id:null,render_theme_version_id:null,approval_policy_version_id:null});

export type ManifestDraft=Pick<Manifest,'name'|'description'|'category'|'document_type'|'sections'>;
export const newManifestDraft=():ManifestDraft=>({name:'',description:'',category:'',document_type:'technical_solution',sections:[{id:crypto.randomUUID(),title:'',mandatory:true}]});
export const addSection=(sections:Section[]):Section[]=>[...sections,{id:crypto.randomUUID(),title:'',mandatory:false}];

export function manifestFromDraft(draft:ManifestDraft):Manifest{
 const name=draft.name.trim(),category=draft.category.trim();
 if(!name||name.length>256||invalid(name)||!category||category.length>128||invalid(category)||draft.description.length>1024||invalid(draft.description)||!types.includes(draft.document_type)||draft.sections.length<1||draft.sections.length>64)throw new Error('请填写合法的名称、分类、文种和 1–64 个章节');
 const ids=new Set<string>();
 const sections=draft.sections.map(section=>{
  const title=section.title.trim();
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(section.id)||ids.has(section.id)||!title||title.length>256||invalid(title)||typeof section.mandatory!=='boolean')throw new Error('章节标题不能为空、重复 ID 不允许，且不能包含控制字符');
  ids.add(section.id);return {id:section.id,title,mandatory:section.mandatory};
 });
 return {schema_version:'1.0',name,description:draft.description,category,document_type:draft.document_type,sections,rules:emptyRules(),assets:[]};
}

// A single stored entry avoids executable content and compression ambiguity. The Worker
// remains authoritative: producing a ZIP in the browser never counts as validation.
export function packageManifest(draft:ManifestDraft):File{
 const raw=new TextEncoder().encode(JSON.stringify(manifestFromDraft(draft)));
 if(raw.length>MAX_MANIFEST)throw new Error('清单超过 128 KiB');
 const filename=new TextEncoder().encode('manifest.json');
 const size=30+filename.length+raw.length+46+filename.length+22;
 if(size>5*1024*1024)throw new Error('模板包超过 5 MiB');
 const buffer=new ArrayBuffer(size), bytes=new Uint8Array(buffer), view=new DataView(buffer);
 let crc=0xffffffff;
 for(const byte of raw){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0)}
 crc=(crc^0xffffffff)>>>0;
 const filenameLength=filename.length,central=30+filenameLength+raw.length;
 view.setUint32(0,0x04034b50,true);view.setUint16(4,20,true);view.setUint16(6,0,true);view.setUint16(8,0,true);
 view.setUint32(14,crc,true);view.setUint32(18,raw.length,true);view.setUint32(22,raw.length,true);view.setUint16(26,filenameLength,true);
 bytes.set(filename,30);bytes.set(raw,30+filenameLength);
 view.setUint32(central,0x02014b50,true);view.setUint16(central+4,20,true);view.setUint16(central+6,20,true);
 view.setUint32(central+16,crc,true);view.setUint32(central+20,raw.length,true);view.setUint32(central+24,raw.length,true);
 view.setUint16(central+28,filenameLength,true);bytes.set(filename,central+46);
 const end=central+46+filenameLength;
 view.setUint32(end,0x06054b50,true);view.setUint16(end+8,1,true);view.setUint16(end+10,1,true);
 view.setUint32(end+12,46+filenameLength,true);view.setUint32(end+16,central,true);
 return new File([buffer],'template-manifest.zip',{type:'application/zip'});
}
