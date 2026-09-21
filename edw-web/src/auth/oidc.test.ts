import {afterEach,beforeEach,expect,test,vi} from 'vitest';

const values = new Map<string,string>();
const assign = vi.fn();
const workspacePath='/workspaces/22222222-2222-4222-8222-222222222222';
const recordId='11111111-1111-4111-8111-111111111111';
const unsafeReturnPaths=[
  'https://evil.invalid','//evil.invalid','javascript:alert(1)',
  '/admin/members?access_token=secret','/admin/members#fragment','/workspaces/../admin',
  '/auth/callback',`${workspacePath}/unknown`,`${workspacePath}/home/`,
  '/workspaces/not-a-uuid/documents',`${workspacePath}/records/not-a-uuid`,
  `${workspacePath}/resources/not-a-uuid`,`${workspacePath}/records/${recordId}/extra`,
  `${workspacePath}/search?q=private-search-term`,`${workspacePath}/records/${recordId}#fragment`,
  `${workspacePath}/records/%31${recordId.slice(1)}`,`${workspacePath}/records/../home`,
  `${workspacePath}/home\n`,`${workspacePath}/home\r`,`${workspacePath}/home\u2028`,`${workspacePath}/home\u2029`,
];
beforeEach(()=>{
  vi.resetModules(); vi.clearAllMocks(); values.clear();
  vi.stubGlobal('window',{location:{origin:'http://localhost:18080',search:'',assign}});
  vi.stubGlobal('sessionStorage',{setItem:(k:string,v:string)=>values.set(k,v),getItem:(k:string)=>values.get(k)??null,removeItem:(k:string)=>values.delete(k)});
  vi.stubGlobal('history',{replaceState:vi.fn()});
  vi.stubGlobal('fetch',vi.fn());
});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()});

async function callbackTransaction(){
  const auth=await import('./oidc'); await auth.beginLogin();
  const tx=JSON.parse(values.get('oidc.tx')!);
  window.location.search=`?code=example&state=${tx.state}`;
  return auth;
}

function logoutFields(auth:{logout:()=>void}):Record<string,string>{
  const fields:Array<{name:string;value:string}>=[];
  const form={method:'',action:'',hidden:false,appendChild:(input:{name:string;value:string})=>fields.push(input),submit:vi.fn(),remove:vi.fn()};
  vi.stubGlobal('document',{createElement:(tag:string)=>tag==='form'?form:{type:'',name:'',value:''},body:{appendChild:vi.fn()}});
  auth.logout();
  return Object.fromEntries(fields.map(input=>[input.name,input.value]));
}

test('authorization uses S256 and never puts an access token in URL',async()=>{
  const auth = await import('./oidc'); await auth.beginLogin();
  const url = new URL(assign.mock.calls[0][0]);
  expect(url.searchParams.get('code_challenge_method')).toBe('S256');
  expect(url.searchParams.get('response_type')).toBe('code');
  const tx = JSON.parse(values.get('oidc.tx')!);
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(tx.verifier)));
  const challenge=btoa(String.fromCharCode(...digest)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
  expect(url.searchParams.get('code_challenge')).toBe(challenge);
  expect(url.searchParams.has('access_token')).toBe(false);
});

test('wrong state clears transaction and never exchanges a code',async()=>{
  const auth=await import('./oidc'); await auth.beginLogin();
  window.location.search='?code=example&state=invalid';
  await expect(auth.finishLogin()).rejects.toThrow('state');
  expect(fetch).not.toHaveBeenCalled(); expect(values.size).toBe(0);
});

test.each([
  '/','/admin/members',
  ...['home','documents','favorites','references','recycle','search','project','projects','account'].map(page=>`${workspacePath}/${page}`),
  `${workspacePath}/resources/${recordId}`,`${workspacePath}/records/${recordId}`,
  '/workspaces/AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA/records/BBBBBBBB-BBBB-4BBB-8BBB-BBBBBBBBBBBB',
])('validated return path %s survives the one-shot login transaction',async destination=>{
  window.location.pathname=destination;
  const auth=await callbackTransaction();
  expect(JSON.parse(values.get('oidc.tx')!).returnTo).toBe(destination);
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'memory-token'})));
  await expect(auth.finishLogin()).resolves.toBe(destination);
  expect(values.size).toBe(0);
  expect(history.replaceState).toHaveBeenCalledWith({},'', '/');
});

test.each(unsafeReturnPaths)('unsafe return path %s rejects before exchange',async returnTo=>{
  const auth=await import('./oidc');
  values.set('oidc.tx',JSON.stringify({state:'expected',verifier:'verifier',returnTo}));
  window.location.search='?code=example&state=expected';
  await expect(auth.finishLogin()).rejects.toThrow('登录返回路径无效');
  expect(fetch).not.toHaveBeenCalled();expect(values.size).toBe(0);
});

test.each(unsafeReturnPaths)('login from unsafe pathname %s stores only the root fallback',async pathname=>{
  window.location.pathname=pathname;
  const auth=await import('./oidc');
  await auth.beginLogin();
  expect(JSON.parse(values.get('oidc.tx')!).returnTo).toBe('/');
});

