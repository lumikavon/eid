import { token } from '../auth/oidc';
import { boundedJson } from '../http/bounded-json';
export type Account={actor_id:string;subject:string;display_name:string;department:string;workspace_id:string;workspace_slug:string;workspace_name:string};
export type AccountRequestErrorKind='authentication'|'forbidden'|'transient'|'invalid-response'|'validation';
export class AccountRequestError extends Error{
  constructor(message:string,readonly kind:AccountRequestErrorKind,readonly status?:number){super(message);this.name='AccountRequestError'}
}
export const isAuthenticationRejection=(error:unknown):error is AccountRequestError=>error instanceof AccountRequestError&&error.kind==='authentication';
export const isWorkspaceForbidden=(error:unknown):error is AccountRequestError=>error instanceof AccountRequestError&&error.kind==='forbidden';
export const REQUEST_TIMEOUT_MS=8000;
const MAX_READINESS_BODY_BYTES=64*1024;
const MAX_ACCOUNT_BODY_BYTES=64*1024;
const readinessChecks=['postgres','redis','rabbitmq','s3','keycloak','worker','scheduler'] as const;
type ReadinessCheck=typeof readinessChecks[number];

const readinessReasons:Record<ReadinessCheck,Record<string,string>>={
  postgres:{unavailable:'数据库无法连接，请检查 PostgreSQL 服务与连接配置',timeout:'数据库检查超时，请检查 PostgreSQL 服务是否阻塞',marker_schema_or_privilege_mismatch:'数据库环境、结构或读取权限不匹配，请运行隔离校验并检查迁移与授权'},
  redis:{unavailable:'缓存服务无法连接，请检查 Redis 服务与连接配置',timeout:'缓存检查超时，请检查 Redis 服务是否阻塞'},
  rabbitmq:{unavailable:'消息队列无法连接，请检查 RabbitMQ 服务与连接配置',timeout:'消息队列检查超时，请检查 RabbitMQ 服务是否阻塞'},
  s3:{unavailable:'对象存储无法连接，请检查 S3 服务与连接配置',timeout:'对象存储检查超时，请检查 S3 服务是否阻塞',bucket_missing:'对象存储缺少项目专属存储桶，请检查本地存储初始化'},
  keycloak:{
    unavailable:'身份服务无法连接，请检查 Keycloak 服务与连接配置',
    timeout:'身份服务检查超时，请检查 Keycloak 服务是否阻塞',
    audience_mismatch:'身份服务 audience 配置不匹配，请检查本地 OIDC 配置',
    jwks_url_mismatch:'身份服务 JWKS 地址不匹配，请检查本地 OIDC 配置',
    malformed_discovery:'身份服务发现文档无效，请检查 Keycloak realm 配置',
    issuer_mismatch:'身份服务 issuer 不匹配，请检查公开访问地址与 realm 配置',
    jwks_uri_mismatch:'身份服务发现的 JWKS 地址不匹配，请检查 Keycloak realm 配置',
    malformed_jwks:'身份服务签名密钥响应无效，请检查 Keycloak realm 密钥',
    keys_missing:'身份服务缺少签名密钥，请检查 Keycloak realm 密钥',
    usable_signing_key_missing:'身份服务缺少可用的 RS256 验签密钥，请检查 Keycloak realm 密钥',
    admin_url_mismatch:'身份服务管理地址不匹配，请检查 Keycloak 管理端点配置',
    monitor_client_mismatch:'身份服务就绪监控客户端不匹配，请检查 Keycloak 监控客户端配置',
    monitor_token_unavailable:'身份服务监控令牌无法获取，请检查 Keycloak 监控客户端凭据',
    monitor_role_mismatch:'身份服务监控客户端角色不匹配，请检查 Keycloak realm-management 角色配置',
    monitor_permission_denied:'身份服务监控客户端权限不足，请检查 Keycloak 管理读取权限',
    realm_configuration_mismatch:'身份服务 realm 配置不匹配，请检查 Keycloak realm 配置',
    client_configuration_mismatch:'身份服务 Web 客户端配置不匹配，请检查 Keycloak 客户端配置',
    audience_mapper_mismatch:'身份服务 audience 映射配置不匹配，请检查 Keycloak 协议映射器配置',
  },
  worker:{unavailable:'后台任务服务无法连接，请检查 Worker 与消息队列连接',timeout:'后台任务检查超时，请检查 Worker 是否阻塞'},
  scheduler:{unavailable:'任务调度器无法连接，请检查调度服务',timeout:'任务调度器检查超时，请检查调度服务是否阻塞',marker_schema_or_privilege_mismatch:'任务调度器环境、结构或读取权限不匹配，请检查迁移与授权',lease_inactive:'任务调度器租约未激活，请检查调度服务状态'},
};

