import {test,expect,BrowserContext,Page} from '@playwright/test';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';

const viewports=[
  {width:1920,height:1080},
  {width:1440,height:900},
  {width:1181,height:800},
  {width:1180,height:800},
  {width:1024,height:768},
  {width:768,height:1024},
];

const styleProperties=[
  'display','position','box-sizing','align-items','align-self','justify-content',
  'flex-direction','flex','gap','padding',
  'border','border-bottom','border-radius','box-shadow','background','background-color','background-image',
  'color','font-family','font-size','font-weight','line-height','white-space','overflow','overflow-x','overflow-y',
  'opacity','transform','transition','visibility','z-index','content','left','right','top','bottom',
];

const layoutProperties=[
  ...styleProperties,'width','height','min-width','min-height','grid-template-rows','grid-template-columns',
  'margin','margin-left','margin-top',
];

const shellSelectors=[
  '.app','.topbar','.brand','.logo','.topnav','.topnav button','.topnav .ico','.top-spacer',
  '#globalSearch','.bell','.avatar','.uinfo','.uinfo b','.uinfo small','.shell','.sidebar',
  '.side-title','.project-card','.project-icon','.status','.side-menu','.side-menu .side-item',
  '.side-bottom','.storage','.page.active','.toast','.mobile-note',
];

const layoutSelectors=new Set([
  '.app','.topbar','.brand','.logo','.topnav','.topnav button','.topnav .ico','.top-spacer',
  '#globalSearch','.bell','.avatar','.uinfo','.uinfo b','.uinfo small','.shell','.sidebar',
  '.side-title','.project-card','.project-icon','.status','.side-menu','.side-menu .side-item',
  '.storage','.page.active','.toast','.mobile-note',
]);

const pseudoSelectors=[
  {selector:'.logo',pseudo:'::before'},
  {selector:'.logo',pseudo:'::after'},
  {selector:'.bell',pseudo:'::after'},
];

const textRangeSelectors=new Set([
  '.brand','.topnav button','.topnav .ico','.uinfo b','.uinfo small','.side-title',
  '.side-menu .side-item','.toast','.mobile-note',
]);

async function shellContract(page:Page){
  return page.evaluate(({selectors,properties,layoutProperties,layoutSelectors,pseudos,textSelectors})=>{
    const round=(value:number)=>Math.round(value*1000)/1000;
    const rect=(element:Element)=>{const value=element.getBoundingClientRect();const parent=element.parentElement?.getBoundingClientRect();return {x:round(value.x-(parent?.x??0)),y:round(value.y-(parent?.y??0)),width:round(value.width),height:round(value.height)}};
    const style=(element:Element,pseudo?:string)=>{const computed=getComputedStyle(element,pseudo);return Object.fromEntries(properties.map(property=>[property,computed.getPropertyValue(property)]))};
    const textRanges=(element:Element)=>Array.from(element.childNodes).filter(node=>node.nodeType===Node.TEXT_NODE&&node.textContent?.trim()).map(node=>{
      const range=document.createRange();range.selectNodeContents(node);const value=range.getBoundingClientRect();
      const parent=element.getBoundingClientRect();
      return {text:node.textContent?.trim(),rect:{x:round(value.x-parent.x),y:round(value.y-parent.y),width:round(value.width),height:round(value.height)}};
    });
    const elements=Object.fromEntries(selectors.map(selector=>[selector,Array.from(document.querySelectorAll(selector)).map(element=>({
      ...(layoutSelectors.includes(selector)?{rect:rect(element),style:Object.fromEntries(layoutProperties.map(property=>[property,getComputedStyle(element).getPropertyValue(property)]))}:{style:style(element)}),
      ...(textSelectors.includes(selector)?{textRanges:textRanges(element)}:{}),
    }))]));
    const pseudo=Object.fromEntries(pseudos.map(({selector,pseudo})=>[`${selector}${pseudo}`,Array.from(document.querySelectorAll(selector)).map(element=>Object.fromEntries(layoutProperties.map(property=>[property,getComputedStyle(element,pseudo).getPropertyValue(property)])))]));
    return {elements,pseudo,resolvedBodyFont:getComputedStyle(document.body).fontFamily,devicePixelRatio};
  },{selectors:shellSelectors,properties:styleProperties,layoutProperties,layoutSelectors:[...layoutSelectors],pseudos:pseudoSelectors,textSelectors:[...textRangeSelectors]});
}

