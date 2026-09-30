import {Node,type JSONContent} from '@tiptap/core';
import {Paragraph} from '@tiptap/extension-paragraph';
import {Heading} from '@tiptap/extension-heading';
import {Table} from '@tiptap/extension-table';

export type DomainBlock={id:string;type:string;content:Record<string,unknown>;[key:string]:unknown};
export type DomainSection={id:string;title:string;blocks:DomainBlock[];[key:string]:unknown};
export type DomainAst={schema_version:'1.0';document:{metadata:Record<string,unknown>;sections:DomainSection[];claims:unknown[];citations:unknown[];review_state:Record<string,unknown>;[key:string]:unknown};[key:string]:unknown};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const safeLink=(value:unknown):value is string=>{if(typeof value!=='string'||/[\s\\]/.test(value))return false;try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!!url.hostname&&!url.username&&!url.password&&url.port!=='0'}catch{return false}};
const known=new Set(['paragraph','heading','table','figure','diagram','requirement','test_item','test_case','acceptance','citation','warning','code','form']);
const asRecord=(value:unknown):Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const text=(value:unknown):string=>typeof value==='string'?value:'';

const privateAttribute={default:null,renderHTML:()=>({})};
export const DomainParagraph=Paragraph.extend({addAttributes(){return {...this.parent?.(),blockId:privateAttribute,domainList:privateAttribute,domainOriginal:privateAttribute}}});
export const DomainHeading=Heading.extend({addAttributes(){return {...this.parent?.(),blockId:privateAttribute,domainOriginal:privateAttribute}}});
export const DomainTable=Table.extend({addAttributes(){return {...this.parent?.(),blockId:privateAttribute,domainOriginal:privateAttribute}}});
export const DomainAtom=Node.create({
 name:'domainAtom',group:'block',atom:true,selectable:true,
 addAttributes(){return {blockId:privateAttribute,raw:privateAttribute}},
 parseHTML(){return [{tag:'div[data-domain-atom]'}]},
 renderHTML({node}){const raw=asRecord(node.attrs.raw);const label=known.has(text(raw.type))?`结构块 · ${text(raw.type)}`:'未来结构（只读）';return ['div',{'data-domain-atom':'true',contenteditable:'false',role:'note'},label]},
});

