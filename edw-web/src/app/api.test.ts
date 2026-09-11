import {afterEach,beforeEach,expect,test,vi} from 'vitest';

vi.mock('../auth/oidc',()=>({token:()=> 'in-memory-token'}));

beforeEach(()=>{
  vi.resetModules();vi.useFakeTimers();
  vi.stubGlobal('window',{location:{origin:'http://localhost:18080'}});
  vi.stubGlobal('fetch',vi.fn());
});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()});

test('readiness aborts a stalled request before the next poll and reports a readable timeout',async()=>{
  const {getReadiness,REQUEST_TIMEOUT_MS}=await import('./api');
  expect(REQUEST_TIMEOUT_MS).toBeLessThan(15000);
  let signal:AbortSignal|undefined;
  vi.mocked(fetch).mockImplementation((_input,init)=>new Promise((_resolve,reject)=>{
    signal=init?.signal??undefined;
    signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true});
  }));

  const request=getReadiness();
  const rejection=expect(request).rejects.toThrow('依赖状态检查超时，请稍后重试');
  await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS-1);
  expect(signal?.aborted).toBe(false);
  await vi.advanceTimersByTimeAsync(1);
  await rejection;
  expect(signal?.aborted).toBe(true);
});

test('a completed readiness request clears its deadline',async()=>{
  const {getReadiness,REQUEST_TIMEOUT_MS}=await import('./api');
  let signal:AbortSignal|undefined;
  vi.mocked(fetch).mockImplementation((_input,init)=>{signal=init?.signal??undefined;return Promise.resolve(new Response('{"status":"ready","checks":{"postgres":"ready","redis":"ready","rabbitmq":"ready","s3":"ready","keycloak":"ready","worker":"ready"}}'))});

  await expect(getReadiness()).resolves.toBe('依赖已就绪');
  await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
  expect(signal?.aborted).toBe(false);
});

test('the deadline also covers a response body stalled after headers',async()=>{
  const {getReadiness,REQUEST_TIMEOUT_MS}=await import('./api');
  let signal:AbortSignal|undefined;
  vi.mocked(fetch).mockImplementation((_input,init)=>{
    signal=init?.signal??undefined;
    const stream=new ReadableStream({start(controller){signal?.addEventListener('abort',()=>controller.error(new DOMException('aborted','AbortError')),{once:true})}});
    return Promise.resolve(new Response(stream));
  });
  const rejected=expect(getReadiness()).rejects.toThrow('依赖状态检查超时，请稍后重试');
  await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
  await rejected;
  expect(signal?.aborted).toBe(true);
});

test('an HTTP 200 with no readiness payload is not shown as ready',async()=>{
  const {getReadiness}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response('{}'));
  await expect(getReadiness()).rejects.toThrow('依赖状态响应无效');
});

test('an HTTP 200 with invalid JSON reports a stable readable response error',async()=>{
  const {getReadiness}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response('{invalid-json'));
  const error=await getReadiness().then(()=>null,value=>value as Error);
  if(!error)throw new Error('expected readiness rejection');
  expect(error.message).toBe('依赖状态响应无效');
  expect(error.message).not.toContain('JSON');
  expect(error.message).not.toContain('SyntaxError');
});

test('a structured readiness 503 turns whitelisted dependency states into actionable reasons',async()=>{
  const {getReadiness}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{details:{checks:{postgres:'marker_schema_or_privilege_mismatch',redis:'ready',rabbitmq:'ready',s3:'bucket_missing',keycloak:'ready',worker:'unavailable'}}}}),{status:503}));
  await expect(getReadiness()).rejects.toThrow('本地依赖尚未就绪：数据库环境、结构或读取权限不匹配，请运行隔离校验并检查迁移与授权；对象存储缺少项目专属存储桶，请检查本地存储初始化；后台任务服务无法连接，请检查 Worker 与消息队列连接');
});