async function sidebarGeometry(page:Page){
  return page.evaluate(()=>{
    const sidebar=document.querySelector('.sidebar')!.getBoundingClientRect();
    const projectCard=document.querySelector('.project-card')!.getBoundingClientRect();
    const sideMenu=document.querySelector('.side-menu')!.getBoundingClientRect();
    const rect=(value:DOMRect)=>({
      x:Math.round((value.x-sidebar.x)*1000)/1000,
      y:Math.round((value.y-sidebar.y)*1000)/1000,
      width:Math.round(value.width*1000)/1000,
      height:Math.round(value.height*1000)/1000,
    });
    return {
      projectCard:rect(projectCard),
      sideMenu:rect(sideMenu),
      menuOffset:Math.round((sideMenu.top-projectCard.bottom)*1000)/1000,
    };
  });
}

async function projectCardFlexGeometry(page:Page){
  return page.evaluate(()=>{
    const projectIcon=document.querySelector('.project-icon')!;
    const projectCopy=document.querySelector('.project-card > div:nth-child(2)')!;
    const status=document.querySelector('.status')!;
    const iconRect=projectIcon.getBoundingClientRect();
    const copyRect=projectCopy.getBoundingClientRect();
    const iconStyle=getComputedStyle(projectIcon);
    return {
      projectIcon:{
        rectWidth:Math.round(iconRect.width*1000)/1000,
        styleWidth:iconStyle.width,
        gridTemplateColumns:iconStyle.gridTemplateColumns,
      },
      projectCopyRectWidth:Math.round(copyRect.width*1000)/1000,
      statusMarginLeft:getComputedStyle(status).marginLeft,
    };
  });
}

async function openReference(context:BrowserContext,width:number,height:number){
  const original=readFileSync('docs/prototype/index.html','utf8').replace(/<script>[\s\S]*?<\/script>/g,'');
  const reference=await context.newPage();
  await reference.setViewportSize({width,height});
  await reference.route('**/__prototype_baseline',route=>route.fulfill({contentType:'text/html',body:original}));
  await reference.goto('/__prototype_baseline');
  return reference;
}

const screenshotHash=(image:Buffer)=>createHash('sha256').update(image).digest('hex');
const toastIsRendered=(page:Page)=>page.locator('.toast').evaluate(element=>{
  const style=getComputedStyle(element);const rect=element.getBoundingClientRect();
  return style.display!=='none'&&style.visibility!=='hidden'&&style.opacity==='1'&&rect.width>0&&rect.height>0;
});

test('shell preserves prototype dimensions and persistent states',async({page})=>{
  const readiness=page.waitForResponse(response=>response.url().endsWith('/health/ready'));
  await page.goto('/');
  const readinessResponse=await readiness;
  expect(readinessResponse.status()).toBe(200);
  expect(readinessResponse.headers()['cache-control']).toBe('no-store');
  await expect(page.locator('.topbar')).toHaveCSS('height','64px');
  expect(await page.locator('.shell').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ')[0])).toBe('266px');
  await expect(page.getByTestId('auth-status')).toBeVisible();
  await expect(page.getByTestId('ready-status')).toHaveText('依赖已就绪');
  expect(await page.evaluate(()=>Object.keys(localStorage))).toEqual([]);
});

test('real Keycloak PKCE login returns mapped account without persistent tokens',async({page})=>{
  let releaseMe=()=>{};
  let observeMe=()=>{};
  const meRequested=new Promise<void>(resolve=>{observeMe=resolve});
  const holdMe=new Promise<void>(resolve=>{releaseMe=resolve});
  const unauthorized=await page.request.get('/api/v1/me');
  expect(unauthorized.status()).toBe(401);
  expect(unauthorized.headers()['cache-control']).toBe('no-store');
  await page.route('**/api/v1/me',async route=>{observeMe();await holdMe;await route.continue()});
  await page.goto('/');
  const signedOutSidebar=await sidebarGeometry(page);
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await page.locator('#username').fill('local-member');
  await page.locator('#password').fill('eid-local-member');
  const exchanged=page.waitForResponse(r=>r.url().endsWith('/protocol/openid-connect/token'));
  await page.locator('#kc-login').click();
  const exchange=await exchanged;
  expect(exchange.status()).toBe(200);
  await meRequested;
  await expect(page.getByTestId('auth-status')).toHaveText('正在载入当前账户');
  expect(await sidebarGeometry(page)).toEqual(signedOutSidebar);
  await page.screenshot({path:'test-results/workspace-account-loading.png'});
  const mappedAccount=page.waitForResponse(response=>response.url().endsWith('/api/v1/me'));
  releaseMe();
  const mappedAccountResponse=await mappedAccount;
  expect(mappedAccountResponse.status()).toBe(200);
  expect(mappedAccountResponse.headers()['cache-control']).toBe('no-store');
  await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
  await expect(page.locator('.uinfo b')).toHaveText('本地项目成员');
  expect(await sidebarGeometry(page)).toEqual(signedOutSidebar);
  expect(page.url()).toBe('http://localhost:18080/');
  expect(await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}))).toEqual({local:[],session:[]});
  await page.screenshot({path:'test-results/workspace-authenticated.png'});
  await page.getByRole('button',{name:'安全退出',exact:true}).click();
  await page.waitForURL('http://localhost:18080/');
  await expect(page.locator('.uinfo b')).toHaveText('未登录');
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await expect(page.locator('#username')).toBeVisible();
  await expect(page.locator('#password')).toBeVisible();
});

