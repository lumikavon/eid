import {expect,test,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import TemplateWorkspace from './TemplateWorkspace';

const wid='00000000-0000-4000-8000-000000000001';
const aid='00000000-0000-4000-8000-000000000002';
const tid='00000000-0000-4000-8000-000000000003';
const did='00000000-0000-4000-8000-000000000004';
const current={workspace_id:wid,actor_id:aid,policy_epoch:[4,2,4],name:'当前项目',slug:'project',display_name:'作者',department:'工程部',roles:['author'],clearance:1,operations:['document:create']};
const card={template_id:tid,version_id:tid,name:'项目技术方案',description:'受控开发样例',scope:'project',category:'方案',document_type:'technical_solution',version_label:'v1',development_only:true,outline:['项目概述','实施计划']};
const types=['technical_solution','bid','prd','test_plan','project_summary','technical_requirements','quality_outline','project_plan','functional_test_outline','performance_test_outline','production_form'];
const catalog={types:types.map(id=>({id,label:id,workflow_state:'catalog_only'})),knowledge_scopes:[{id:'project_only',label:'仅当前项目',available:true},{id:'project_enterprise_quality',label:'企业与质量库',available:false},{id:'all_authorized',label:'全部',available:false}]};
const doc={id:did,workspace_id:wid,name:'项目技术方案',document_type:'technical_solution',knowledge_scope:'project_only',template_version_id:tid,version_id:tid,base_version_id:null,content_hash:'a'.repeat(64),revision:1,replayed:false,ast:{schema_version:'1.0',document:{metadata:{title:'项目技术方案',document_type:'technical_solution',knowledge_scope:'project_only',template_version_id:tid},sections:[{id:did,title:'项目概述',blocks:[{id:tid,type:'paragraph',content:{text:''}}]}],claims:[],citations:[],review_state:{status:'not_reviewed'}}}};
const calls=vi.hoisted(()=>({keys:[] as unknown[][]}));
vi.mock('@tanstack/react-query',()=>({useQueryClient:()=>({invalidateQueries:vi.fn()}),useQuery:(config:{queryKey:unknown[]})=>{calls.keys.push(config.queryKey);const name=String(config.queryKey[0]);return {data:name==='template-catalog'?catalog:name==='template-list'?[card]:name==='template-document'?doc:undefined,isFetching:false,isPending:false,error:null,refetch:vi.fn()}}}));
function render(documentId?:string){calls.keys=[];return renderToStaticMarkup(<MemoryRouter initialEntries={[`/workspaces/${wid}/${documentId?`documents/${documentId}`:'templates'}`]}><TemplateWorkspace current={current} documentId={documentId} onReject={vi.fn()} onRefresh={vi.fn()}/></MemoryRouter>)}
test('template center preserves P-07 controls and marks development catalog',()=>{
 const html=render();expect(html).toContain('id="templateSearch"');expect(html).toContain('id="templateGrid"');expect(html).toContain('按文种筛选');expect(html).toContain('产品线');expect(html).toContain('个人草稿');expect(html).toContain('开发样例');expect(html).toContain('项目技术方案');expect(html).not.toContain('正式模板');
 expect(calls.keys.every(key=>String(key[1]).includes(`${aid}:${wid}:4:2:4`))).toBe(true);
});
test('new document opens its own AST-backed editing shell without claiming a save',()=>{
 const html=render(did);expect(html).toContain(did);expect(html).toContain('id="docTree"');expect(html).toContain('项目概述');expect(html).toContain('id="docTitle"');expect(html).toContain('领域 AST 草稿');expect(html).toContain('已加载，尚未修改');expect(html).not.toContain('已保存 · 版本');
});
