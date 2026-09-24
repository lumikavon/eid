import {afterEach,describe,expect,it,vi} from 'vitest';
import {getEventPage,getNotifications,getTask,getTasks,getUnreadNotification,markNotificationRead,retryTask,streamTask} from './task-api';

vi.mock('../auth/oidc',()=>({token:()=> 'memory-only-token'}));
const workspace='11111111-1111-4111-8111-111111111111';
const taskId='22222222-2222-4222-8222-222222222222';
const notificationId='33333333-3333-4333-8333-333333333333';
const timestamp='2026-09-24T12:00:00Z';
const json=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
const snapshot=(overrides:Record<string,unknown>={})=>({task_id:taskId,state:'FAILED',stage:'failed',category:'integration',operation:'inventory',parent_task_id:null,attempt:1,fence_token:1,current_seq:2,retention_floor:1,progress:null,result_ref:null,error:'ATTEMPTS_EXHAUSTED',error_class:'ATTEMPTS_EXHAUSTED',next_retry_at:null,cancel_requested:false,external_effect_state:'none',created_at:timestamp,updated_at:timestamp,status_url:`/api/v1/workspaces/${workspace}/tasks/${taskId}`,result_url:`/api/v1/workspaces/${workspace}/tasks/${taskId}/result`,can_cancel:false,can_retry:true,action_reason:'TASK_TERMINAL',...overrides});
const notification=(read_at:string|null=null)=>({notification_id:notificationId,task_id:taskId,event_seq:2,event_type:'task.failed',state:'FAILED',created_at:timestamp,read_at});
afterEach(()=>vi.unstubAllGlobals());

