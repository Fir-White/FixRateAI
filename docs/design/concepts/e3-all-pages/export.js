// Read-only official native exports. Supply FRAMES. Limit exporter concurrency to three.
const queue=[...FRAMES],result=[];
async function worker(){while(queue.length){const f=queue.shift(),p=penpot.currentFile.pages.find(p=>p.id===f.pageId),r=p.getShapeById(f.id),start=Date.now(),bytes=await r.export({type:'png',scale:1});let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.slice(i,i+8192));result.push({key:f.key,width:r.width,height:r.height,bytes:bytes.length,ms:Date.now()-start,png:btoa(binary)});}}
await Promise.all([worker(),worker(),worker()]);return result;
