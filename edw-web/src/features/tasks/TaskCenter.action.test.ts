import {afterEach,expect,it,vi} from 'vitest';
import {forgetTaskAction,restoreTaskAction} from './task-action';

const scope='actor:11111111-1111-4111-8111-111111111111:1:1:1';
const taskId='22222222-2222-4222-8222-222222222222';
const key='original-retry-key';

function storage(){
 const values=new Map<string,string>();
 vi.stubGlobal('sessionStorage',{getItem:(name:string)=>values.get(name)??null,setItem:(name:string,value:string)=>{values.set(name,value)},removeItem:(name:string)=>{values.delete(name)}});
 return values;
}

afterEach(()=>vi.unstubAllGlobals());

it('restores an uncertain retry with its original key only in the revalidated scope',()=>{
 const values=storage();values.set('eid.task-action.v1',JSON.stringify({scope,taskId,kind:'retry',key}));
 expect(restoreTaskAction(scope)).toMatchObject({scope,taskId,kind:'retry',key,state:'unknown'});
 expect(restoreTaskAction(`${scope}:changed`)).toBeNull();
 expect(values.has('eid.task-action.v1')).toBe(false);
});

it('discards malformed task identities before exposing a saved action',()=>{
 const values=storage();values.set('eid.task-action.v1',JSON.stringify({scope,taskId:'../tasks/other',kind:'retry',key}));
 expect(restoreTaskAction(scope)).toBeNull();
 forgetTaskAction();expect(values.size).toBe(0);
});
