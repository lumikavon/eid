import {validId} from '../../app/discovery-api';

export type TaskAction={scope:string;taskId:string;kind:'cancel'|'retry';key:string;state:'confirm'|'pending'|'unknown'|'resolved';message:string;outcomeTaskId?:string};
const actionStorageKey='eid.task-action.v1';

export function forgetTaskAction(){try{sessionStorage.removeItem(actionStorageKey)}catch{/* Memory state remains authoritative when storage is unavailable. */}}

export function restoreTaskAction(scope:string):TaskAction|null{
 try{const raw=sessionStorage.getItem(actionStorageKey);if(!raw)return null;const saved:unknown=JSON.parse(raw);
  if(!saved||typeof saved!=='object'||Array.isArray(saved))return null;
  const value=saved as Record<string,unknown>;
  if(value.scope!==scope||!validId(value.taskId)||!['cancel','retry'].includes(String(value.kind))||typeof value.key!=='string'||!/^[A-Za-z0-9._:-]{1,128}$/.test(value.key)){forgetTaskAction();return null}
  const kind=value.kind as TaskAction['kind'];return {scope,taskId:value.taskId,kind,key:value.key,state:'unknown',message:kind==='retry'?'上次提交结果未知。请用同一操作标识核对，不要创建新的重试。':'上次取消提交结果未知。先刷新任务状态，不要盲目重复提交。'};
 }catch{forgetTaskAction();return null}
}

export function rememberTaskAction(action:TaskAction){try{sessionStorage.setItem(actionStorageKey,JSON.stringify({scope:action.scope,taskId:action.taskId,kind:action.kind,key:action.key}))}catch{/* The current tab still retains the action in memory. */}}
