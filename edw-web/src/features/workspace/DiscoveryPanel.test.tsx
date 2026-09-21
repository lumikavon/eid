import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {MemoryRouter} from 'react-router-dom';
import DiscoveryPanel from './DiscoveryPanel';
import {DiscoveryError,type Context,type Item,type Storage,type Summary} from '../../app/discovery-api';
vi.mock('../../auth/oidc',()=>({token:()=> 'memory-only'}));
const mocked=vi.hoisted(()=>({states:{} as Record<string,{data?:unknown;error?:unknown;isPending?:boolean;isFetching?:boolean}>,keys:[] as unknown[][],enabled:[] as boolean[],retainDisabledCache:false}));
vi.mock('@tanstack/react-query',()=>({useQueryClient:()=>({cancelQueries:vi.fn(),removeQueries:vi.fn(),invalidateQueries:vi.fn()}),useQuery:(options:{queryKey:unknown[];enabled:boolean})=>{mocked.keys.push(options.queryKey);mocked.enabled.push(options.enabled);const key=options.queryKey[6] as string;return {isFetching:false,isPending:false,error:null,...(options.enabled||mocked.retainDisabledCache?mocked.states[key]:{}),refetch:vi.fn()}}}));
const wid='00000000-0000-4000-8000-000000000001';const actor='00000000-0000-4000-8000-000000000002';const rid='00000000-0000-4000-8000-000000000003';
const context:Context={actor_id:actor,workspace_id:wid,policy_epoch:[4,2,4]};
const current={...context,name:'真实项目',slug:'actual-project',display_name:'当前作者',department:'工程部',roles:['author'],clearance:1,operations:['workspace:read','document:edit']};
const item:Item={id:rid,workspace_id:wid,title:'当前授权文档',kind:'document',document_type:'technical',lifecycle:'DRAFT',visibility:'visible',created_by:actor,created_at:'2026-09-14T00:00:00Z',updated_at:'2026-09-18T02:00:00Z',version_label:null,revision:1,resource_epoch:8,favorite:false,favorite_revision:0,participating:true};
const storage:Storage={metadata_bytes:321,measured_at:'2026-09-18T00:00:00Z',scope:'authorized_filtered_record_metadata',definition:'pg_column_size(discovery_record)+pg_column_size(access_resource.title)',visibility:'visible',attachment_bytes:null,quota_bytes:null};
const page={items:[item],total_count:1,next_cursor:null,context,storage};
const summary:Summary={context,workspace:{id:wid,name:'真实项目',slug:'actual-project',project_id:'p',customer_id:'c',product_id:'x',department:'工程部',classification:1},total_count:1,storage,week_new_documents:{value:1,window_start:'2026-09-14T00:00:00Z',window_end:'2026-09-18T00:00:00Z',definition:'authorized_filtered_documents_created_since_utc_monday'},todo_count:1,last_activity_at:null,future_panels:(['review','ai_words','quality','templates','recommendations','creation'] as const).map(id=>({id,value:null,state:id==='quality'?'not_evaluated':'unavailable',reason:'尚无权威业务数据',owner:'2-1'}))};
const detail={item,context,resource_context:{...context,policy_epoch:[4,2,8]},actions:{favorite:true,restore:false,restore_policy_version:null},content_state:'metadata_only'};
function render(view='home',query=''){return renderToStaticMarkup(<MemoryRouter initialEntries={[`/workspaces/${wid}/${view}`]}><DiscoveryPanel current={current} search={{query,sequence:1}} onReject={vi.fn()} onRefresh={vi.fn()}/></MemoryRouter>)}
beforeEach(()=>{vi.stubGlobal('navigator',{onLine:true});mocked.states={list:{data:page},summary:{data:summary},todo:{data:page},detail:{data:detail}};mocked.keys=[];mocked.enabled=[];mocked.retainDisabledCache=false});
afterEach(()=>vi.unstubAllGlobals());
test('home preserves four KPIs, four cards, four tabs and five creation entries with null future values',()=>{
 const html=render();expect(html.match(/class="kpi"/g)).toHaveLength(4);expect(html.match(/class="mini-card"/g)).toHaveLength(4);expect(html.match(/role="tab"/g)).toHaveLength(4);expect(html.match(/class="quick-item"/g)).toHaveLength(5);
 expect(html).toContain('当前授权文档');expect(html).toContain('未评估');expect(html).toContain('UTC 周一');expect(html).not.toContain('28,560');expect(html).not.toContain('较上周 +');
 expect(mocked.keys.every(key=>key.slice(0,6).join(':')===`discovery:${actor}:${wid}:4:2:4`)).toBe(true);
});
test('empty filtered collection retains filters and reset without sample rows',()=>{
 mocked.states.list={data:{...page,items:[],total_count:0}};const html=render('documents?status=ARCHIVED&type=manual');
 expect(html).toContain('data-state="empty-filtered"');expect(html).toContain('value="ARCHIVED" selected');expect(html).toContain('共 0 条');expect(html).not.toContain('当前授权文档');
});
test.each(['unavailable','timeout','offline','authentication','forbidden'] as const)('persistent %s hides formerly cached record data',failure=>{
 mocked.states.list={data:page,error:new DiscoveryError(failure,`状态 ${failure}`)};const html=render('documents');expect(html).toContain(`data-state="${failure}"`);expect(html).not.toContain('当前授权文档');expect(html).not.toContain('discovery-table');
});
test('loading masks old actionable records instead of presenting stale success',()=>{
 mocked.states.list={data:page,isFetching:true};const html=render('documents');expect(html).toContain('data-state="loading"');expect(html).not.toContain('当前授权文档');
});
test('metadata detail has exact identity, no body editor, and archived state remains explicit',()=>{
 mocked.states.detail={data:{...detail,item:{...item,lifecycle:'ARCHIVED',visibility:'recycled'}}};const html=render(`records/${rid}`);
 expect(html).toContain(rid);expect(html).toContain('仅有元数据');expect(html).toContain('归档内容只读');expect(html).toContain('当前权限或恢复策略不支持');expect(html).toMatch(/disabled=""[^>]*>恢复列表可见性/);expect(html).not.toContain('contenteditable');expect(html).not.toContain('永久删除');
});
test('resource denial clears its title and actions without claiming workspace denial',()=>{
 mocked.states.detail={data:detail,error:new DiscoveryError('forbidden','当前目标不可访问，受保护内容已清除',403)};const html=render(`records/${rid}`);expect(html).not.toContain('当前授权文档');expect(html).not.toContain('添加收藏');expect(html).not.toContain('工作区访问被拒绝');expect(html).toContain('返回记录列表');
});
test('search shows current project scope and distinguishes real functions',()=>{
 mocked.states.list={data:{...page,functions:[{id:'documents',route:'documents',title:'项目文档',workspace_id:wid}]}};const html=render('search','查找此词');expect(html).toContain('搜索范围：真实项目');expect(html).toContain('查找此词');expect(html).toContain('aria-label="功能结果"');
});
test('function-only search results do not claim that the search has no matches',()=>{
 mocked.states.list={data:{...page,items:[],total_count:0,functions:[{id:'recycle',route:'recycle',title:'回收站',workspace_id:wid}]}};
 const html=render('search','回收');expect(html).toContain('aria-label="功能结果"');expect(html).toContain('回收站 · 真实项目');expect(html).toContain('共 0 条当前授权记录');expect(html).not.toContain('data-state="empty-filtered"');expect(html).not.toContain('无符合筛选条件的数据');
});
test('search with neither records nor functions retains the filtered empty state',()=>{
 mocked.states.list={data:{...page,items:[],total_count:0,functions:[]}};
 const html=render('search','无匹配词');expect(html).toContain('data-state="empty-filtered"');expect(html).toContain('无符合筛选条件的数据');expect(html).not.toContain('aria-label="功能结果"');
});
test('empty search waits for Enter without sending an unscoped list',()=>{
 const html=render('search');expect(html).toContain('请在顶部输入关键词并按 Enter');expect(html).not.toContain('当前授权文档');
});
test('project detail displays current authoritative attributes and an actual collection entry',()=>{
 const html=render('project');expect(html).toContain('discovery-project');expect(html).toContain('暂无记录活动');expect(html).toContain('打开项目文档');expect(html).toContain(wid);
});
test('references default to the union collection with optional kind AND filter',()=>{
 render('references');const key=mocked.keys.find(k=>k[6]==='list')!;expect(String(key[7])).toContain('"collection":"references"');expect(String(key[7])).not.toContain('"kind"');
});
test.each(['all','todo','references'])('route collection %s survives parsing with the other filters',collection=>{
 render(`favorites?collection=${collection}&kind=reference&type=manual&status=ARCHIVED`);
 const key=mocked.keys.find(k=>k[6]==='list')!;expect(JSON.parse(String(key[7]))[2]).toEqual({collection,tab:'favorites',visibility:'visible',limit:20,kind:'reference',document_type:'manual',lifecycle:'ARCHIVED'});
});
test('documents references intersection stays explicit instead of widening to all documents',()=>{
 render('documents?collection=references');const key=mocked.keys.find(k=>k[6]==='list')!;
 expect(JSON.parse(String(key[7]))[2]).toMatchObject({collection:'references',kind:'document'});
});
test.each([
 ['documents?kind=knowledge','当前视图仅显示文档'],
 ['documents?kind=reference','当前视图仅显示文档'],
 ['home?kind=knowledge','当前视图仅显示文档'],
 ['references?collection=todo','“参考资料”仅支持全部或参考资料集合'],
 ['favorites?tab=created','“我的收藏”固定显示收藏标签'],
 [`records/${rid}?from=documents&kind=knowledge`,'当前视图仅显示文档'],
 [`records/${rid}?from=references&collection=todo`,'“参考资料”仅支持全部或参考资料集合'],
])('fixed-view conflict %s is rejected before any list request',(route,message)=>{
 mocked.retainDisabledCache=true;
 const html=render(route);
 expect(html).toContain('data-state="validation"');expect(html).toContain(message);expect(html).toContain('重置筛选');expect(html).not.toContain('当前授权文档');expect(html).not.toContain('discovery-total');expect(html).not.toContain('待办集合');expect(html).not.toContain('添加收藏');expect(html).not.toContain('重新读取');expect(mocked.enabled).toHaveLength(5);expect(mocked.enabled.every(value=>!value)).toBe(true);
});
test('conflicting raw inputs have distinct request keys and compatible fixed-view intersections remain enabled',()=>{
 render('documents?kind=knowledge');const knowledgeKey=String(mocked.keys.find(key=>key[6]==='list')![7]);const knowledgeEnabled=mocked.enabled[mocked.keys.findIndex(key=>key[6]==='list')];
 mocked.keys=[];mocked.enabled=[];render('documents?kind=reference');const referenceKey=String(mocked.keys.find(key=>key[6]==='list')![7]);const referenceEnabled=mocked.enabled[mocked.keys.findIndex(key=>key[6]==='list')];
 mocked.keys=[];mocked.enabled=[];render('references?collection=all');const compatibleIndex=mocked.keys.findIndex(key=>key[6]==='list');
 expect(knowledgeKey).not.toBe(referenceKey);expect(knowledgeEnabled).toBe(false);expect(referenceEnabled).toBe(false);expect(mocked.enabled[compatibleIndex]).toBe(true);
});