const isPlainObject=(value:unknown):value is Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null);

function readinessFailure(body:unknown):string{
  if(!isPlainObject(body)||!isPlainObject(body.error)||!isPlainObject(body.error.details)||!isPlainObject(body.error.details.checks))return '本地依赖尚未就绪';
  const checks=body.error.details.checks;
  if(Object.keys(checks).length!==readinessChecks.length||!readinessChecks.every(name=>typeof checks[name]==='string'))return '本地依赖尚未就绪';
  const reasons:string[]=[];
  for(const name of readinessChecks){
    const status=checks[name] as string;if(status==='ready')continue;
    const reason=readinessReasons[name][status];
    if(!reason)return '本地依赖尚未就绪：依赖检查返回未知状态，请查看 API 服务日志';
    reasons.push(reason);
  }
  return reasons.length?`本地依赖尚未就绪：${reasons.join('；')}`:'本地依赖尚未就绪';
}

async function boundedFetch<T>(input:RequestInfo|URL,init:RequestInit,timeoutMessage:string,consume:(response:Response)=>Promise<T>):Promise<T>{
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
  try{return await consume(await fetch(input,{...init,signal:controller.signal}))}
  catch(error){if(controller.signal.aborted)throw new Error(timeoutMessage);throw error}
  finally{clearTimeout(timeout)}
}

export async function getMe():Promise<Account>{
  const value=token(); if(!value) throw new Error('尚未登录');
  try{
    return await boundedFetch('/api/v1/me',{headers:{Authorization:`Bearer ${value}`,'X-Request-ID':crypto.randomUUID()}},'账户请求超时，请稍后重试',async response=>{
      if(!response.ok){
        if(response.status===401)throw new AccountRequestError('登录已失效，请重新登录','authentication',response.status);
        if(response.status===403)throw new AccountRequestError('当前账户没有工作区访问权限','forbidden',response.status);
        let body:unknown;
        try{body=await boundedJson(response,MAX_ACCOUNT_BODY_BYTES,'账户错误响应无效')}catch{throw new AccountRequestError(`账户请求失败 (${response.status})`,'transient',response.status)}
        const error=isPlainObject(body)&&isPlainObject(body.error)?body.error:undefined;
        const message=error&&typeof error.message==='string'?error.message:`账户请求失败 (${response.status})`;
        throw new AccountRequestError(message,'transient',response.status);
      }
      let body:unknown;
      try{body=await boundedJson(response,MAX_ACCOUNT_BODY_BYTES,'账户响应格式无效')}catch{throw new AccountRequestError('账户响应格式无效','invalid-response')}
      const account=isPlainObject(body)?body.data:undefined;
      const fields=['actor_id','subject','display_name','department','workspace_id','workspace_slug','workspace_name'];
      if(!isPlainObject(account)||!fields.every(field=>typeof account[field]==='string'))throw new AccountRequestError('账户响应格式无效','invalid-response');
      return account as Account;
    });
  }catch(error){
    if(error instanceof AccountRequestError)throw error;
    throw new AccountRequestError(error instanceof Error?error.message:'账户请求失败','transient');
  }
}
export async function getReadiness():Promise<string>{
  return boundedFetch('/health/ready',{},'依赖状态检查超时，请稍后重试',async response=>{
    const body=await boundedJson(response,MAX_READINESS_BODY_BYTES,'依赖状态响应无效');
    if(!response.ok)throw new Error(response.status===503?readinessFailure(body):'本地依赖尚未就绪');
    const checks=isPlainObject(body)?body.checks:undefined;
    if(!isPlainObject(body)||body.status!=='ready'||!isPlainObject(checks)||Object.keys(checks).length!==readinessChecks.length||!readinessChecks.every(key=>checks[key]==='ready'))throw new Error('依赖状态响应无效');
    return '依赖已就绪';
  });
}