const toTextNodes=(content:Record<string,unknown>):JSONContent[]=>{
 const runs=Array.isArray(content.runs)?content.runs:[{text:content.text??''}];
 return runs.filter(run=>text(asRecord(run).text).length).map(run=>{
  const value=asRecord(run);const marks=Array.isArray(value.marks)?value.marks:[];
  return {type:'text',text:text(value.text),marks:marks.flatMap(mark=>{
   const item=asRecord(mark);if(['bold','italic','underline'].includes(text(item.type)))return [{type:item.type as string}];
   if(item.type==='link'&&safeLink(item.href))return [{type:'link',attrs:{href:item.href}}];
   if(item.type==='color'&&typeof item.value==='string'&&/^#[0-9a-fA-F]{6}$/.test(item.value))return [{type:'textStyle',attrs:{color:item.value}}];
   throw new Error('不支持的领域文本格式，不能无损编辑');
  })};
 });
};
const cellNode=(cell:unknown):JSONContent=>{const data=asRecord(cell);return {type:'tableCell',attrs:{colspan:data.colspan??1,rowspan:data.rowspan??1},content:[{type:'paragraph',content:toTextNodes({text:text(data.text)})}]}};
export function domainToEditor(section:DomainSection):JSONContent{
 return {type:'doc',content:section.blocks.map(block=>{
  const content=asRecord(block.content);
  if(block.type==='paragraph'||block.type==='heading'){
   const node:JSONContent={type:block.type,attrs:{blockId:block.id,domainOriginal:block,textAlign:content.align??'left', ...(block.type==='heading'?{level:content.level??2}:{domainList:content.list??null})},content:toTextNodes(content)};
   if(block.type==='paragraph'&&content.list==='bullet')return {type:'bulletList',content:[{type:'listItem',content:[node]}]};
   if(block.type==='paragraph'&&content.list==='ordered')return {type:'orderedList',content:[{type:'listItem',content:[node]}]};
   return node;
  }
  if(block.type==='table'&&Array.isArray(content.rows))return {type:'table',attrs:{blockId:block.id,domainOriginal:block},content:content.rows.map(row=>({type:'tableRow',content:Array.isArray(row)?row.map(cellNode):[]}))};
  return {type:'domainAtom',attrs:{blockId:block.id,raw:block}};
 })};
}
const flatten=(nodes:JSONContent[],list?:'bullet'|'ordered'):JSONContent[]=>nodes.flatMap(node=>{
 if(node.type==='bulletList'||node.type==='orderedList')return flatten(node.content??[],node.type==='bulletList'?'bullet':'ordered');
 if(node.type==='listItem')return flatten(node.content??[],list);
 return [{...node,attrs:{...node.attrs,domainList:list??null}}];
});
const fromTextNodes=(nodes:JSONContent[]|undefined)=>{
 const runs=(nodes??[]).flatMap(node=>node.type==='text'&&typeof node.text==='string'?[{text:node.text,marks:(node.marks??[]).flatMap(mark=>{
  if(['bold','italic','underline'].includes(text(mark.type)))return [{type:mark.type}];
  if(mark.type==='link'){
   if(!safeLink(mark.attrs?.href))throw new Error('链接地址不安全');
   return [{type:'link',href:mark.attrs.href}];
  }
  if(mark.type==='textStyle'&&typeof mark.attrs?.color==='string'&&/^#[0-9a-fA-F]{6}$/.test(mark.attrs.color))return [{type:'color',value:mark.attrs.color}];
  throw new Error('不支持的编辑器文本格式，不能保存');
 })}]:node.type?(()=>{throw new Error('不支持的编辑器行内结构，不能保存')})():[]);
 return {text:runs.map(run=>run.text).join(''),runs};
};
const cellText=(node:JSONContent):string=>{
 const contents=node.content??[];if(contents.length!==1||contents[0].type!=='paragraph')throw new Error('表格单元格不支持多段落');
 const parts=contents[0].content??[];
 if(parts.some(part=>part.type!=='text'||(part.marks?.length??0)>0))throw new Error('表格单元格格式暂不支持无损保存');
 return parts.map(part=>part.text??'').join('');
};
export function editorToDomain(section:DomainSection,editor:JSONContent):DomainSection{
 if(editor.type!=='doc')throw new Error('编辑器结构无效');
 const original=new Map(section.blocks.map(block=>[block.id,block]));
 const blocks=flatten(editor.content??[]).map(node=>{
  const id=node.attrs?.blockId;
  if(typeof id!=='string'||!uuid.test(id))throw new Error('结构块标识丢失');
  const previous=original.get(id);
  if(node.type==='domainAtom'){
   const raw=asRecord(node.attrs?.raw);
   if(!previous){if(raw.type!=='figure'||raw.id!==id||!uuid.test(text(asRecord(raw.content).resource_id)))throw new Error('只读结构不可修改');return raw as DomainBlock}
   if(JSON.stringify(raw)!==JSON.stringify(previous))throw new Error('只读结构不可修改');
   return previous;
  }
  if(node.type==='paragraph'||node.type==='heading'){
   const base=previous??{id,type:node.type,content:{text:''}};
   if(base.type!==node.type)throw new Error('结构块类型改变');
   const content:Record<string,unknown>={...base.content,...fromTextNodes(node.content)};
   const align=node.attrs?.textAlign;if(align!==undefined&&align!==null){if(!['left','center','right','justify'].includes(String(align)))throw new Error('不支持的段落对齐方式');content.align=align}
   if(node.type==='heading')content.level=node.attrs?.level??2;
   else if(node.attrs?.domainList)content.list=node.attrs.domainList;
   else delete content.list;
   return {...base,content};
  }
  if(node.type==='table'){
   const base=previous??{id,type:'table',content:{rows:[]}};
   if(base.type!=='table')throw new Error('表格结构块类型改变');
   const oldRows=Array.isArray(base.content.rows)?base.content.rows:[];
   const rows=(node.content??[]).map((row,rowIndex)=>(row.content??[]).map((cell,cellIndex)=>({
    ...asRecord(Array.isArray(oldRows[rowIndex])?oldRows[rowIndex][cellIndex]:{}),
    text:cellText(cell),rowspan:cell.attrs?.rowspan??1,colspan:cell.attrs?.colspan??1,
   })));
   return {...base,content:{...base.content,rows}};
  }
  throw new Error('编辑器出现未支持的结构');
 });
 if(new Set(blocks.map(block=>block.id)).size!==blocks.length)throw new Error('重复结构块标识');
 section.blocks.forEach((originalBlock,index)=>{
  if(!known.has(originalBlock.type)&&JSON.stringify(originalBlock)!==JSON.stringify(blocks[index]))throw new Error('未来结构只读保留，不可删除或移动');
 });
 return {...section,blocks};
}