test('an intermittent account 503 keeps the in-memory session and recovers on the scheduled 15 second retry',async({page})=>{
  await page.addInitScript(()=>{
    const nativeSetInterval=window.setInterval;
    const scheduled:number[]=[];
    Object.defineProperty(window,'__scheduledIntervals',{value:scheduled});
    window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>{
      scheduled.push(timeout??0);
      return nativeSetInterval(handler,timeout,...args);
    };
  });
  let requestCount=0;
  const authorizationHeaders:string[]=[];
  let releaseRetry=()=>{};
  let observeRetry=()=>{};
  const retryRequested=new Promise<void>(resolve=>{observeRetry=resolve});
  const holdRetry=new Promise<void>(resolve=>{releaseRetry=resolve});
  await page.route('**/api/v1/me',async route=>{
    requestCount+=1;
    authorizationHeaders.push(route.request().headers().authorization??'');
    if(requestCount===1){
      await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'account service unavailable'}})});
      return;
    }
    observeRetry();
    await holdRetry;
    await route.continue();
  });
  await page.goto('/');
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await page.locator('#username').fill('local-member');
  await page.locator('#password').fill('eid-local-member');
  await page.locator('#kc-login').click();
  await expect(page.getByTestId('auth-status')).toHaveText('账户服务暂时不可用');
  await expect(page.getByRole('alert')).toContainText('将自动重试，也可手动重试');
  expect(await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}))).toEqual({local:[],session:[]});

  await retryRequested;
  expect(await page.evaluate(()=>(window as typeof window&{__scheduledIntervals:number[]}).__scheduledIntervals)).toContain(15000);
  await expect(page.getByTestId('auth-status')).toHaveText('正在载入当前账户');
  releaseRetry();
  await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
  await expect(page.locator('.uinfo b')).toHaveText('本地项目成员');
  expect(authorizationHeaders).toHaveLength(2);
  expect(authorizationHeaders[0]).toMatch(/^Bearer /);
  expect(authorizationHeaders[1]).toBe(authorizationHeaders[0]);
  expect(await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}))).toEqual({local:[],session:[]});
});

test('an explicit account 401 clears the in-memory session',async({page})=>{
  await page.route('**/api/v1/me',route=>route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({error:{message:'login expired'}})}));
  await page.goto('/');
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await page.locator('#username').fill('local-member');
  await page.locator('#password').fill('eid-local-member');
  await page.locator('#kc-login').click();
  await expect(page.getByTestId('auth-status')).toHaveText('认证失败');
  await expect(page.getByRole('alert')).toHaveText('登录已失效，请重新登录');
  await expect(page.getByRole('button',{name:'登录工作区',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'重试账户加载',exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}))).toEqual({local:[],session:[]});
});

test('an account 403 preserves the valid session and shows a durable workspace denial without retrying',async({page})=>{
  await page.addInitScript(()=>{
    const nativeSetInterval=window.setInterval;
    window.setInterval=(handler:TimerHandler,timeout?:number,...args:unknown[])=>nativeSetInterval(handler,timeout===15000?100:timeout,...args);
  });
  let requestCount=0;
  await page.route('**/api/v1/me',async route=>{
    requestCount+=1;
    await new Promise(resolve=>setTimeout(resolve,250));
    return route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({error:{message:'workspace rejected'}})});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await page.locator('#username').fill('local-member');
  await page.locator('#password').fill('eid-local-member');
  await page.locator('#kc-login').click();
  await expect(page.getByTestId('auth-status')).toHaveText('工作区访问被拒绝');
  await expect(page.getByRole('alert')).toHaveText('当前账户没有工作区访问权限');
  await expect(page.getByRole('button',{name:'安全退出',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'登录工作区',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'重试账户加载',exact:true})).toHaveCount(0);
  await page.waitForTimeout(350);
  expect(requestCount).toBe(1);
});

