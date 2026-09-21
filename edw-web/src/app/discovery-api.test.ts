import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {executeDiscoveryCommand,getDiscovery,getDiscoveryDetail,getDiscoveryProjects,getDiscoverySummary,searchDiscovery,validDiscoveryQuery,type Command,type Context,type Item,type Storage} from './discovery-api';
import {REQUEST_TIMEOUT_MS} from './api';
const auth=vi.hoisted(()=>({value:'memory-only'}));
vi.mock('../auth/oidc',()=>({token:()=>auth.value}));
const wid='00000000-0000-4000-8000-000000000001';
const actor='00000000-0000-4000-8000-000000000002';
const rid='00000000-0000-4000-8000-000000000003';
const context:Context={actor_id:actor,workspace_id:wid,policy_epoch:[4,2,4]};
const item:Item={id:rid,workspace_id:wid,title:'实际文档',kind:'document',document_type:'technical',lifecycle:'DRAFT',visibility:'visible',created_by:actor,created_at:'2026-09-14T00:00:00Z',updated_at:'2026-09-18T02:00:00.123456+00:00',version_label:null,revision:1,resource_epoch:8,favorite:false,favorite_revision:0,participating:true};
const storage:Storage={metadata_bytes:321,measured_at:'2026-09-18T00:00:00Z',scope:'authorized_filtered_record_metadata',definition:'pg_column_size(discovery_record)+pg_column_size(access_resource.title)',visibility:'visible',attachment_bytes:null,quota_bytes:null};
const page=()=>({items:[item],total_count:1,next_cursor:null,context,storage});
const detail=()=>({item,context,resource_context:{...context,policy_epoch:[4,2,8]},actions:{favorite:true,restore:false,restore_policy_version:null},content_state:'metadata_only'});
const respond=(data:unknown)=>vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data})));
beforeEach(()=>{auth.value='memory-only';vi.stubGlobal('fetch',vi.fn());vi.stubGlobal('navigator',{onLine:true})});
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()});
test('discovery reads actual metadata with bearer and AND filters',async()=>{
 respond(page());const result=await getDiscovery(context,{tab:'created',kind:'document',document_type:'technical',lifecycle:'DRAFT',limit:20});
 expect(result.items).toEqual([item]);expect(result.storage.metadata_bytes).toBe(321);
 const [url,options]=vi.mocked(fetch).mock.calls[0];expect(url).toBe(`/api/v1/workspaces/${wid}/discovery?tab=created&kind=document&document_type=technical&lifecycle=DRAFT&limit=20`);expect(options?.headers).toMatchObject({Authorization:'Bearer memory-only'});
 expect(url).not.toContain('actor');expect(url).not.toContain('memory-only');
});
test('route filters are an exact bounded whitelist with no search or identity override',()=>{
 expect(validDiscoveryQuery('?tab=created&type=technical&status=DRAFT&collection=todo&from=home')).toBe(true);
 for(const collection of ['all','todo','references'])expect(validDiscoveryQuery(`?collection=${collection}&kind=reference&tab=favorites`)).toBe(true);
 for(const invalid of ['?query=secret','?actor_id=other','?tab=recent&tab=favorites','?tab=admin','?from=https://example.test','?kind=policy',`?x=${'x'.repeat(513)}`])expect(validDiscoveryQuery(invalid)).toBe(false);
});
test('search trims input, retains term only in body and maps fixed function routes',async()=>{
 respond({...page(),functions:[{id:'documents',route:'documents',title:'项目文档',workspace_id:wid}]});
 expect((await searchDiscovery(context,' 敏感标题 ',{})).functions).toHaveLength(1);
 const [url,options]=vi.mocked(fetch).mock.calls[0];expect(url).toBe(`/api/v1/workspaces/${wid}/search`);expect(options?.method).toBe('POST');expect(JSON.parse(String(options?.body))).toEqual({query:'敏感标题'});
});
test.each(['','  ','a'.repeat(129),'a\0b'])('invalid search is rejected before fetch (%s)',async query=>{await expect(searchDiscovery(context,query)).rejects.toMatchObject({failure:'validation'});expect(fetch).not.toHaveBeenCalled()});
test.each([
 ['astral', '\u{20bb7}'.repeat(300)],['astral maximum','\u{20bb7}'.repeat(512)],
 ['mixed maximum','a'.repeat(256)+'\u{20bb7}'.repeat(256)],['combining maximum','e\u0301'.repeat(256)],
])('title accepts Unicode code point bounds: %s',async(_label,title)=>{
 respond({...page(),items:[{...item,title}]});expect((await getDiscovery(context)).items[0].title).toBe(title);
});
test.each(['\u{20bb7}'.repeat(513),'a'.repeat(256)+'\u{20bb7}'.repeat(257),'e\u0301'.repeat(256)+'a'])('title rejects 513 code points',async title=>{
 respond({...page(),items:[{...item,title}]});await expect(getDiscovery(context)).rejects.toMatchObject({failure:'invalid-response'});
});
test.each(['\u{20bb7}'.repeat(128),'a'.repeat(64)+'\u{20bb7}'.repeat(64),'e\u0301'.repeat(64)])('search accepts exactly 128 code points and preserves the POST body',async query=>{
 respond({...page(),functions:[]});await searchDiscovery(context,` ${query} `);
 expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body)).query).toBe(query);
});
test.each(['\u{20bb7}'.repeat(129),'a'.repeat(64)+'\u{20bb7}'.repeat(65),'e\u0301'.repeat(64)+'a'])('search rejects 129 code points before fetch',async query=>{
 await expect(searchDiscovery(context,query)).rejects.toMatchObject({failure:'validation'});expect(fetch).not.toHaveBeenCalled();
});
test('optional version label uses the same Unicode code point bound',async()=>{
 const version_label='\u{20bb7}'.repeat(128);respond({...page(),items:[{...item,version_label}]});expect((await getDiscovery(context)).items[0].version_label).toBe(version_label);
 respond({...page(),items:[{...item,version_label:version_label+'a'}]});await expect(getDiscovery(context)).rejects.toMatchObject({failure:'invalid-response'});
});
test.each([{limit:51},{limit:1.1},{cursor:'bad/'},{actor_id:actor},{visibility:'deleted'},{tab:'admin'}])('invalid filter fails closed before fetch',async filters=>{await expect(getDiscovery(context,filters as never)).rejects.toThrow();expect(fetch).not.toHaveBeenCalled()});
test.each([
 {...context,actor_id:rid},{...context,workspace_id:rid},{...context,policy_epoch:[5,2,5]}
])('mismatched context never returns controlled data',async wrong=>{respond({...page(),context:wrong});await expect(getDiscovery(context)).rejects.toMatchObject({failure:'context'})});
test.each([
 {...item,id:'not-a-uuid'}, {...item,workspace_id:actor},{...item,created_at:'2026-02-30T00:00:00Z'},
 {...item,updated_at:'2026-09-18T00:00:00+02:00'},{...item,updated_at:'2026-09-18T25:00:00Z'},
 {...item,favorite:1},{...item,revision:0},{...item,resource_epoch:Number.MAX_SAFE_INTEGER+1},
 {...item,body:'forbidden extra body'},{...item,version_label:'a'.repeat(129)}, {...item,title:'a'.repeat(513)},
 {...item,kind:'policy'},{...item,lifecycle:'PUBLISHED'},{...item,visibility:'deleted'}, {...item,created_by:'unknown'}
])('invalid item contract fails closed',async row=>{respond({...page(),items:[row]});await expect(getDiscovery(context)).rejects.toMatchObject({failure:'invalid-response'})});
test.each([
 {...page(),items:[item,item],total_count:2},{...page(),items:Array(51).fill(item),total_count:51},
 {...page(),total_count:0},{...page(),total_count:'1'}, {...page(),next_cursor:'bad/'},
 {...page(),next_cursor:'a'.repeat(2049)},{...page(),extra:true},
 {...page(),storage:{...storage,quota_bytes:100}}, {...page(),storage:{...storage,metadata_bytes:-1}},
 {...page(),context:{...context,policy_epoch:[4,2]}}, {...page(),storage:{...storage,visibility:'recycled'}}
])('invalid page cannot become a displayed authorized collection',async value=>{respond(value);await expect(getDiscovery(context)).rejects.toThrow()});
test('response must obey caller filters and cursor must advance',async()=>{
 for(const filters of [{tab:'favorites'},{tab:'participating'},{kind:'knowledge'},{document_type:'report'},{lifecycle:'ARCHIVED'},{visibility:'recycled'}]){
  respond({...page(),items:[{...item,participating:false}]});await expect(getDiscovery(context,filters as never)).rejects.toThrow();
 }
 respond({...page(),next_cursor:'same'});await expect(getDiscovery(context,{cursor:'same'})).rejects.toThrow();
});
test('resource epoch is checked independently of workspace epoch and target ID',async()=>{
 respond(detail());expect((await getDiscoveryDetail(context,rid)).item.resource_epoch).toBe(8);
 respond({...detail(),resource_context:context});await expect(getDiscoveryDetail(context,rid)).rejects.toMatchObject({failure:'context'});
 respond({...detail(),item:{...item,id:actor}});await expect(getDiscoveryDetail(context,rid)).rejects.toThrow();
 respond({...detail(),content_state:'full'});await expect(getDiscoveryDetail(context,rid)).rejects.toThrow();
 respond({...detail(),actions:{favorite:true,restore:true,restore_policy_version:null}});await expect(getDiscoveryDetail(context,rid)).rejects.toThrow();
});
test('unknown and inaccessible resources receive the same generic denial without server text',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:'SECRET forbidden title'}}),{status:403}));
 await expect(getDiscoveryDetail(context,rid)).rejects.toMatchObject({failure:'forbidden',status:403,message:'当前目标不可访问，受保护内容已清除'});
});
test.each([[401,'authentication'],[409,'conflict'],[503,'unavailable'],[422,'validation']])('HTTP %s retains its distinct recoverable state',async(status,failure)=>{
 vi.mocked(fetch).mockResolvedValue(new Response('{}',{status:Number(status)}));await expect(getDiscovery(context)).rejects.toMatchObject({failure});
});
test('invalid cursor is distinct from input validation',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{code:'INVALID_CURSOR'}}),{status:422}));await expect(getDiscovery(context,{cursor:'old'})).rejects.toMatchObject({failure:'invalid-cursor'});
});
test.each(['headers','body'])('deadline aborts stalled %s, even if fetch ignores cancellation',async phase=>{
 vi.useFakeTimers();let signal:AbortSignal|undefined;const cancel=vi.fn();
 vi.mocked(fetch).mockImplementation(async(_url,init)=>{signal=init?.signal as AbortSignal;return phase==='headers'?await new Promise<Response>(()=>{}):new Response(new ReadableStream({cancel}))});
 const outcome=expect(getDiscovery(context)).rejects.toMatchObject({failure:'timeout'});await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);await outcome;
 expect(signal?.aborted).toBe(true);if(phase==='body')expect(cancel).toHaveBeenCalledOnce();expect(vi.getTimerCount()).toBe(0);
});
test('cancelled A cannot return after successful B',async()=>{
 let finish!:(response:Response)=>void;vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}));
 const cancel=new AbortController();const resultA=expect(searchDiscovery(context,'A',{},cancel.signal)).rejects.toMatchObject({failure:'cancelled'});
 cancel.abort();respond({...page(),functions:[]});expect((await searchDiscovery(context,'B')).items[0].id).toBe(rid);
 finish(new Response(JSON.stringify({data:{...page(),functions:[]}})));await resultA;
});
test('logout during request discards late success even when fetch ignores abort',async()=>{
 let finish!:(response:Response)=>void;vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}));
 const outcome=expect(getDiscovery(context)).rejects.toMatchObject({failure:'cancelled'});auth.value='';finish(new Response(JSON.stringify({data:page()})));await outcome;
});
test('offline is distinct from service failure and malformed payload',async()=>{
 vi.stubGlobal('navigator',{onLine:false});vi.mocked(fetch).mockRejectedValue(new TypeError('network'));await expect(getDiscovery(context)).rejects.toMatchObject({failure:'offline'});
});
test.each(['declared','stream'])('response byte budget is enforced for %s size',async mode=>{
 vi.mocked(fetch).mockResolvedValue(new Response('x'.repeat(65537),mode==='declared'?{headers:{'content-length':'65537'}}:undefined));await expect(getDiscovery(context)).rejects.toMatchObject({failure:'invalid-response'});
});
test('summary requires six unique null future metrics and actual scope',async()=>{
 const value={context,workspace:{id:wid,name:'Project',slug:'project',project_id:'p',customer_id:'c',product_id:'x',department:'d',classification:1},total_count:1,storage,week_new_documents:{value:1,window_start:'2026-09-14T00:00:00Z',window_end:'2026-09-18T00:00:00Z',definition:'authorized_filtered_documents_created_since_utc_monday'},todo_count:1,last_activity_at:null,future_panels:['review','ai_words','quality','templates','recommendations','creation'].map(id=>({id,value:null,state:'unavailable',reason:'尚未开放',owner:'2-1'}))};
 respond(value);expect((await getDiscoverySummary(context)).future_panels.every(p=>p.value===null)).toBe(true);
 respond({...value,future_panels:value.future_panels.map(p=>({...p,value:0}))});await expect(getDiscoverySummary(context)).rejects.toThrow();
 respond({...value,future_panels:Array(6).fill(value.future_panels[0])});await expect(getDiscoverySummary(context)).rejects.toThrow();
});
test('search functions cannot provide arbitrary redirects',async()=>{
 respond({...page(),functions:[{id:'documents',route:'https://example.test',title:'malicious',workspace_id:wid}]});await expect(searchDiscovery(context,'word')).rejects.toThrow();
});
test('unknown favorite outcome replays exact original key and body and consumes current state',async()=>{
 const command:Command={key:'same-original-command',resourceId:rid,action:'favorite.set',body:{favorite:true,expected_revision:0}};
 vi.mocked(fetch).mockRejectedValueOnce(new TypeError('connection lost'));await expect(executeDiscoveryCommand(context,command)).rejects.toMatchObject({failure:'unavailable'});
 const receipt={operation_id:actor,action:'favorite.set',resource_id:rid,replayed:true,occurred_at:'2026-09-18T00:00:00Z',context,current:{...item,favorite:false,favorite_revision:2}};
 respond(receipt);expect((await executeDiscoveryCommand(context,command)).current.favorite).toBe(false);
 for(const call of vi.mocked(fetch).mock.calls){expect(call[1]?.headers).toMatchObject({'Idempotency-Key':command.key});expect(JSON.parse(String(call[1]?.body))).toEqual(command.body)}
});
test('restore sends record revision and policy version; response binds command and resource',async()=>{
 const command:Command={key:'restore-original',resourceId:rid,action:'restore_visibility',body:{expected_revision:7,policy_version:'fixture-policy-v1'}};
 const receipt={operation_id:actor,action:'restore_visibility',resource_id:rid,replayed:false,occurred_at:'2026-09-18T00:00:00Z',context,current:{...item,lifecycle:'ARCHIVED'}};
 respond(receipt);expect((await executeDiscoveryCommand(context,command)).current.lifecycle).toBe('ARCHIVED');
 expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/v1/workspaces/${wid}/recycle/${rid}:restore`);
 respond({...receipt,resource_id:actor});await expect(executeDiscoveryCommand(context,command)).rejects.toThrow();
});
test('todo and references are explicit collections intersecting every other filter',async()=>{
 respond(page());await getDiscovery(context,{collection:'todo',tab:'participating',lifecycle:'DRAFT'});
 expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('collection=todo&tab=participating&lifecycle=DRAFT');
 respond({...page(),items:[{...item,kind:'knowledge',document_type:null}]});expect((await getDiscovery(context,{collection:'references'})).items[0].kind).toBe('knowledge');
 respond(page());await expect(getDiscovery(context,{collection:'references'})).rejects.toMatchObject({failure:'invalid-response'});
 respond({...page(),items:[{...item,lifecycle:'ARCHIVED'}]});await expect(getDiscovery(context,{collection:'todo'})).rejects.toThrow();
});
test('project activity uses bounded current contexts and sorts real page activity',async()=>{
 const ids=[wid,'00000000-0000-4000-8000-000000000004'];
 const makeSummary=(id:string)=>({context:{...context,workspace_id:id},workspace:{id,name:`Project ${id}`,slug:'project',project_id:'p',customer_id:'c',product_id:'x',department:'d',classification:1},total_count:1,storage,week_new_documents:{value:1,window_start:'2026-09-14T00:00:00Z',window_end:'2026-09-18T00:00:00Z',definition:'authorized_filtered_documents_created_since_utc_monday'},todo_count:1,last_activity_at:id===wid?null:'2026-09-18T00:00:00Z',future_panels:['review','ai_words','quality','templates','recommendations','creation'].map(id=>({id,value:null,state:'unavailable',reason:'尚未开放',owner:'2-1'}))});
 vi.mocked(fetch).mockImplementation(async url=>{
  if(String(url).startsWith('/api/v1/access/workspaces'))return new Response(JSON.stringify({data:{workspaces:ids.map(id=>({...context,workspace_id:id,name:'Project',slug:'p',display_name:'Actor',department:'d',roles:['author'],operations:['workspace:read'],clearance:1})),next_cursor:null}}));
  const id=String(url).split('/')[4];return new Response(JSON.stringify({data:makeSummary(id)}));
 });
 const result=await getDiscoveryProjects(context);expect(result.items.map(p=>p.workspace.id)).toEqual([...ids].reverse());expect(fetch).toHaveBeenCalledTimes(3);expect(result.next_cursor).toBeNull();
});
