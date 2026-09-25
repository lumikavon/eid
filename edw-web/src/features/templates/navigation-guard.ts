type Guard={path:string;state:unknown;shouldBlock:(destination:string)=>boolean};
let active:Guard|null=null;
let installed=false;

/** Capture browser Back/Forward before BrowserRouter handles popstate. Never store draft content. */
export function registerDocumentHistoryGuard(shouldBlock:Guard['shouldBlock']):()=>void{
 if(typeof window==='undefined')return()=>{};
 if(!installed){window.addEventListener('popstate',event=>{
  const guard=active;if(!guard)return;
  const destination=window.location.pathname+window.location.search+window.location.hash;
  if(destination===guard.path||!guard.shouldBlock(destination))return;
  event.stopImmediatePropagation();event.preventDefault();
  // Back already changed the address; restore the document without a second popstate.
  window.history.pushState(guard.state,'',guard.path);
 },true);installed=true}
 const guard:Guard={path:window.location.pathname+window.location.search+window.location.hash,state:window.history.state,shouldBlock};
 active=guard;
 return()=>{if(active===guard)active=null};
}