describe('task observation wire boundaries',()=>{
 it('preserves a real unsupported category and unknown progress without inventing a handler',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(json({data:[snapshot({category:'generation',operation:'draft',result_url:null,can_retry:false,action_reason:'OPERATION_UNAVAILABLE'})],next_cursor:null})));
  const page=await getTasks(workspace);
  expect(page.data[0]).toMatchObject({category:'generation',can_retry:false,progress:null,action_reason:'OPERATION_UNAVAILABLE'});
 });
 it('accepts a non-inventory running stage without exposing an inventory result URL',async()=>{
  const row=snapshot({state:'RUNNING',stage:'working',category:'generation',operation:'draft',result_url:null,error:null,error_class:null,can_retry:false,action_reason:'OPERATION_UNAVAILABLE'});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(json({data:row})));
  expect(await getTask(workspace,taskId)).toMatchObject({stage:'working',result_url:null,progress:null});
 });
 it('accepts an explicit retention reset and rejects a nonconsecutive event page',async()=>{
  const fetcher=vi.fn().mockResolvedValueOnce(json({data:[],current_seq:5,retention_floor:4,reset_required:true})).mockResolvedValueOnce(json({data:[{task_id:taskId,seq:4,event_type:'task.failed',state:'FAILED',occurred_at:timestamp}],current_seq:5,retention_floor:1,reset_required:false}));
  vi.stubGlobal('fetch',fetcher);
  expect((await getEventPage(workspace,taskId,0)).reset_required).toBe(true);
  await expect(getEventPage(workspace,taskId,1)).rejects.toMatchObject({failure:'invalid-response'});
 });
 it('sends bearer and cursor in headers and never in the SSE URL',async()=>{
  const bytes=new TextEncoder().encode(`id: 3\nevent: task\ndata: ${JSON.stringify({task_id:taskId,seq:3,event_type:'task.failed',state:'FAILED',occurred_at:timestamp})}\n\n`);
  const fetcher=vi.fn().mockResolvedValue(new Response(new ReadableStream({start(controller){controller.enqueue(bytes);controller.close()}}),{headers:{'Content-Type':'text/event-stream'}}));
  vi.stubGlobal('fetch',fetcher);const received:number[]=[];
  await streamTask(workspace,taskId,2,item=>{received.push(item.seq)},()=>{},new AbortController().signal);
  expect(received).toEqual([3]);
  const [url,init]=fetcher.mock.calls[0] as [string,RequestInit];
  expect(url).toBe(`/api/v1/workspaces/${workspace}/tasks/${taskId}/events`);
  expect(init.headers).toMatchObject({Authorization:'Bearer memory-only-token','Last-Event-ID':'2'});
 });
 it('rejects revoked event access before consuming a stream',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(json({error:{code:'ACCESS_DENIED'}},403)));
  await expect(streamTask(workspace,taskId,0,()=>{},()=>{},new AbortController().signal)).rejects.toMatchObject({failure:'forbidden',status:403});
 });
 it('separates expired login from forbidden workspace access',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(json({},401)).mockResolvedValueOnce(json({},403)));
  await expect(getTasks(workspace)).rejects.toMatchObject({failure:'authentication',status:401});
  await expect(getTasks(workspace)).rejects.toMatchObject({failure:'forbidden',status:403});
 });
 it('consumes many complete SSE frames in one read while rejecting an oversized unfinished frame',async()=>{
  const frames=Array.from({length:150},(_,index)=>{const seq=index+3;return `id: ${seq}\nevent: task\ndata: ${JSON.stringify({task_id:taskId,seq,event_type:'task.failed',state:'FAILED',occurred_at:timestamp})}\n\n`}).join('');
  expect(frames.length).toBeGreaterThan(16384);
  const streamed=(text:string)=>new Response(new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode(text));controller.close()}}),{headers:{'Content-Type':'text/event-stream'}});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(streamed(frames)).mockResolvedValueOnce(streamed('x'.repeat(16385))));
  const received:number[]=[];await streamTask(workspace,taskId,2,item=>{received.push(item.seq)},()=>{},new AbortController().signal);
  expect(received).toHaveLength(150);expect(received[0]).toBe(3);expect(received.at(-1)).toBe(152);
  await expect(streamTask(workspace,taskId,2,()=>{},()=>{},new AbortController().signal)).rejects.toMatchObject({failure:'invalid-response'});
 });
 it('keeps the supplied retry identity in the wire request',async()=>{
  const childId='44444444-4444-4444-8444-444444444444';const retryKey='same-operation-key';
  const child=snapshot({task_id:childId,parent_task_id:taskId,status_url:`/api/v1/workspaces/${workspace}/tasks/${childId}`,result_url:`/api/v1/workspaces/${workspace}/tasks/${childId}/result`});
  const fetcher=vi.fn().mockResolvedValue(json({data:child},202));vi.stubGlobal('fetch',fetcher);
  expect((await retryTask(workspace,taskId,retryKey)).parent_task_id).toBe(taskId);
  const [,init]=fetcher.mock.calls[0] as [string,RequestInit];expect(init.headers).toMatchObject({'Idempotency-Key':retryKey});
 });
 it('keeps notification read state separate from the referenced task state',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(json({data:[notification()],next_cursor:null})).mockResolvedValueOnce(json({data:notification(timestamp)})));
  const before=await getNotifications(workspace);const after=await markNotificationRead(workspace,notificationId);
  expect(before.data[0].read_at).toBeNull();expect(after.read_at).toBe(timestamp);expect(after.state).toBe('FAILED');
 });
 it('uses the authorized unread result and rejects an incomplete response',async()=>{
  const fetcher=vi.fn().mockResolvedValueOnce(json({has_unread:true})).mockResolvedValueOnce(json({has_unread:false})).mockResolvedValueOnce(json({}));
  vi.stubGlobal('fetch',fetcher);
  expect(await getUnreadNotification(workspace)).toBe(true);
  expect(await getUnreadNotification(workspace)).toBe(false);
  await expect(getUnreadNotification(workspace)).rejects.toMatchObject({failure:'invalid-response'});
  expect(fetcher.mock.calls[0][0]).toBe(`/api/v1/workspaces/${workspace}/tasks/notifications/unread`);
 });
});
