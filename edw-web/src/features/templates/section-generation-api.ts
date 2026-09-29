import type {WorkspaceAccess} from '../../app/access-api';
import {token} from '../../auth/oidc';
import {boundedJson} from '../../http/bounded-json';

export type SectionInputs={section_id:string;document_version_id:string;document_revision:number;pack_id:string|null;pack_job_id:string|null;gaps:string[]};
export type SectionScope={sections:{id:string;title:string}[];document_version_id:string;document_revision:number};
export type SectionJob={id:string;section_id:string;state:string;stage:string;attempt:number;error_code:string|null;missing:string[];proposal_hash:string|null;updated_at:string;proposal?:{ast:{content:{text:string}}[];claims:{source_id:string;locator:string}[];missing:string[];provenance:{model_id:string;pack_id:string}}};

async function request(current:WorkspaceAccess,documentId:string,path:string,method='GET',body?:object):Promise<Record<string,unknown>>{
 const access=token();if(!access)throw new Error('登录已失效');
 const response=await fetch(`/api/v1/workspaces/${current.workspace_id}/documents/${documentId}/generation${path}`,{
  method,headers:{Authorization:`Bearer ${access}`,'Content-Type':'application/json','X-Request-ID':crypto.randomUUID()},
  body:body?JSON.stringify(body):undefined,cache:'no-store'});
 if(!response.ok)throw new Error(`章节任务不可用 (${response.status})`);
 const data=await boundedJson(response,256*1024,'章节任务回执无效');
 if(!data||typeof data!=='object'||!('data' in data)||!data.data||typeof data.data!=='object')throw new Error('章节任务回执无效');
 if(token()!==access)throw new Error('授权已变化，请重新读取');
 return data.data as Record<string,unknown>;
}
export const sectionInputs=(current:WorkspaceAccess,documentId:string,sectionId:string)=>request(current,documentId,`/sections/${sectionId}/inputs`) as Promise<SectionInputs>;
export const generationScope=(current:WorkspaceAccess,documentId:string)=>request(current,documentId,'/scope') as Promise<SectionScope>;
export const listSectionJobs=(current:WorkspaceAccess,documentId:string)=>request(current,documentId,'/jobs') as Promise<{items:SectionJob[]}>;
export const startSection=(current:WorkspaceAccess,documentId:string,body:object)=>request(current,documentId,'/sections','POST',body) as Promise<SectionJob>;
export const observeSection=(current:WorkspaceAccess,documentId:string,jobId:string)=>request(current,documentId,`/sections/${jobId}`) as Promise<SectionJob>;
export const cancelSection=(current:WorkspaceAccess,documentId:string,jobId:string)=>request(current,documentId,`/sections/${jobId}/cancel`,'POST') as Promise<SectionJob>;