test.each([
  ['unavailable','身份服务无法连接，请检查 Keycloak 服务与连接配置'],
  ['timeout','身份服务检查超时，请检查 Keycloak 服务是否阻塞'],
  ['audience_mismatch','身份服务 audience 配置不匹配，请检查本地 OIDC 配置'],
  ['jwks_url_mismatch','身份服务 JWKS 地址不匹配，请检查本地 OIDC 配置'],
  ['malformed_discovery','身份服务发现文档无效，请检查 Keycloak realm 配置'],
  ['issuer_mismatch','身份服务 issuer 不匹配，请检查公开访问地址与 realm 配置'],
  ['jwks_uri_mismatch','身份服务发现的 JWKS 地址不匹配，请检查 Keycloak realm 配置'],
  ['malformed_jwks','身份服务签名密钥响应无效，请检查 Keycloak realm 密钥'],
  ['keys_missing','身份服务缺少签名密钥，请检查 Keycloak realm 密钥'],
  ['usable_signing_key_missing','身份服务缺少可用的 RS256 验签密钥，请检查 Keycloak realm 密钥'],
  ['admin_url_mismatch','身份服务管理地址不匹配，请检查 Keycloak 管理端点配置'],
  ['monitor_client_mismatch','身份服务就绪监控客户端不匹配，请检查 Keycloak 监控客户端配置'],
  ['monitor_token_unavailable','身份服务监控令牌无法获取，请检查 Keycloak 监控客户端凭据'],
  ['monitor_role_mismatch','身份服务监控客户端角色不匹配，请检查 Keycloak realm-management 角色配置'],
  ['monitor_permission_denied','身份服务监控客户端权限不足，请检查 Keycloak 管理读取权限'],
  ['realm_configuration_mismatch','身份服务 realm 配置不匹配，请检查 Keycloak realm 配置'],
  ['client_configuration_mismatch','身份服务 Web 客户端配置不匹配，请检查 Keycloak 客户端配置'],
  ['audience_mapper_mismatch','身份服务 audience 映射配置不匹配，请检查 Keycloak 协议映射器配置'],
])('a complete readiness 503 explains Keycloak %s without reflecting server content',async(status,reason)=>{
  const {getReadiness}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:'server-secret-content',details:{checks:{postgres:'ready',redis:'ready',rabbitmq:'ready',s3:'ready',keycloak:status,worker:'ready'}}}}),{status:503}));
  const error=await getReadiness().then(()=>null,value=>value as Error);
  expect(error?.message).toBe(`本地依赖尚未就绪：${reason}`);
  expect(error?.message).not.toContain('server-secret-content');
});

test('a complete readiness 503 with an unknown Keycloak state stays generic and safe',async()=>{
  const {getReadiness}=await import('./api');
  const secret='unknown-keycloak-secret';
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:'server-secret-content',details:{checks:{postgres:'ready',redis:'ready',rabbitmq:'ready',s3:'ready',keycloak:secret,worker:'ready'}}}}),{status:503}));
  const error=await getReadiness().then(()=>null,value=>value as Error);
  expect(error?.message).toBe('本地依赖尚未就绪：依赖检查返回未知状态，请查看 API 服务日志');
  expect(error?.message).not.toContain(secret);
  expect(error?.message).not.toContain('server-secret-content');
});

test('a readiness 503 never reflects unknown dependency names, states, or server messages',async()=>{
  const {getReadiness}=await import('./api');
  const secret='server-secret-content';
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:secret,details:{checks:{postgres:'ready',redis:'ready',rabbitmq:'ready',s3:'ready',keycloak:'ready',worker:secret,unexpected:secret}}}}),{status:503}));
  const error=await getReadiness().then(()=>null,value=>value as Error);
  if(!error)throw new Error('expected readiness rejection');
  expect(error.message).toBe('本地依赖尚未就绪');
  expect(error.message).not.toContain(secret);
  expect(error.message).not.toContain('unexpected');
});

test('an oversized readiness response is rejected without parsing or reflecting its content',async()=>{
  const {getReadiness}=await import('./api');
  const secret='oversized-server-secret';
  vi.mocked(fetch).mockResolvedValue(new Response(secret,{headers:{'content-length':'65537'}}));
  const error=await getReadiness().then(()=>null,value=>value as Error);
  if(!error)throw new Error('expected readiness rejection');
  expect(error.message).toBe('依赖状态响应无效');
  expect(error.message).not.toContain(secret);
});

test.each([
  ['incomplete',{"postgres":"ready","redis":"ready","rabbitmq":"ready","s3":"ready","keycloak":"ready"}],
  ['array',["ready","ready","ready","ready","ready","ready"]],
  ['extra',{"postgres":"ready","redis":"ready","rabbitmq":"ready","s3":"ready","keycloak":"ready","worker":"ready","unexpected":"ready"}],
])('readiness rejects %s checks',async(_label,checks)=>{
  const {getReadiness}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({status:'ready',checks})));
  await expect(getReadiness()).rejects.toThrow('依赖状态响应无效');
});

