import {spawn,type ChildProcessWithoutNullStreams} from 'node:child_process';
import {resolve} from 'node:path';

type User={username:string;subject:string;actor_id:string;resource_id:string};
export type DiscoveryFixture={
 run_id:string;users:Record<string,User>;workspaces:{a:string;b:string};records:Record<string,string>;
 policy_version:string;definition_sha256:string;stateDirectory:string;accessWorkspaces:string[];
 boundary:Record<string,string>;runtime:Record<string,unknown>;usage:Record<string,unknown>;
};
const python=resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
export const guardTimeout=240000;
export type FixtureLease={fixture:DiscoveryFixture;assertHeld:()=>void;release:()=>Promise<void>;
 onLost:(callback:()=>void)=>void};

/** Collection is offline. Only beforeAll acquires and consumes a real fresh run. */
export async function selectedDiscoveryFixture():Promise<FixtureLease>{
 const runId=process.env.EID_DISCOVERY_FIXTURE_RUN;
 if(!runId||!/^[a-z0-9][a-z0-9-]{0,31}$/.test(runId))throw new Error('Select one explicit NEW EID_DISCOVERY_FIXTURE_RUN.');
 if(process.env.EID_ENVIRONMENT_CONFIG!=='deployment/environments/seadee-develop.yaml'||process.env.EID_RUN_DISCOVERY_UX!=='1')throw new Error('Explicit seadee-develop selector and EID_RUN_DISCOVERY_UX=1 required.');
 const child:ChildProcessWithoutNullStreams=spawn(python,['-m','scripts.verify_discovery_fixtures','--run-id',runId],{cwd:process.cwd(),stdio:'pipe',windowsHide:true});
 let failure:Error|undefined,releasing=false,stderr='',bytes=0;
 const lost=new Set<()=>void>();
 const fail=(error:Error)=>{failure??=error;for(const callback of lost)callback()};
 child.once('error',error=>fail(error));
 child.once('exit',(code,signal)=>{if(!releasing)fail(new Error(`Discovery fixture lock lost: ${code}/${signal}; ${stderr}`))});
 child.stdin.on('error',error=>fail(error));
 child.stderr.setEncoding('utf8');child.stderr.on('data',(value:string)=>{stderr=(stderr+value).slice(-8000)});
 const fixture=await new Promise<DiscoveryFixture>((accept,reject)=>{
  let stdout='',ready=false;
  const stop=(error:Error)=>{clearTimeout(timer);fail(error);child.kill();reject(error)};
  const timer=setTimeout(()=>stop(new Error('Discovery preflight timed out; preserve any consumed marker.')),guardTimeout);
  child.once('error',stop);
  child.once('exit',()=>{if(!ready){clearTimeout(timer);reject(failure??new Error(`Discovery preflight exited: ${stderr}`))}});
  child.stdout.setEncoding('utf8');child.stdout.on('data',(value:string)=>{
   if(ready)return;bytes+=Buffer.byteLength(value);stdout+=value;
   if(bytes>128*1024){stop(new Error('Discovery preflight output exceeded bound'));return}
   const end=stdout.indexOf('\n');if(end<0)return;
   try{
    const result=JSON.parse(stdout.slice(0,end)) as DiscoveryFixture;
    if(result.run_id!==runId||!result.usage||!result.runtime||!result.boundary)throw new Error('Invalid guarded discovery response');
    clearTimeout(timer);ready=true;accept(result);
   }catch(error){stop(error instanceof Error?error:new Error('Invalid discovery preflight JSON'))}
  });
 });
 const assertHeld=()=>{
  if(failure)throw failure;
  if(releasing||child.exitCode!==null||child.signalCode!==null||child.killed||child.stdin.destroyed||child.stdin.writableEnded)throw new Error('Discovery fixture lock is not held');
 };
 assertHeld();
 return {fixture,assertHeld,onLost:callback=>{lost.add(callback);if(failure)callback()},release:async()=>{
  assertHeld();releasing=true;
  await new Promise<void>((accept,reject)=>{
   const timer=setTimeout(()=>{child.kill();reject(new Error('Discovery final candidate verification timed out'))},guardTimeout);
   child.once('exit',(code,signal)=>{clearTimeout(timer);if(code===0&&signal===null)accept();else reject(new Error(`Discovery release failed: ${code}/${signal}; ${stderr}`))});
   child.stdin.end();
  });
  if(failure)throw failure;
 }};
}

export function evidencePath(fixture:DiscoveryFixture,name:string){return `test-results/story-1-3-evidence/${fixture.run_id}/${name}`}
