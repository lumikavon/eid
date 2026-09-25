import {expect,test} from 'vitest';
import {planMerge} from './domain-merge';
import type {DomainAst} from './domain-adapter';

const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const base:DomainAst={schema_version:'1.0',document:{metadata:{title:'草稿',template_version_id:id(1),document_type:'technical_solution',knowledge_scope:'project_only'},sections:[{id:id(2),title:'范围',blocks:[{id:id(3),type:'paragraph',content:{text:'初始'}},{id:id(4),type:'paragraph',content:{text:'其次'}}]}],claims:[{id:id(5),text:'Claim'}],citations:[{id:id(6),source_id:id(7)}],review_state:{status:'not_reviewed'}}};
const copy=()=>structuredClone(base);

test('disjoint edits and distinct new blocks survive without choosing a winner',()=>{
 const local=copy(),latest=copy();local.document.sections[0].blocks[0].content.text='本地';
 latest.document.sections[0].blocks[1].content.text='服务端';
 local.document.sections[0].blocks.push({id:id(8),type:'paragraph',content:{text:'本地新增'}});
 latest.document.sections[0].blocks.push({id:id(9),type:'paragraph',content:{text:'服务端新增'}});
 const plan=planMerge(base,local,latest);expect(plan.unresolved).toEqual([]);
 expect(plan.ast.document.sections[0].blocks.map(block=>block.content.text)).toEqual(['本地','服务端','本地新增','服务端新增']);
 expect(base.document.sections[0].blocks[0].content.text).toBe('初始');
});

test('distinct inserts retain their anchors instead of silently moving local content',()=>{
 const local=copy(),latest=copy();local.document.sections[0].blocks.splice(1,0,{id:id(8),type:'paragraph',content:{text:'X'}});
 latest.document.sections[0].blocks.splice(1,0,{id:id(9),type:'paragraph',content:{text:'Y'}});
 expect(planMerge(base,local,latest).ast.document.sections[0].blocks.map(block=>block.content.text)).toEqual(['初始','X','Y','其次']);
});

test('overlap, delete-versus-edit and manual choice require explicit resolution',()=>{
 const local=copy(),latest=copy();local.document.sections[0].blocks[0].content.text='本地';
 latest.document.sections[0].blocks[0].content.text='服务端';local.document.sections[0].blocks.pop();
 latest.document.sections[0].blocks[1].content.text='并发修改';
 const pending=planMerge(base,local,latest);expect(pending.unresolved).toHaveLength(2);
 const choices=Object.fromEntries(pending.conflicts.map(item=>[item.key,{strategy:'mine' as const}]));
 const merged=planMerge(base,local,latest,choices);expect(merged.unresolved).toEqual([]);
 expect(merged.ast.document.sections[0].blocks.map(block=>block.content.text)).toEqual(['本地']);
 const manual=planMerge(base,local,latest,{...choices,[pending.conflicts[0].key]:{strategy:'manual',manual:{id:id(3),type:'paragraph',content:{text:'人工'}}}});
 expect(manual.ast.document.sections[0].blocks[0].content.text).toBe('人工');
});

test('future node or section order cannot be silently discarded',()=>{
 const historical=copy();historical.document.sections[0].blocks.push({id:id(10),type:'future',content:{stable:true}});
 const latest=structuredClone(historical),local=structuredClone(historical);
 local.document.sections[0].blocks.pop();
 expect(()=>planMerge(historical,local,latest)).toThrow('未来结构只读保留');
 const reordered=copy();reordered.document.sections[0].blocks.reverse();
 expect(()=>planMerge(base,reordered,copy())).toThrow('顺序');
});