test('account HTTP 401 is typed as a definite authentication rejection',async()=>{
  const {AccountRequestError,getMe,isAuthenticationRejection}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:'login rejected'}}),{status:401}));
  const error=await getMe().then(()=>null,value=>value as unknown);
  expect(error).toBeInstanceOf(AccountRequestError);
  if(!(error instanceof AccountRequestError))throw new Error('expected AccountRequestError');
  expect(error.status).toBe(401);
  expect(error.kind).toBe('authentication');
  expect(isAuthenticationRejection(error)).toBe(true);
});

test('account HTTP 403 is a durable workspace rejection rather than an invalid session',async()=>{
  const {AccountRequestError,getMe,isAuthenticationRejection,isWorkspaceForbidden}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:'workspace rejected'}}),{status:403}));
  const error=await getMe().then(()=>null,value=>value as unknown);
  expect(error).toBeInstanceOf(AccountRequestError);
  if(!(error instanceof AccountRequestError))throw new Error('expected AccountRequestError');
  expect(error.status).toBe(403);
  expect(error.kind).toBe('forbidden');
  expect(error.message).toBe('当前账户没有工作区访问权限');
  expect(isAuthenticationRejection(error)).toBe(false);
  expect(isWorkspaceForbidden(error)).toBe(true);
});

test('account 503 is typed as transient and preserves the distinction from authentication rejection',async()=>{
  const {AccountRequestError,getMe,isAuthenticationRejection}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({error:{message:'account service unavailable'}}),{status:503}));
  const error=await getMe().then(()=>null,value=>value as unknown);
  expect(error).toBeInstanceOf(AccountRequestError);
  if(!(error instanceof AccountRequestError))throw new Error('expected AccountRequestError');
  expect(error.status).toBe(503);
  expect(error.kind).toBe('transient');
  expect(isAuthenticationRejection(error)).toBe(false);
});

test.each([
  ['success',200,'invalid-response',undefined],
  ['server error',503,'transient',503],
])('account %s with a declared oversized body is cancelled and typed safely',async(_label,status,kind,expectedStatus)=>{
  const {AccountRequestError,getMe}=await import('./api');
  const cancelled=vi.fn();
  const stream=new ReadableStream({cancel:cancelled});
  vi.mocked(fetch).mockResolvedValue(new Response(stream,{status,headers:{'content-length':'65537'}}));

  const error=await getMe().then(()=>null,value=>value as unknown);
  expect(error).toBeInstanceOf(AccountRequestError);
  if(!(error instanceof AccountRequestError))throw new Error('expected AccountRequestError');
  expect(error.kind).toBe(kind);
  expect(error.status).toBe(expectedStatus);
  expect(error.message).not.toContain('server-secret');
  expect(cancelled).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledOnce();
});

test.each([
  ['success',200,'invalid-response',undefined],
  ['server error',503,'transient',503],
])('account %s with a chunked oversized body is cancelled and typed safely',async(_label,status,kind,expectedStatus)=>{
  const {AccountRequestError,getMe}=await import('./api');
  const cancelled=vi.fn();
  const stream=new ReadableStream({
    start(controller){controller.enqueue(new Uint8Array(64*1024));controller.enqueue(new TextEncoder().encode('server-secret'));},
    cancel:cancelled,
  });
  vi.mocked(fetch).mockResolvedValue(new Response(stream,{status}));

  const error=await getMe().then(()=>null,value=>value as unknown);
  expect(error).toBeInstanceOf(AccountRequestError);
  if(!(error instanceof AccountRequestError))throw new Error('expected AccountRequestError');
  expect(error.kind).toBe(kind);
  expect(error.status).toBe(expectedStatus);
  expect(error.message).not.toContain('server-secret');
  expect(cancelled).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledOnce();
});

test('a malformed successful account response is typed as retryable invalid data',async()=>{
  const {AccountRequestError,getMe,isAuthenticationRejection}=await import('./api');
  vi.mocked(fetch).mockResolvedValue(new Response('{"data":{"display_name":"incomplete"}}'));
  const error=await getMe().then(()=>null,value=>value as unknown);
  expect(error).toBeInstanceOf(AccountRequestError);
  if(!(error instanceof AccountRequestError))throw new Error('expected AccountRequestError');
  expect(error.kind).toBe('invalid-response');
  expect(error.status).toBeUndefined();
  expect(isAuthenticationRejection(error)).toBe(false);
});
