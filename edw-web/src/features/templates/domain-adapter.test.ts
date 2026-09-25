import {expect,test} from 'vitest';
import {domainToEditor,editorToDomain,type DomainSection} from './domain-adapter';

const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const section:DomainSection={id:id(1),title:'范围',blocks:[
 {id:id(2),type:'paragraph',content:{text:'加粗链接',runs:[{text:'加粗',marks:[{type:'bold'}]},{text:'链接',marks:[{type:'link',href:'https://example.org/source'}]}]}},
 {id:id(3),type:'heading',content:{text:'阶段',level:2}},
 {id:id(4),type:'table',content:{rows:[[{text:'A',rowspan:2,colspan:1},{text:'B'}],[{text:'C'}]]}},
 {id:id(5),type:'figure',content:{resource_id:id(15),alt:'架构图',width:800,height:600}},
 {id:id(6),type:'diagram',content:{text:'graph TD'}},
 {id:id(7),type:'requirement',content:{requirement_id:'REQ-1',statement:'核验',verification_method:'人工',source_refs:[id(18)]}},
 {id:id(8),type:'citation',content:{text:'来源',source_id:id(19)}},
 {id:id(9),type:'warning',content:{text:'注意'}},
 {id:id(10),type:'code',content:{text:'print(1)'}},
 {id:id(11),type:'form',content:{field_id:'f1',label:'签名',value:''}},
 {id:id(12),type:'future_chart',content:{nested:{schema_version:'2.0',values:[1,2]}}},
]};

test('all legal block kinds, requirement/source refs, table spans and opaque future nodes survive adapter round-trip',()=>{
 const editor=domainToEditor(section);const result=editorToDomain(section,editor);
 expect(result.blocks.map(block=>[block.id,block.type])).toEqual(section.blocks.map(block=>[block.id,block.type]));
 expect(result.blocks[2].content.rows).toEqual([[{text:'A',rowspan:2,colspan:1},{text:'B',rowspan:1,colspan:1}],[{text:'C',rowspan:1,colspan:1}]]);
 expect(result.blocks[3]).toEqual(section.blocks[3]);expect(result.blocks[5]).toEqual(section.blocks[5]);
 expect(result.blocks[10]).toEqual(section.blocks[10]);
 expect(result.blocks[0].content.runs).toEqual(section.blocks[0].content.runs);
});

test('unknown node modification cannot be converted into a writable draft',()=>{
 const editor=domainToEditor(section);const atom=editor.content?.at(-1);
 if(!atom?.attrs)throw new Error('missing future node');
 atom.attrs.raw={...atom.attrs.raw,content:{nested:{values:[]}}};
 expect(()=>editorToDomain(section,editor)).toThrow('只读结构不可修改');
});

test('unsafe link cannot be round-tripped or persisted',()=>{
 const editor=domainToEditor(section);const first=editor.content?.[0]?.content?.[1];
 if(!first?.marks?.[0])throw new Error('missing link mark');
 first.marks[0].attrs={href:'javascript:alert(1)'};
 expect(()=>editorToDomain(section,editor)).toThrow('链接地址不安全');
});

test('paragraph alignment and list removal round-trip to domain metadata',()=>{
 const editor=domainToEditor(section);const paragraph=editor.content?.[0];if(!paragraph?.attrs)throw new Error('missing paragraph');
 paragraph.attrs.textAlign='center';
 expect(editorToDomain(section,editor).blocks[0].content.align).toBe('center');
 const listed=structuredClone(section);listed.blocks[0].content.list='bullet';const listEditor=domainToEditor(listed);
 const unwrapped=listEditor.content?.[0]?.content?.[0]?.content?.[0];if(!unwrapped)throw new Error('missing list item');
 listEditor.content![0]=unwrapped;
 expect(editorToDomain(listed,listEditor).blocks[0].content.list).toBeUndefined();
});

test('a safe @ in a link path is retained, not silently dropped',()=>{
 const changed=structuredClone(section);changed.blocks[0].content={text:'路径',runs:[{text:'路径',marks:[{type:'link',href:'https://example.org/a@b'}]}]};
 expect(editorToDomain(changed,domainToEditor(changed)).blocks[0].content.runs).toEqual(changed.blocks[0].content.runs);
});

test('deleted future nodes, table multiline and table marks cannot be silently saved',()=>{
 const missing=domainToEditor(section);missing.content?.pop();
 expect(()=>editorToDomain(section,missing)).toThrow('未来结构只读保留');
 const multiple=domainToEditor(section);const cell=multiple.content?.[2]?.content?.[0]?.content?.[0];
 if(!cell?.content)throw new Error('missing table cell');
 cell.content.push({type:'paragraph',content:[{type:'text',text:'new line'}]});
 expect(()=>editorToDomain(section,multiple)).toThrow('不支持多段落');
 cell.content.pop();const part=cell.content[0].content?.[0];if(!part)throw new Error('missing cell text');part.marks=[{type:'bold'}];
 expect(()=>editorToDomain(section,multiple)).toThrow('暂不支持无损保存');
});

test('new figure retains one block ID and private resource reference',()=>{
 const editor=domainToEditor(section);const block={id:id(33),type:'figure',content:{resource_id:id(34),alt:'照片',width:4,height:3}};
 editor.content?.push({type:'domainAtom',attrs:{blockId:block.id,raw:block}});
 expect(editorToDomain(section,editor).blocks.at(-1)).toEqual(block);
});
