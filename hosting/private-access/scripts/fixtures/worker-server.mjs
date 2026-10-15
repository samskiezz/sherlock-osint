// Loopback-only integration fixture. The production Worker runs unchanged;
// this in-memory bucket replaces R2 and contains only owned synthetic data.
import http from 'node:http';
import {webcrypto} from 'node:crypto';
import worker from '../../worker/index.js';
globalThis.crypto ||= webcrypto;

class Bucket {
  data = new Map();
  async put(key, value) {
    this.data.set(key, typeof value === 'string' ? new TextEncoder().encode(value)
      : new Uint8Array(await new Response(value).arrayBuffer()));
  }
  async get(key) {
    const value = this.data.get(key);
    return value ? {
      json: async () => JSON.parse(new TextDecoder().decode(value)),
      body: new ReadableStream({start(controller) {controller.enqueue(value); controller.close();}}),
    } : null;
  }
  async head(key) {return this.data.has(key) ? {} : null;}
  async delete(key) {for (const item of Array.isArray(key) ? key : [key]) this.data.delete(item);}
  async list({prefix, limit}) {
    return {objects: [...this.data.keys()].filter(key => key.startsWith(prefix)).slice(0, limit).map(key => ({key}))};
  }
}
const env = {BUCKET: new Bucket(), RELAY_SECRET: 'owned-fixture-relay-secret'};
const server = http.createServer(async (incoming, outgoing) => {
  try {
    if (incoming.url === '/__fixture/ready') {
      outgoing.writeHead(env.BUCKET.data.has('heartbeat') ? 200 : 503);
      outgoing.end();
      return;
    }
    if (incoming.url.startsWith('/__sherlock_relay/')
        && incoming.headers['oai-sites-authorization'] !== 'Bearer owned-fixture-service-token') {
      outgoing.writeHead(401); outgoing.end(); return;
    }
    const parts = []; let size = 0;
    for await (const part of incoming) {
      size += part.length;
      if (size > 1024 * 1024) throw new Error('Fixture transfer limit');
      parts.push(part);
    }
    const request = new Request('https://owned-fixture.chatgpt.site' + incoming.url, {
      method: incoming.method, headers: incoming.headers,
      ...(!['GET', 'HEAD'].includes(incoming.method) && size ? {body: Buffer.concat(parts)} : {}),
    });
    const response = await worker.fetch(request, env, {waitUntil: promise => promise.catch(() => {})});
    outgoing.writeHead(response.status, Object.fromEntries(response.headers));
    outgoing.end(Buffer.from(await response.arrayBuffer()));
  } catch {
    outgoing.writeHead(500); outgoing.end('Owned fixture failed');
  }
});
server.listen(0, '127.0.0.1', () => console.log(JSON.stringify({port: server.address().port})));