test('login preserves the search page without storing query text or URL fragments',async()=>{
  const destination=`${workspacePath}/search`;
  window.location.pathname=destination;
  window.location.search='?q=private-search-term';
  window.location.hash='#private-fragment';
  const auth=await import('./oidc');
  await auth.beginLogin();

  const stored=values.get('oidc.tx')!;
  expect(JSON.parse(stored)).toEqual({state:expect.any(String),verifier:expect.any(String),returnTo:destination});
  expect(stored).not.toContain('private-search-term');
  expect(stored).not.toContain('private-fragment');
  expect(String(assign.mock.calls[0][0])).not.toContain('private-search-term');
  expect(String(assign.mock.calls[0][0])).not.toContain('private-fragment');
});

test.each([
  ['malformed JSON','{broken'],
  ['null JSON','null'],
  ['missing verifier',JSON.stringify({state:'expected'})],
  ['wrong verifier type',JSON.stringify({state:'expected',verifier:42})],
])('invalid stored transaction (%s) is cleared and rejected before token exchange',async(_label,stored)=>{
  const auth=await import('./oidc');
  values.set('oidc.tx',stored);
  window.location.search='?code=example&state=expected';

  await expect(auth.finishLogin()).rejects.toThrow('登录事务无效');
  expect(fetch).not.toHaveBeenCalled();
  expect(values.size).toBe(0);
  expect(history.replaceState).toHaveBeenCalledWith({},'', '/');
});

test('a missing stored transaction fails closed and a fresh login creates a new transaction',async()=>{
  const auth=await import('./oidc');
  window.location.search='?code=example&state=expected';
  await expect(auth.finishLogin()).rejects.toThrow('登录事务无效');
  expect(fetch).not.toHaveBeenCalled();
  expect(history.replaceState).toHaveBeenCalledWith({},'', '/');

  await auth.beginLogin();
  expect(JSON.parse(values.get('oidc.tx')!)).toEqual(expect.objectContaining({state:expect.any(String),verifier:expect.any(String)}));
  expect(assign).toHaveBeenCalledOnce();
});

test('callback exchanges once and holds tokens only in memory',async()=>{
  const auth=await callbackTransaction();
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'test-only-token'})));
  await Promise.all([auth.finishLogin(),auth.finishLogin()]);
  expect(fetch).toHaveBeenCalledTimes(1); expect(values.size).toBe(0);
  expect(auth.token()).toBe('test-only-token'); auth.clearSession(); expect(auth.token()).toBeNull();
});

test('a failed new callback clears an existing session and permits fresh authentication',async()=>{
 const auth=await callbackTransaction();
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'old-memory-token'})));
 await auth.finishLogin();
 await auth.beginLogin();
 expect(auth.token()).toBe('old-memory-token');
 window.location.search='?code=next&state=wrong';
 await expect(auth.finishLogin()).rejects.toThrow('state');
 expect(auth.token()).toBeNull();
 await auth.beginLogin();
 const tx=JSON.parse(values.get('oidc.tx')!);
 window.location.search=`?code=fresh&state=${tx.state}`;
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'fresh-memory-token'})));
 await auth.finishLogin();
 expect(auth.token()).toBe('fresh-memory-token');
});

test('a successful pre-deployment transaction without returnTo resumes at root',async()=>{
 const auth=await import('./oidc');
 values.set('oidc.tx',JSON.stringify({state:'old-state',verifier:'old-verifier'}));
 window.location.search='?code=example&state=old-state';
 vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'memory-token'})));
 await expect(auth.finishLogin()).resolves.toBe('/');
 expect(auth.token()).toBe('memory-token');expect(values.size).toBe(0);
 expect(fetch).toHaveBeenCalledOnce();
});

test('user logout clears memory and ends the Keycloak SSO session with the fixed local return URI',async()=>{
  const fields:Array<{name:string;value:string}>=[];
  const form={method:'',action:'',hidden:false,appendChild:(input:{name:string;value:string})=>fields.push(input),submit:vi.fn(),remove:vi.fn()};
  vi.stubGlobal('document',{createElement:(tag:string)=>tag==='form'?form:{type:'',name:'',value:''},body:{appendChild:vi.fn()}});
  const auth=await callbackTransaction();
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'test-only-token',id_token:'test-only-id-token'})));
  await auth.finishLogin();

  assign.mockClear();
  auth.logout();

  expect(auth.token()).toBeNull();
  const url=new URL(form.action);
  expect(url.pathname).toBe('/realms/eid-local/protocol/openid-connect/logout');
  expect(form.method).toBe('POST');
  expect(url.search).toBe('');
  expect(Object.fromEntries(fields.map(input=>[input.name,input.value]))).toEqual({client_id:'eid-web',post_logout_redirect_uri:'http://localhost:18080/',id_token_hint:'test-only-id-token'});
  expect(form.submit).toHaveBeenCalledOnce();expect(form.remove).toHaveBeenCalledOnce();
  expect(assign).not.toHaveBeenCalled();
  expect(values.size).toBe(0);
});

