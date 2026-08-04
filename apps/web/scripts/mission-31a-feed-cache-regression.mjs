import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "lib/api.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const apiModule = { exports: {} };

let feedRequests = 0;
let failNextMutation = false;
globalThis.fetch = async (url, options = {}) => {
  const isFeed = String(url).includes("/feed?");
  if (isFeed) feedRequests += 1;
  const failed = !isFeed && failNextMutation;
  failNextMutation = false;
  return {
    ok: !failed,
    status: failed ? 500 : 200,
    statusText: failed ? "mutation_failed" : "OK",
    json: async () => isFeed
      ? { symbol: "PETR4", count: 0, posts: [], version: feedRequests }
      : failed ? { detail: "mutation_failed" } : { likes: 1, status: "ok" },
  };
};

new Function("exports", "module", "require", "process", compiled)(
  apiModule.exports,
  apiModule,
  require,
  process,
);
const api = apiModule.exports;
assert.equal(api.resolveMediaUrl("/media/posts/photo.png"), "http://127.0.0.1:8000/media/posts/photo.png");
assert.equal(api.resolveMediaUrl("https://media.tenor.com/reaction.gif"), "https://media.tenor.com/reaction.gif");

const first = await api.getFeed("token", "PETR4");
const cached = await api.getFeed("token", "PETR4");
assert.equal(feedRequests, 1, "normal feed reads must share the 15s cache");
assert.equal(cached.version, first.version);

for (const mutate of [
  () => api.createPost("token", "PETR4", { text: "new" }),
  () => api.commentOnPost("token", 1, { text: "comment" }),
  () => api.likePost("token", 1),
  () => api.muteUser("token", 2),
  () => api.followUser("token", 2),
  () => api.deletePost("token", 1),
]) {
  const before = feedRequests;
  await mutate();
  await api.getFeed("token", "PETR4");
  assert.equal(feedRequests, before + 1, "successful social mutation must invalidate feed cache");
}

failNextMutation = true;
await assert.rejects(api.likePost("token", 1), /mutation_failed/);
const beforeFailedRefresh = feedRequests;
await api.getFeed("token", "PETR4");
assert.equal(feedRequests, beforeFailedRefresh, "failed mutation must preserve the existing feed cache");

console.log("mission-31a-feed-cache-regression: ok");
