import {afterEach,expect,test,vi} from 'vitest';

afterEach(()=>vi.unstubAllGlobals());

test('browser Back blocks a dirty draft before router popstate, but permits clean navigation',async()=>{
 vi.resetModules();
 let listener:(event:PopStateEvent)=>void=()=>{};
 const current={pathname:'/workspaces/w/documents/d',search:'',hash:''};
 const pushState=vi.fn((_state:unknown,_unused:string,path:string)=>{current.pathname=path});
 vi.stubGlobal('window',{location:current,history:{state:{idx:4},pushState},addEventListener:(type:string,handler:(event:PopStateEvent)=>void,capture:boolean)=>{expect(type).toBe('popstate');expect(capture).toBe(true);listener=handler}});
 const {registerDocumentHistoryGuard}=await import('./navigation-guard');
 const attempted:string[]=[];let dirty=true;
 const unregister=registerDocumentHistoryGuard(destination=>{if(!dirty)return false;attempted.push(destination);return true});
 current.pathname='/workspaces/w/documents';const stop=vi.fn();const prevent=vi.fn();
 listener({stopImmediatePropagation:stop,preventDefault:prevent} as unknown as PopStateEvent);
 expect(attempted).toEqual(['/workspaces/w/documents']);expect(stop).toHaveBeenCalledOnce();expect(prevent).toHaveBeenCalledOnce();
 expect(pushState).toHaveBeenCalledWith({idx:4},'', '/workspaces/w/documents/d');
 dirty=false;current.pathname='/workspaces/w/home';listener({stopImmediatePropagation:stop,preventDefault:prevent} as unknown as PopStateEvent);
 expect(stop).toHaveBeenCalledOnce();unregister();
});
