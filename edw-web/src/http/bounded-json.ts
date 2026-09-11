export async function boundedJson(response:Response,maxBytes:number,invalidMessage:string):Promise<unknown>{
  const declared=response.headers.get('content-length');
  if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>maxBytes)){
    await response.body?.cancel().catch(()=>{});
    throw new Error(invalidMessage);
  }
  if(!response.body)throw new Error(invalidMessage);
  const reader=response.body.getReader();const chunks:Uint8Array[]=[];let size=0;
  try{
    while(true){const {done,value}=await reader.read();if(done)break;if(value){size+=value.byteLength;if(size>maxBytes){await reader.cancel().catch(()=>{});throw new Error(invalidMessage)}chunks.push(value)}}
  }finally{reader.releaseLock()}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength}
  try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)) as unknown}catch{throw new Error(invalidMessage)}
}