test('invalidating a rejected API session never redirects to Keycloak logout',async()=>{
  const auth=await callbackTransaction();
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:'test-only-token',id_token:'test-only-id-token'})));
  await auth.finishLogin();
  assign.mockClear();

  auth.clearSession();

  expect(auth.token()).toBeNull();
  expect(assign).not.toHaveBeenCalled();
});

test('failed token exchange does not create an authenticated session',async()=>{
  const auth=await callbackTransaction();
  vi.mocked(fetch).mockResolvedValue(new Response('{}',{status:400}));
  await expect(auth.finishLogin()).rejects.toThrow('交换失败');
  expect(auth.token()).toBeNull(); expect(values.size).toBe(0);
});

test.each([undefined,null,{},42,'','   '])('rejects malformed access_token value %#',async accessToken=>{
  const auth=await callbackTransaction();
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({access_token:accessToken})));
  await expect(auth.finishLogin()).rejects.toThrow('令牌响应无有效 access_token');
  expect(auth.token()).toBeNull();
});

test('malformed token JSON does not assign access or ID tokens',async()=>{
  const auth=await callbackTransaction();
  vi.mocked(fetch).mockResolvedValue(new Response('{"access_token":"should-not-be-assigned","id_token":'));

  await expect(auth.finishLogin()).rejects.toThrow('令牌响应无效');
  expect(auth.token()).toBeNull();
  expect(logoutFields(auth)).not.toHaveProperty('id_token_hint');
});

test('a declared oversized token response is cancelled without assigning access or ID tokens',async()=>{
  const auth=await callbackTransaction();
  const cancelled=vi.fn();
  const stream=new ReadableStream({cancel:cancelled});
  vi.mocked(fetch).mockResolvedValue(new Response(stream,{headers:{'content-length':'65537'}}));

  await expect(auth.finishLogin()).rejects.toThrow('令牌响应无效');
  expect(cancelled).toHaveBeenCalledOnce();
  expect(auth.token()).toBeNull();
  expect(logoutFields(auth)).not.toHaveProperty('id_token_hint');
});

test('a chunked oversized token response is cancelled without assigning access or ID tokens',async()=>{
  const auth=await callbackTransaction();
  const cancelled=vi.fn();
  const stream=new ReadableStream({
    start(controller){
      controller.enqueue(new TextEncoder().encode(JSON.stringify({access_token:'should-not-be-assigned',id_token:'should-not-be-assigned'}).padEnd(64*1024,' ')));
      controller.enqueue(new Uint8Array([0]));
    },
    cancel:cancelled,
  });
  vi.mocked(fetch).mockResolvedValue(new Response(stream));

  await expect(auth.finishLogin()).rejects.toThrow('令牌响应无效');
  expect(cancelled).toHaveBeenCalledOnce();
  expect(auth.token()).toBeNull();
  expect(logoutFields(auth)).not.toHaveProperty('id_token_hint');
});

test('token exchange times out while waiting for response headers',async()=>{
  vi.useFakeTimers();
  const auth=await callbackTransaction();
  expect(auth.TOKEN_EXCHANGE_TIMEOUT_MS).toBe(8000);
  let signal:AbortSignal|undefined;
  vi.mocked(fetch).mockImplementation((_input,init)=>new Promise((_resolve,reject)=>{
    signal=init?.signal??undefined;
    signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true});
  }));

  const rejected=expect(auth.finishLogin()).rejects.toThrow('授权码交换超时，请稍后重试');
  await vi.advanceTimersByTimeAsync(auth.TOKEN_EXCHANGE_TIMEOUT_MS);
  await rejected;
  expect(signal?.aborted).toBe(true);
  expect(auth.token()).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
});

test('token exchange deadline covers stalled response JSON consumption',async()=>{
  vi.useFakeTimers();
  const auth=await callbackTransaction();
  let signal:AbortSignal|undefined;
  vi.mocked(fetch).mockImplementation((_input,init)=>{
    signal=init?.signal??undefined;
    const stream=new ReadableStream({start(controller){signal?.addEventListener('abort',()=>controller.error(new DOMException('aborted','AbortError')),{once:true})}});
    return Promise.resolve(new Response(stream));
  });

  const rejected=expect(auth.finishLogin()).rejects.toThrow('授权码交换超时，请稍后重试');
  await vi.advanceTimersByTimeAsync(auth.TOKEN_EXCHANGE_TIMEOUT_MS);
  await rejected;
  expect(signal?.aborted).toBe(true);
  expect(auth.token()).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
});

test('a completed token exchange clears its deadline',async()=>{
  vi.useFakeTimers();
  const auth=await callbackTransaction();
  let signal:AbortSignal|undefined;
  vi.mocked(fetch).mockImplementation((_input,init)=>{
    signal=init?.signal??undefined;
    return Promise.resolve(new Response(JSON.stringify({access_token:'test-only-token'})));
  });

  await expect(auth.finishLogin()).resolves.toBe('/');
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(auth.TOKEN_EXCHANGE_TIMEOUT_MS);
  expect(signal?.aborted).toBe(false);
});
