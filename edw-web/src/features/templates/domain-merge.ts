import type {DomainAst,DomainBlock,DomainSection} from './domain-adapter';

export type MergeChoice={strategy:'mine'|'latest'|'manual';manual?:unknown};
export type MergeConflict={key:string;label:string;kind:'block'|'title'|'section'|'bindings';base:unknown;local:unknown;latest:unknown};
export type MergePlan={ast:DomainAst;conflicts:MergeConflict[];unresolved:string[]};
export const sameDomainValue=(a:unknown,b:unknown)=>JSON.stringify(a,(_,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.entries(value).sort(([x],[y])=>x.localeCompare(y))):value)===JSON.stringify(b,(_,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.entries(value).sort(([x],[y])=>x.localeCompare(y))):value);
const equal=sameDomainValue;
const clone=<T>(value:T):T=>structuredClone(value);
const ids=(blocks:DomainBlock[])=>blocks.map(block=>block.id);
const known=new Set(['paragraph','heading','table','figure','diagram','requirement','citation','warning','code','form']);
const sameOrder=(base:string[],other:string[])=>equal(base.filter(id=>other.includes(id)),other.filter(id=>base.includes(id)));

/** Three-way domain merge. No editor JSON or DOM, no implicit last-writer-wins. */
export function planMerge(base:DomainAst,local:DomainAst,latest:DomainAst,choices:Record<string,MergeChoice>={}):MergePlan{
 if(base.schema_version!=='1.0'||local.schema_version!=='1.0'||latest.schema_version!=='1.0')throw new Error('领域 AST 版本不兼容');
 const b=base.document,l=local.document,s=latest.document;
 if(!equal(b.metadata.template_version_id,l.metadata.template_version_id)||!equal(b.metadata.template_version_id,s.metadata.template_version_id)||
    !equal({...b.metadata,title:undefined},{...l.metadata,title:undefined})||!equal({...s.metadata,title:undefined},{...l.metadata,title:undefined})||
    !equal(b.review_state,l.review_state)||!equal({...b,metadata:undefined,sections:undefined,claims:undefined,citations:undefined},{...l,metadata:undefined,sections:undefined,claims:undefined,citations:undefined}))throw new Error('不可变领域元数据已变化');
 const baseSections=b.sections.map(section=>section.id);
 if(!equal(baseSections,l.sections.map(section=>section.id))||!equal(baseSections,s.sections.map(section=>section.id)))throw new Error('章节结构变化需重新核对，不能自动合并');
 const conflicts:MergeConflict[]=[];const unresolved:string[]=[];
 function choose<T>(key:string,label:string,kind:MergeConflict['kind'],before:T,mine:T,newest:T):T{
  if(equal(mine,before))return clone(newest);
  if(equal(newest,before)||equal(mine,newest))return clone(mine);
  conflicts.push({key,label,kind,base:before,local:mine,latest:newest});
  const decision=choices[key];if(!decision){unresolved.push(key);return clone(newest)}
  if(decision.strategy==='mine')return clone(mine);
  if(decision.strategy==='latest')return clone(newest);
  if(decision.strategy!=='manual')throw new Error('人工合并策略无效');
  if(!Object.hasOwn(decision,'manual')||decision.manual===undefined){unresolved.push(key);return clone(newest)}
  return clone(decision.manual as T);
 }
 const result=clone(latest);
 result.document.metadata.title=choose('document:title','文档标题','title',b.metadata.title,l.metadata.title,s.metadata.title);
 result.document.claims=choose('document:claims','Claim 绑定','bindings',b.claims,l.claims,s.claims);
 result.document.citations=choose('document:citations','引用绑定','bindings',b.citations,l.citations,s.citations);
 result.document.sections=result.document.sections.map((fresh:DomainSection,index:number)=>{
  const old=b.sections[index],mine=l.sections[index];
  if(!equal({...old,title:undefined,blocks:undefined},{...mine,title:undefined,blocks:undefined}))throw new Error('章节附加字段不能静默改写');
  const section=clone(fresh);section.title=choose(`section:${old.id}:title`,`章节：${old.title}`,'section',old.title,mine.title,fresh.title);
  const oldIds=ids(old.blocks),mineIds=ids(mine.blocks),freshIds=ids(fresh.blocks);
  old.blocks.forEach((block,position)=>{if(!known.has(block.type)&&(!equal(block,mine.blocks[position])||!equal(block,fresh.blocks[position])))throw new Error('未来结构只读保留，不可删除、移动或修改')});
  mine.blocks.forEach(block=>{if(!known.has(block.type)&&!old.blocks.some(item=>item.id===block.id))throw new Error('不可新增未知结构')});
  if(new Set(mineIds).size!==mineIds.length||new Set(freshIds).size!==freshIds.length||!sameOrder(oldIds,mineIds)||!sameOrder(oldIds,freshIds))throw new Error('章节块顺序或标识发生不兼容变化');
  const oldMap=new Map(old.blocks.map(block=>[block.id,block]));const mineMap=new Map(mine.blocks.map(block=>[block.id,block]));const freshMap=new Map(fresh.blocks.map(block=>[block.id,block]));
  const merged=new Map<string,DomainBlock>();
  for(const id of new Set([...oldIds,...mineIds,...freshIds])){
   const block=choose(`block:${section.id}:${id}`,`章节「${section.title}」的块 ${id}`,'block',oldMap.get(id)??null,mineMap.get(id)??null,freshMap.get(id)??null);
   if(block!==null){if(!block||block.id!==id)throw new Error('人工合并块标识不一致');merged.set(id,block)}
  }
  // Keep server order, but insert local-only blocks at their nearest retained local anchors.
  const ordered=freshIds.filter(id=>merged.has(id));
  mineIds.forEach((id,index)=>{
   if(freshMap.has(id)||!merged.has(id))return;
   const previous=mineIds.slice(0,index).reverse().find(candidate=>ordered.includes(candidate));
   const following=mineIds.slice(index+1).find(candidate=>ordered.includes(candidate));
   const position=previous?ordered.indexOf(previous)+1:following?ordered.indexOf(following):ordered.length;
   if(following&&position>ordered.indexOf(following))throw new Error('新增块的相对位置存在冲突，必须人工处理');
   ordered.splice(position,0,id);
  });
  section.blocks=ordered.map(id=>merged.get(id)!);
  return section;
 });
 return {ast:result,conflicts,unresolved};
}
