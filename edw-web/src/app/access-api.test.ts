import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {getWorkspace,getWorkspaces,getMembers,getResource,saveMember} from './access-api';
import {REQUEST_TIMEOUT_MS} from './api';
vi.mock('../auth/oidc',()=>({token:()=> 'memory-only'}));
beforeEach(()=>{vi.stubGlobal('fetch',vi.fn())});
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()});
const workspace={workspace_id:'w',actor_id:'a',name:'Project',slug:'project',display_name:'Member',department:'Engineering',roles:['author'],clearance:1,policy_epoch:[1,2,3],operations:['workspace:read']};
test('workspace selection returns verified policy epochs and carries only bearer identity',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:workspace})));
 expect(await getWorkspace('w')).toEqual(workspace);
 const [url,init]=vi.mocked(fetch).mock.calls[0];expect(url).toBe('/api/v1/access/workspaces/w');
 expect(init?.headers).toMatchObject({Authorization:'Bearer memory-only'});
 expect(String(url)).not.toContain('memory-only');
});
test.each([401,403,409,503])('policy failure %s does not become an allowed response',async status=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:workspace}),{status}));
 await expect(getWorkspace('w')).rejects.toMatchObject({status});
});
test.each([null,{...workspace,policy_epoch:[1,2]},{...workspace,policy_epoch:[1,'2',3]},{...workspace,clearance:9}])('malformed context fails closed',async data=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data})));
 await expect(getWorkspace('w')).rejects.toThrow();
});
test('workspace list and membership responses are bounded',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{workspaces:Array(51).fill(workspace),next_cursor:null}})));
 await expect(getWorkspaces()).rejects.toThrow();
 vi.mocked(fetch).mockResolvedValue(new Response('x'.repeat(262145)));
 await expect(getMembers('w')).rejects.toThrow();
});

test('member responses accept fifty policies and reject fifty one',async()=>{
 const member={identity_id:'member',display_name:'Member',roles:['author'],active:true,clearance:1,project_scope:['p'],customer_scope:['c'],product_scope:['x'],department_scope:['d'],owner_scope:'self',approval_states:['draft'],valid_from:'2026-09-01T00:00:00Z',valid_until:null};
 for(const size of [50,51]){
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{members:Array(size).fill(member),policy_epoch:[1,1,1],next_cursor:null}})));
  if(size===50)expect((await getMembers('w')).members).toHaveLength(50);
  else await expect(getMembers('w')).rejects.toThrow('成员响应格式无效');
 }
});

test('resource response identity must match the requested resource',async()=>{
 const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{id,title:'Resource',kind:'policy'}})));
 expect((await getResource('w',id.toUpperCase())).id).toBe(id);
 expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/v1/access/workspaces/w/resources/${id.toUpperCase()}`);
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',title:'Resource',kind:'policy'}})));
 await expect(getResource('w',id)).rejects.toThrow('资源响应格式无效');
});

test('workspace enumeration consumes bounded pages beyond 200 without losing earlier projects',async()=>{
 const ids=Array.from({length:206},(_,n)=>`00000000-0000-0000-0000-${(n+1).toString(16).padStart(12,'0')}`);
 vi.mocked(fetch).mockImplementation(async input=>{
  const cursor=new URL(String(input),'http://local').searchParams.get('after');
  const start=cursor?ids.indexOf(cursor)+1:0;const page=ids.slice(start,start+50);
  return new Response(JSON.stringify({data:{workspaces:page.map(workspace_id=>({...workspace,workspace_id})),next_cursor:start+50<ids.length?page.at(-1):null}}));
 });
 const seen:string[]=[];let cursor:string|undefined;
 do{const page=await getWorkspaces(cursor);seen.push(...page.workspaces.map(p=>p.workspace_id));cursor=page.next_cursor??undefined}while(cursor);
 expect(seen).toEqual(ids);
 expect(fetch).toHaveBeenCalledTimes(5);
});

test('a repeated workspace cursor fails closed instead of looping',async()=>{
 const next_cursor='00000000-0000-0000-0000-000000000001';
 vi.mocked(fetch).mockImplementation(async()=>new Response(JSON.stringify({data:{workspaces:[],next_cursor}})));
 await expect(getWorkspaces(next_cursor)).rejects.toThrow('项目响应格式无效');
 expect(fetch).toHaveBeenCalledTimes(1);
});

test('workspace selection resolves one page without automatically fetching the next',async()=>{
 const next_cursor='00000000-0000-0000-0000-000000000001';
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{workspaces:[workspace],next_cursor}})));
 expect(await getWorkspaces()).toEqual({workspaces:[workspace],next_cursor});
 expect(fetch).toHaveBeenCalledTimes(1);
});

test.each(['headers','body'])('access deadline aborts stalled %s and returns a retryable timeout',async phase=>{
 vi.useFakeTimers();let signal:AbortSignal|undefined;
 vi.mocked(fetch).mockImplementation(async(_url,init)=>{
  signal=init?.signal as AbortSignal;
  if(phase==='headers')return new Promise((_resolve,reject)=>signal!.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError'))));
  return new Response(new ReadableStream({start(controller){signal!.addEventListener('abort',()=>controller.error(new DOMException('aborted','AbortError')))}}));
 });
 const outcome=expect(getWorkspace('w')).rejects.toMatchObject({message:'权限请求超时，请重试',kind:'transient'});
 await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
 await outcome;expect(signal?.aborted).toBe(true);expect(vi.getTimerCount()).toBe(0);
});
test('member writes contain only editable policy and current epoch, never actor overrides',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{audit_id:'audit',workspace_epoch:5}})));
 await saveMember('w',{identity_id:'member',display_name:'Member',roles:['author'],active:false,clearance:1,project_scope:['p'],customer_scope:['c'],product_scope:['x'],department_scope:['d'],owner_scope:'self',approval_states:['draft'],valid_from:'2026-09-01T00:00:00Z',valid_until:null},[4,1,4]);
 const body=JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string);
 expect(body.expected_epoch).toEqual([4,1,4]);expect(body.active).toBe(false);
 expect(body).not.toHaveProperty('display_name');expect(body).not.toHaveProperty('actor_id');
});

test('422 identifies invalid input instead of an unavailable permission service',async()=>{
 vi.mocked(fetch).mockResolvedValue(new Response('{}',{status:422}));
 await expect(getWorkspace('w')).rejects.toMatchObject({kind:'validation',status:422,message:expect.stringContaining('输入格式无效')});
});

test.each(['invalid','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001'])('member cursor %s cannot repeat, regress or have an invalid shape',async next_cursor=>{
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({data:{members:[],policy_epoch:[1,1,1],next_cursor}})));
 await expect(getMembers('w','00000000-0000-0000-0000-000000000002')).rejects.toThrow('成员响应格式无效');
});