test('an invalid callback state is readable and offers a fresh login',async({page})=>{
  await page.goto('/');
  await page.evaluate(()=>sessionStorage.setItem('oidc.tx',JSON.stringify({state:'expected-state',verifier:'test-verifier'})));
  await page.goto('/auth/callback?code=example&state=invalid');
  await expect(page.getByTestId('auth-status')).toHaveText('认证失败');
  await expect(page.getByRole('alert')).toContainText('登录 state 校验失败');
  await expect(page.getByRole('button',{name:'登录工作区',exact:true})).toBeVisible();
  expect(page.url()).toBe('http://localhost:18080/');
});

test('logout fences a delayed periodic account refresh',async({page})=>{
  let logoutMethod='';let logoutUrl='';
  page.on('request',request=>{if(new URL(request.url()).pathname.endsWith('/protocol/openid-connect/logout')){logoutMethod=request.method();logoutUrl=request.url()}});
  let requestCount=0;
  let releasePeriodic=()=>{};
  let observePeriodic=()=>{};
  const periodicRequested=new Promise<void>(resolve=>{observePeriodic=resolve});
  const holdPeriodic=new Promise<void>(resolve=>{releasePeriodic=resolve});
  await page.route('**/api/v1/me',async route=>{
    requestCount+=1;
    if(requestCount===2){observePeriodic();await holdPeriodic}
    await route.continue().catch(()=>{});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await page.locator('#username').fill('local-member');
  await page.locator('#password').fill('eid-local-member');
  await page.locator('#kc-login').click();
  await expect(page.getByTestId('auth-status')).toHaveText('已安全登录');
  await periodicRequested;
  await page.getByRole('button',{name:'安全退出',exact:true}).click();
  await page.waitForURL('http://localhost:18080/');
  expect(logoutMethod).toBe('POST');
  expect(new URL(logoutUrl).search).toBe('');
  await expect(page.getByTestId('auth-status')).toHaveText('需要登录');
  await expect(page.locator('.uinfo b')).toHaveText('未登录');
  releasePeriodic();
  await page.waitForTimeout(300);
  await expect(page.getByTestId('auth-status')).toHaveText('需要登录');
  await expect(page.locator('.uinfo b')).toHaveText('未登录');
  await expect(page.getByRole('button',{name:'安全退出',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'登录工作区',exact:true}).click();
  await expect(page.locator('#username')).toBeVisible();
});

test('dependency failure remains visibly distinguishable from readiness',async({page})=>{
  await page.route('**/health/ready',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'must not be rendered',details:{checks:{postgres:'unavailable',redis:'ready',rabbitmq:'ready',s3:'ready',keycloak:'ready',worker:'ready'}}}})}));
  await page.goto('/');
  await expect(page.getByTestId('ready-status')).toHaveText('本地依赖尚未就绪：数据库无法连接，请检查 PostgreSQL 服务与连接配置');
  await expect(page.getByTestId('ready-status')).not.toContainText('must not be rendered');
  await expect(page.getByTestId('ready-status')).toBeVisible();
  await page.screenshot({path:'test-results/workspace-readiness-error.png'});
});

test('a stalled readiness request becomes a readable timeout before the next poll',async({page})=>{
  await page.clock.install({time:new Date('2026-09-10T12:00:00Z')});
  await page.clock.pauseAt(new Date('2026-09-10T12:00:01Z'));
  let observeRequest=()=>{};
  let releaseRequest=()=>{};
  const requested=new Promise<void>(resolve=>{observeRequest=resolve});
  const held=new Promise<void>(resolve=>{releaseRequest=resolve});
  await page.route('**/health/ready',async route=>{
    observeRequest();
    await held;
    await route.fulfill({status:200,contentType:'application/json',body:'{}'}).catch(()=>{});
  });
  try{
    await page.goto('/');
    await requested;
    await page.clock.fastForward(7999);
    await expect(page.getByTestId('ready-status')).toHaveText('正在检查依赖');
    await page.clock.fastForward(1);
    await expect(page.getByTestId('ready-status')).toHaveText('依赖状态检查超时，请稍后重试');
    await expect(page.getByTestId('ready-status')).toBeVisible();
  }finally{releaseRequest()}
});

