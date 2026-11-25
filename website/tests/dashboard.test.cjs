const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

function harness() {
  const nodes = new Map();
  const storage = new Map();
  const requests = [];
  const handlers = {};
  const node = key => { if (!nodes.has(key)) nodes.set(key, { innerHTML: "", textContent: "", hidden: false, open: false }); return nodes.get(key); };
  const context = vm.createContext({
    console, URL, URLSearchParams, AbortSignal, TextEncoder, Uint8Array,
    crypto: webcrypto, btoa: text => Buffer.from(text, "binary").toString("base64"),
    localStorage: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
    sessionStorage: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
    location: { hash: "", search: "" }, history: { replaceState() {} }, setInterval() {},
    window: { CORAL_CONFIG: { backendURL: "http://127.0.0.1:8000" }, addEventListener() {}, confirm: () => true },
    document: { querySelector: node, querySelectorAll: () => [], activeElement: { tagName: "BODY" }, addEventListener: (name, fn) => handlers[name] = fn },
    fetch: async (url, options) => {
      requests.push({ url, ...options });
      const body = url.endsWith("/profiles") ? { profiles: [{ id: "p", login: "dev", repository: "dev/repo", codespace: "coral-space", state: "available", hermes: 1, error: "" }] } :
        url.endsWith("/usage") ? { remaining_seconds: 14400, used_seconds: 0, session_seconds: 0, inactivity_seconds: 600, history: [], daily: [] } :
        url.endsWith("/tasks") ? { tasks: [] } : url.endsWith("/schedules") ? { schedules: [] } : { notifications: [] };
      return { ok: true, status: 200, json: async () => body };
    }
  });
  vm.runInContext(fs.readFileSync("website/app.js", "utf8"), context);
  return { context, node, requests, evaluate: code => vm.runInContext(code, context) };
}

test("signed-out home is truthful and contains working navigation", () => {
  const h = harness();
  const html = h.node("#content").innerHTML;
  assert.match(html, /Make room for/);
  assert.match(html, /data-action="login"/);
  assert.match(html, /Sleeping/);
  assert.doesNotMatch(html, /42 passing|24% RAM|7 Days/);
  assert.match(h.node("#navigation").innerHTML, /data-page="terminal"/);
});

test("untrusted prompts and output cannot insert executable markup", () => {
  const h = harness();
  const html = h.evaluate(`taskCard({id:'t', prompt:'<img src=x onerror=alert(1)>', output:'</pre><script>alert(1)</script>', status:'succeeded', kind:'hermes', created:1, error:''})`);
  assert.doesNotMatch(html, /<script>|<img src=x/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img src=x/);
});

test("background refresh reads state without extending inactivity", async () => {
  const h = harness();
  h.evaluate("state.token='private-token'");
  await h.evaluate("refresh()");
  assert.equal(h.requests.length, 5);
  assert.ok(h.requests.every(r => r.method === "GET"));
  assert.ok(h.requests.every(r => r.headers.Authorization === "Bearer private-token"));
  assert.ok(h.requests.every(r => !r.url.includes("activity")));
});

test("user typing is throttled but records meaningful activity", async () => {
  const h = harness();
  h.evaluate("state.token='token'"); await h.evaluate("refresh()"); h.requests.length = 0;
  await h.evaluate("activity('chat')"); await h.evaluate("activity('chat')");
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].method, "POST");
  assert.deepEqual(JSON.parse(h.requests[0].body), { kind: "chat" });
});

test("insecure remote backend URLs are rejected before a request", async () => {
  const h = harness(); h.evaluate("state.backend='http://public.example.com'");
  await assert.rejects(h.evaluate("api('/profiles')"), /Use HTTPS/);
  assert.equal(h.requests.length, 0);
});

test("all authenticated screens render the backend contract", async () => {
  const h = harness(); h.evaluate("state.token='token'"); await h.evaluate("refresh()");
  for (const page of ["home", "workspace", "files", "terminal", "schedules", "usage", "extended", "profiles", "settings"]) {
    h.evaluate(`state.page='${page}';render()`);
    assert.ok(h.node("#content").innerHTML.length > 100, page);
    assert.doesNotMatch(h.node("#content").innerHTML, /undefined/, page);
  }
});
