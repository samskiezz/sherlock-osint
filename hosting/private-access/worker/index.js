// Private HTTPS access to the existing app. No host commands or arbitrary upstream URLs.
const PREFIX = '/__sherlock_relay/';
const TTL = 85000;
const MAX_INPUT = 32 * 1024 * 1024;
const MAX_OUTPUT = 256 * 1024 * 1024;
const METHODS = new Set(['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS']);
const HEADERS = ['content-type','content-disposition','content-range','accept-ranges','etag','last-modified','cache-control'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const json = (data, status=200) => Response.json(data, {status, headers:{'Cache-Control':'no-store'}});
function permitted(path) {
  return path === '/' || path.startsWith('/api/') || path.startsWith('/assets/') || path.startsWith('/pdfjs/') || path === '/favicon.ico';
}
async function putBody(bucket,key,request,limit) {
  const rawLength=request.headers.get('content-length');
  if(rawLength!==null) {
    const length=Number(rawLength);
    if(!Number.isSafeInteger(length)||length<0||length>limit)throw new Error('Transfer limit exceeded');
    // Preserve the runtime's known-length request stream required by R2.
    return bucket.put(key,request.body);
  }
  // Unknown-length bodies use a smaller bounded buffer, never an unbounded stream.
  const ceiling=Math.min(limit,32*1024*1024), chunks=[];
  let size=0;
  const reader=request.body.getReader();
  while(true) {const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>ceiling){await reader.cancel();throw new Error('Transfer limit exceeded');}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  return bucket.put(key,bytes);
}
async function remove(bucket, id) {
  await bucket.delete(['pending/'+id,'ticket/'+id,'input/'+id,'output/'+id,'response/'+id]);
}
export default {
  async fetch(request, env, ctx) {
    let url = new URL(request.url);
    let serviceCheck = false;
    if (!env.BUCKET || !env.RELAY_SECRET) return json({detail:'Private access is being configured.'},503);
    if (url.pathname.startsWith(PREFIX)) {
      if (request.headers.get('X-Sherlock-Relay-Key') !== env.RELAY_SECRET) return json({detail:'Unauthorised relay request'},403);
      const command = url.pathname.slice(PREFIX.length);
      if (command === 'heartbeat' && request.method === 'POST') {
        await env.BUCKET.put('heartbeat', JSON.stringify({at:Date.now()}));
        return json({ok:true});
      }
      if (command === 'pull' && request.method === 'POST') {
        const listing = await env.BUCKET.list({prefix:'pending/',limit:8});
        const jobs = [];
        for (const entry of listing.objects) {
          const object = await env.BUCKET.get(entry.key);
          if (!object) continue;
          const job = await object.json();
          if (Date.now() - job.created > TTL) { await remove(env.BUCKET,job.id); continue; }
          jobs.push(job);
          await env.BUCKET.delete(entry.key);
        }
        return json({jobs});
      }
      if (command === 'check' && request.method === 'GET') {
        const target=url.searchParams.get('path') || '/';
        if (!target.startsWith('/') || target.startsWith('//') || target.includes('\\')) return json({detail:'Invalid probe path'},400);
        const destination=new URL(target,url.origin);
        if (!permitted(destination.pathname)) return json({detail:'Probe route unavailable'},404);
        serviceCheck=true;url=destination;
      }
      if (!serviceCheck) {
      const id = url.searchParams.get('id') || '';
      if (!/^[a-f0-9-]{36}$/.test(id)) return json({detail:'Invalid ticket'},400);
      const ticketObject = await env.BUCKET.get('ticket/'+id);
      if (!ticketObject) return json({detail:'Ticket expired'},410);
      const ticket = await ticketObject.json();
      if (Date.now() - ticket.created > TTL) { await remove(env.BUCKET,id); return json({detail:'Ticket expired'},410); }
      if (command === 'input' && request.method === 'GET') {
        const body = await env.BUCKET.get('input/'+id);
        return body ? new Response(body.body) : new Response(null,{status:204});
      }
      if (command === 'respond' && request.method === 'POST') {
        const status = Number(request.headers.get('X-Sherlock-Status'));
        if (!Number.isInteger(status) || status < 200 || status > 599) return json({detail:'Invalid response'},400);
        let metadata;
        try {metadata=JSON.parse(decodeURIComponent(request.headers.get('X-Sherlock-Headers') || '%7B%7D'));}
        catch {return json({detail:'Invalid response headers'},400);}
        const headers={};
        for (const k of HEADERS) if (typeof metadata[k] === 'string') headers[k]=metadata[k].slice(0,2000);
        if (request.body) await putBody(env.BUCKET,'output/'+id,request,MAX_OUTPUT);
        // Publish completion only after the full response object exists.
        if (!(await env.BUCKET.head('ticket/'+id))) { await env.BUCKET.delete('output/'+id); return json({detail:'Ticket expired'},410); }
        await env.BUCKET.put('response/'+id,JSON.stringify({status,headers}));
        return json({ok:true});
      }
      return json({detail:'Unknown relay operation'},404);
      }
    }
    // Sites must confirm owner-only access. Service tokens supply no visitor identity.
    if (!serviceCheck && !(request.headers.get('oai-authenticated-user-id') || (env.OWNER_EMAIL && request.headers.get('oai-authenticated-user-email')?.toLowerCase()===env.OWNER_EMAIL.toLowerCase()))) return json({detail:'Open this private Site while signed into its owner account.'},401);
    if (!METHODS.has(request.method) || !permitted(url.pathname)) return json({detail:'Route unavailable'},404);
    if (!['GET','HEAD','OPTIONS'].includes(request.method)) {
      const origin=request.headers.get('origin');
      if (origin && origin!==url.origin) return json({detail:'Cross-origin request rejected'},403);
    }
    const heartbeat=await env.BUCKET.get('heartbeat');
    if (!heartbeat || Date.now()-(await heartbeat.json()).at>20000) return new Response('SHERLOCK is temporarily disconnected from its investigation workspace. Reload shortly.',{status:503,headers:{'Content-Type':'text/plain','Retry-After':'5'}});
    const size=Number(request.headers.get('content-length') || 0);
    if (size>MAX_INPUT) return json({detail:'Upload exceeds the 32 MiB remote-access limit'},413);
    const id=crypto.randomUUID(), created=Date.now();
    const headers={};
    for (const name of ['content-type','range','if-none-match']) {
      const value=request.headers.get(name);if(value)headers[name]=value;
    }
    const job={id,created,method:request.method,path:url.pathname+url.search,headers,has_body:!!request.body};
    try {
      if (request.body) await putBody(env.BUCKET,'input/'+id,request,MAX_INPUT);
      await env.BUCKET.put('ticket/'+id,JSON.stringify({created}));
      await env.BUCKET.put('pending/'+id,JSON.stringify(job));
      let attempts=0;
      while (Date.now()-created<TTL) {
        const result=await env.BUCKET.get('response/'+id);
        if (result) {
          const response=await result.json();
          const body=await env.BUCKET.get('output/'+id);
          const outHeaders=new Headers(response.headers);
          // Responses can contain private evidence. Never cache the mailbox response publicly.
          outHeaders.set('Cache-Control','private, no-store');
          outHeaders.set('X-Content-Type-Options','nosniff');
          // R2 streams remain readable after deletion. Delete transient request/response objects.
          ctx.waitUntil(remove(env.BUCKET,id));
          return new Response(request.method==='HEAD'||[204,304].includes(response.status)?null:body?.body,{status:response.status,headers:outHeaders});
        }
        await sleep(attempts++<6?200:2500);
      }
      ctx.waitUntil(remove(env.BUCKET,id));
      return json({detail:'The investigation workspace did not respond in time. Check job history before retrying a write.'},504);
    } catch (_) {
      ctx.waitUntil(remove(env.BUCKET,id));
      return json({detail:'The private connection could not complete this request.'},502);
    }
  }
};