test('unavailable actions use the exact source toast and remain transient',async({page,context})=>{
  await page.goto('/');
  await expect(page.getByTestId('auth-status')).toHaveText('需要登录');
  const reference=await openReference(context,1920,1080);
  await reference.locator('.avatar').evaluate(el=>el.textContent='访');
  await reference.locator('.uinfo b').evaluate(el=>el.textContent='未登录');
  await reference.locator('.uinfo small').evaluate(el=>el.textContent='需要登录');
  const toast=page.locator('.toast');
  const referenceToast=reference.locator('.toast');
  await expect(toast).toHaveClass('toast');
  expect(await shellContract(page)).toEqual(await shellContract(reference));
  await page.bringToFront();
  const hiddenImage=await page.screenshot({path:'test-results/workspace-toast-hidden.png',timeout:5000});

  await page.clock.install({time:new Date('2026-09-10T12:00:00Z')});
  await page.clock.pauseAt(new Date('2026-09-10T12:00:01Z'));
  await page.locator('#globalSearch').click();
  await referenceToast.evaluate(el=>{el.textContent='搜索功能尚未开放';el.classList.add('show')});
  await expect(toast).toHaveClass(/\bshow\b/);
  await expect(toast).toHaveText('搜索功能尚未开放');
  await expect(toast).toHaveCSS('opacity','1');
  await expect(referenceToast).toHaveCSS('opacity','1');
  expect(await toastIsRendered(page)).toBe(true);
  expect(await toastIsRendered(reference)).toBe(true);
  expect(await shellContract(page)).toEqual(await shellContract(reference));
  await expect(page.locator('.notice .error')).toHaveCount(0);
  await expect(page.getByTestId('ready-status')).toBeVisible();
  await page.bringToFront();
  const shownImage=await page.screenshot({path:'test-results/workspace-toast-shown.png',timeout:5000,animations:'disabled'});
  expect(await toastIsRendered(page)).toBe(true);
  expect(screenshotHash(shownImage)).not.toBe(screenshotHash(hiddenImage));
  await reference.bringToFront();
  await reference.screenshot({path:'test-results/reference-toast-shown.png',timeout:5000,animations:'disabled'});
  expect(await toastIsRendered(reference)).toBe(true);

  await page.clock.fastForward(1799);
  await expect(toast).toHaveClass(/\bshow\b/);
  expect(await toastIsRendered(page)).toBe(true);
  await page.clock.fastForward(1);
  await expect(toast).toHaveClass('toast');
  await referenceToast.evaluate(el=>el.classList.remove('show'));
  await expect(toast).toHaveCSS('opacity','0');
  await expect(referenceToast).toHaveCSS('opacity','0');
  expect(await shellContract(page)).toEqual(await shellContract(reference));
  await reference.close();
});

test('notification button activates with Space and prevents its default keyboard action',async({page})=>{
  await page.goto('/');
  const result=await page.getByRole('button',{name:'通知'}).evaluate(element=>{
    const event=new KeyboardEvent('keydown',{key:' ',bubbles:true,cancelable:true});
    return {dispatched:element.dispatchEvent(event),defaultPrevented:event.defaultPrevented};
  });
  expect(result).toEqual({dispatched:false,defaultPrevented:true});
  await expect(page.locator('.toast')).toHaveClass(/\bshow\b/);
  await expect(page.locator('.toast')).toHaveText('通知功能尚未开放');
});

test('Keycloak rejects an authorization request without PKCE',async({request})=>{
  const result=await request.get('/realms/eid-local/protocol/openid-connect/auth',{
    params:{client_id:'eid-web',redirect_uri:'http://localhost:18080/auth/callback',response_type:'code',scope:'openid',state:'negative-test'},maxRedirects:0});
  expect([302,400]).toContain(result.status());
  const evidence=(result.headers().location??'')+await result.text();
  expect(evidence).toMatch(/invalid_request|code_challenge|PKCE/i);
});

