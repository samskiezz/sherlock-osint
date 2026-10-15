import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import worker from '../worker/index.js';
globalThis.crypto ||= webcrypto;
class Bucket {
 constructor(){this.data=new Map()}
 async put(k,v){const body=typeof v==='string'?new TextEncoder().encode(v):new Uint8Array(await new Response(v).arrayBuffer());this.data.set(k,body)}
 async get(k){const v=this.data.get(k);return v?{json:async()=>JSON.parse(new TextDecoder().decode(v)),body:new ReadableStream({start(c){c.enqueue(v);c.close()}})}:null}
 async head(k){return this.data.has(k)?{}:null}
 async delete(k){for(const x of Array.isArray(k)?k:[k])this.data.delete(x)}
 async list({prefix,limit}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).slice(0,limit).map(key=>({key}))}}
}
function fixture(){return {env:{BUCKET:new Bucket(),RELAY_SECRET:'owned-test-secret'},ctx:{waitUntil:p=>p}}}
const req=(path,options={})=>new Request('https://owned.example'+path,options);
const service={"X-Sherlock-Relay-Key":"owned-test-secret"};
test('reject missing owner identity and incorrect agent secret',async()=>{const {env,ctx}=fixture();assert.equal((await worker.fetch(req('/'),env,ctx)).status,401);assert.equal((await worker.fetch(req('/__sherlock_relay/pull',{method:'POST'}),env,ctx)).status,403)});
test('offline workspace and cross-origin writes remain explicit',async()=>{const{env,ctx}=fixture();const owner={'oai-authenticated-user-id':'owned-user'};assert.equal((await worker.fetch(req('/',{headers:owner}),env,ctx)).status,503);assert.equal((await worker.fetch(req('/api/jobs',{method:'POST',headers:{...owner,origin:'https://other.example'}}),env,ctx)).status,403)});
test('actual request and binary response round trip; mailbox objects deleted',async()=>{const{env,ctx}=fixture();await worker.fetch(req('/__sherlock_relay/heartbeat',{method:'POST',headers:service}),env,ctx);const responsePromise=worker.fetch(req('/api/evidence/OWNED/file',{headers:{'oai-authenticated-user-id':'owned-user',range:'bytes=0-3'}}),env,ctx);let jobs=[];for(let i=0;i<30&&!jobs.length;i++){jobs=(await(await worker.fetch(req('/__sherlock_relay/pull',{method:'POST',headers:service}),env,ctx)).json()).jobs;if(!jobs.length)await new Promise(r=>setTimeout(r,10));}assert.equal(jobs.length,1);const job=jobs[0];assert.equal(job.headers.range,'bytes=0-3');assert.equal(job.path,'/api/evidence/OWNED/file');const ack=await worker.fetch(req('/__sherlock_relay/respond?id='+job.id,{method:'POST',headers:{...service,'X-Sherlock-Status':'206','X-Sherlock-Headers':encodeURIComponent(JSON.stringify({'content-type':'image/png','content-range':'bytes 0-3/10'}))},body:new Uint8Array([0,255,42,128])}),env,ctx);assert.equal(ack.status,200);const response=await responsePromise;assert.equal(response.status,206);assert.deepEqual([...new Uint8Array(await response.arrayBuffer())],[0,255,42,128]);assert.equal(response.headers.get('content-range'),'bytes 0-3/10');await new Promise(r=>setTimeout(r,10));assert.equal(env.BUCKET.data.size,1)});
test('deny arbitrary proxy paths and expired response tickets',async()=>{const{env,ctx}=fixture();assert.equal((await worker.fetch(req('/etc/passwd',{headers:{'oai-authenticated-user-id':'owned-user'}}),env,ctx)).status,404);assert.equal((await worker.fetch(req('/__sherlock_relay/respond?id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',{method:'POST',headers:{...service,'X-Sherlock-Status':'200'}}),env,ctx)).status,410)});
