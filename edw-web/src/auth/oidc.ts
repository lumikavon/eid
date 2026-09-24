import { boundedJson } from '../http/bounded-json';

const issuer = `${window.location.origin}/realms/eid-local`;
const clientId = 'eid-web';
const redirectUri = `${window.location.origin}/auth/callback`;
const postLogoutRedirectUri = 'http://localhost:18080/';
export const TOKEN_EXCHANGE_TIMEOUT_MS = 8000;
const MAX_TOKEN_RESPONSE_BYTES = 64*1024;
let accessToken: string | null = null;
let idToken: string | null = null;
let callback: Promise<string> | null = null;

type OidcTransaction={state:string;verifier:string;returnTo:string};
const uuidPath='[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const workspaceReturnPath=new RegExp(`^/workspaces/${uuidPath}/(?:home|documents|favorites|references|recycle|search|project|projects|account|tasks|notifications|(?:tasks|resources|records)/${uuidPath})$`);
// Comparing the full match also rejects a final line break accepted by the $ anchor.
const safeReturnPath=(path:unknown):path is string=>typeof path==='string'&&(path==='/'||path==='/admin/members'||workspaceReturnPath.exec(path)?.[0]===path);

function parseTransaction(raw:string):OidcTransaction{
  let value:unknown;
  try{value=JSON.parse(raw)}catch{throw new Error('登录事务无效')}
  if(value===null||typeof value!=='object'||Array.isArray(value))throw new Error('登录事务无效');
  const transaction=value as Record<string,unknown>;
  if(typeof transaction.state!=='string'||transaction.state.length===0||typeof transaction.verifier!=='string'||transaction.verifier.length===0)throw new Error('登录事务无效');
  if(transaction.returnTo!==undefined&&!safeReturnPath(transaction.returnTo))throw new Error('登录返回路径无效');
  return {state:transaction.state,verifier:transaction.verifier,returnTo:transaction.returnTo as string??'/'};
}

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
}

export async function beginLogin(): Promise<void> {
  callback=null;
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = base64url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  const state = base64url(crypto.getRandomValues(new Uint8Array(24)));
  const returnTo=safeReturnPath(window.location.pathname)?window.location.pathname:'/';
  sessionStorage.setItem('oidc.tx', JSON.stringify({state, verifier, returnTo}));
  const url = new URL(`${issuer}/protocol/openid-connect/auth`);
  url.searchParams.set('client_id',clientId); url.searchParams.set('redirect_uri',redirectUri);
  url.searchParams.set('response_type','code'); url.searchParams.set('scope','openid profile');
  url.searchParams.set('state',state); url.searchParams.set('code_challenge',challenge); url.searchParams.set('code_challenge_method','S256');
  window.location.assign(url);
}

export function finishLogin(): Promise<string> {
  // exchangeCode synchronously removes the callback URL; StrictMode's second call shares it.
  // A later navigation to a callback URL starts a new validation, never reuses old success.
  if(window.location.pathname==='/auth/callback')callback=null;
  callback ??= exchangeCode().catch(error=>{clearSession();throw error});
  return callback;
}

async function exchangeCode(): Promise<string> {
  const params = new URLSearchParams(window.location.search);
  const code=params.get('code'), state=params.get('state');
  const raw=sessionStorage.getItem('oidc.tx'); sessionStorage.removeItem('oidc.tx');
  history.replaceState({},'', '/');
  if(!code || !state) throw new Error('登录回调缺少授权事务');
  if(!raw)throw new Error('登录事务无效');
  const tx=parseTransaction(raw);
  if(tx.state!==state) throw new Error('登录 state 校验失败');
  const body=new URLSearchParams({grant_type:'authorization_code',client_id:clientId,redirect_uri:redirectUri,code,code_verifier:tx.verifier});
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),TOKEN_EXCHANGE_TIMEOUT_MS);
  try {
    const response=await fetch(`${issuer}/protocol/openid-connect/token`,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body,signal:controller.signal});
    if(!response.ok) throw new Error('授权码交换失败');
    const payload=await boundedJson(response,MAX_TOKEN_RESPONSE_BYTES,'令牌响应无效') as {access_token?:unknown;id_token?:unknown};
    if(typeof payload?.access_token!=='string'||payload.access_token.trim().length===0)throw new Error('令牌响应无有效 access_token');
    accessToken=payload.access_token;
    idToken=typeof payload.id_token==='string'&&payload.id_token.trim().length>0?payload.id_token:null;
    return tx.returnTo;
  } catch(error) {
    if(controller.signal.aborted)throw new Error('授权码交换超时，请稍后重试');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export function token(): string | null { return accessToken; }
export function clearSession(): void { accessToken=null;idToken=null; }
export function logout(): void {
  const logoutHint=idToken;
  clearSession();
  const form=document.createElement('form');
  form.method='POST';form.action=`${issuer}/protocol/openid-connect/logout`;form.hidden=true;
  const fields:Record<string,string>={client_id:clientId,post_logout_redirect_uri:postLogoutRedirectUri};
  if(logoutHint)fields.id_token_hint=logoutHint;
  for(const [name,value] of Object.entries(fields)){
    const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;form.appendChild(input);
  }
  document.body.appendChild(form);
  try{form.submit()}finally{form.remove()}
}