for(const {width,height} of viewports){
  test(`shell contract and review artifacts ${width}x${height}`,async({page,context})=>{
    await page.setViewportSize({width,height}); await page.goto('/');
    await expect(page.getByTestId('auth-status')).toHaveText('需要登录');
    const reference=await openReference(context,width,height);
    // Account copy is an authorized real-data replacement. Normalize only these
    // strings so their glyph geometry can still be checked against the source shell.
    await reference.locator('.avatar').evaluate(el=>el.textContent='访');
    await reference.locator('.uinfo b').evaluate(el=>el.textContent='未登录');
    await reference.locator('.uinfo small').evaluate(el=>el.textContent='需要登录');
    expect(await page.locator('.topnav button').allTextContents()).toEqual(await reference.locator('.topnav button').allTextContents());
    expect(await page.locator('.side-menu .side-item').allTextContents()).toEqual(await reference.locator('.side-menu .side-item').allTextContents());
    const referenceProjectFlex=await projectCardFlexGeometry(reference);
    expect(referenceProjectFlex).toEqual({
      projectIcon:{rectWidth:34.531,styleWidth:'34.5312px',gridTemplateColumns:'34.5312px'},
      projectCopyRectWidth:114.469,
      statusMarginLeft:'0px',
    });
    expect(await projectCardFlexGeometry(page)).toEqual(referenceProjectFlex);
    await expect(page.locator('.project-icon')).toHaveCSS('height','38px');
    const bottomOffset=async(target:Page)=>target.evaluate(()=>{
      const sidebar=document.querySelector('.sidebar')!.getBoundingClientRect();
      const bottom=document.querySelector('.side-bottom')!.getBoundingClientRect();
      return Math.round((sidebar.bottom-bottom.bottom)*1000)/1000;
    });
    expect(await bottomOffset(page)).toBe(await bottomOffset(reference));
    expect(await shellContract(page)).toEqual(await shellContract(reference));
    await page.bringToFront();
    await page.screenshot({path:`test-results/actual-shell-${width}x${height}.png`,fullPage:true});
    await reference.bringToFront();
    await reference.screenshot({path:`test-results/reference-shell-${width}x${height}.png`,fullPage:true});
    if(width<=1180) await expect(page.locator('.mobile-note')).toBeVisible();
    else await expect(page.locator('.mobile-note')).toBeHidden();
    expect(await page.locator('.app').evaluate(el=>getComputedStyle(el).minWidth)).toBe(width<=1180?'1180px':'0px');
    expect(await page.locator('body').evaluate(el=>getComputedStyle(el).overflowX)).toBe(width<=1180?'auto':'hidden');
    await reference.close();
  });
}

test('post-flow runtime log gate covers every owned Compose service',async()=>{
  // Remote inventory, nine log reads and post-scan guards exceed the local budget.
  // Keep the scan and all assertions intact; only bound the complete SSH workflow.
  const scanTimeout=process.env.EID_ENVIRONMENT_CONFIG?300000:60000;
  test.setTimeout(scanTimeout+15000);
  const completed=spawnSync('uv',['run','--frozen','python','-m','scripts.verify_runtime_logs'],{
    cwd:process.cwd(),encoding:'utf8',timeout:scanTimeout,windowsHide:true,
  });
  expect(completed.status,completed.stderr).toBe(0);
  const report=JSON.parse(completed.stdout);
  const services=['postgres','keycloak','rabbitmq','redis','seaweedfs','api','worker','web','nginx'];
  expect(report.passed).toBe(true);
  expect(Object.keys(report.services).sort()).toEqual([...services].sort());
  expect(Object.keys(report.scanned_container_ids).sort()).toEqual([...services].sort());
  expect(report.credential_inventory).toEqual([
    'access_fixture_password',
    'browser_password','keycloak_admin_password','keycloak_monitor_client_secret','postgres_admin_password','postgres_api_password',
    'postgres_migrator_password','postgres_worker_password','rabbitmq_api_password',
    'rabbitmq_bootstrap_admin_password','rabbitmq_worker_password','s3_api_secret_key',
    's3_bootstrap_secret_key','s3_worker_secret_key',
  ]);
  expect(Object.values(report.services as Record<string,{matches:Record<string,number>}>).every(service=>
    Object.values(service.matches).every(count=>count===0)
  )).toBe(true);
  expect(report.runtime_images.services.api.container_id).toBe(report.scanned_container_ids.api);
  expect(report.runtime_images.services.worker.container_id).toBe(report.scanned_container_ids.worker);
  expect(report.runtime_images.services.web.container_id).toBe(report.scanned_container_ids.web);
});
