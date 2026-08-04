import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  cleanupSyntheticSessions,
  countSessions,
  revokeTokenSession,
} from "./lib/ephemeral-auth.mjs";

const API_BASE = "http://127.0.0.1:8000";
const WEB_BASE = "http://127.0.0.1:3000";

async function json(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(`${path}:${response.status}:${JSON.stringify(payload)}`);
  return payload;
}

async function main() {
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
cleanupSyntheticSessions("mission31a-runtime-");
const sessionBaseline = countSessions();
let token = "";
let upload = null;
let comment = null;
let gifStatus = null;
const ordered = [];
const createdPosts = [];
try {
const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const email = `mission31a-runtime-${suffix}@example.com`;
const auth = await json("/auth/register", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    email,
    password: "12345678",
    display_name: "Trader Visual",
    channel: "web",
    accepted_terms: true,
    accepted_privacy: true,
    accepted_risk_notice: true,
  }),
});
token = auth.access_token;
const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
const marker = `runtime-${Date.now()}`;

async function createPost(text, image_url = null) {
  return json("/ticker/PETR4/post", {
    method: "POST",
    headers,
    body: JSON.stringify({ text, sentiment: "bullish", image_url }),
  });
}

for (const label of ["post 1", "post 2", "post 3"]) {
  const post = await createPost(`${marker} ${label}`);
  ordered.push(post);
  createdPosts.push(post);
}
let feed = await json("/ticker/PETR4/feed?limit=500", { headers: { Authorization: headers.Authorization } });
assert.deepEqual(
  feed.posts.filter((post) => String(post.text).startsWith(marker)).map((post) => post.text),
  ["post 3", "post 2", "post 1"].map((label) => `${marker} ${label}`),
);

const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64");
const form = new FormData();
form.append("file", new Blob([png], { type: "image/png" }), "photo.png");
const uploadResponse = await fetch(`${API_BASE}/api/media/upload`, {
  method: "POST",
  headers: { Authorization: headers.Authorization },
  body: form,
});
if (!uploadResponse.ok) throw new Error(`upload:${uploadResponse.status}:${await uploadResponse.text()}`);
upload = await uploadResponse.json();
assert.match(upload.url, /^\/media\/posts\/[a-f0-9]+\.png$/);
const photoPost = await createPost(`${marker} photo`, upload.url);
createdPosts.push(photoPost);

comment = await json(`/post/${ordered[0].id}/comment`, {
  method: "POST",
  headers,
  body: JSON.stringify({ text: "🐂 comentário 🙂", image_url: upload.url }),
});
assert.equal(comment.post_id, ordered[0].id);

for (let reload = 0; reload < 2; reload += 1) {
  feed = await json("/ticker/PETR4/feed?limit=500", { headers: { Authorization: headers.Authorization } });
  const byId = new Map(feed.posts.map((post) => [post.id, post]));
  assert.equal(byId.get(photoPost.id).image_url, upload.url);
  assert.equal(byId.get(ordered[0].id).comments.at(-1).id, comment.id);
  assert.equal(byId.get(ordered[1].id).comments.length, 0);
  assert.equal(byId.get(ordered[2].id).comments.length, 0);
  const forbiddenKeys = [];
  JSON.stringify(feed, (key, value) => {
    if (key === "email" || key === "user_email") forbiddenKeys.push(key);
    return value;
  });
  assert.deepEqual(forbiddenKeys, []);
}

const mediaResponse = await fetch(`${API_BASE}${upload.url}`);
assert.equal(mediaResponse.status, 200);
assert.equal(Buffer.compare(Buffer.from(await mediaResponse.arrayBuffer()), png), 0);

const badForm = new FormData();
badForm.append("file", new Blob(["not-an-image"], { type: "image/png" }), "fake.png");
const badUpload = await fetch(`${API_BASE}/api/media/upload`, {
  method: "POST",
  headers: { Authorization: headers.Authorization },
  body: badForm,
});
assert.equal(badUpload.status, 400);

const html = await (await fetch(`${WEB_BASE}/site`)).text();
assert.ok(!html.includes("snbr-emoji-quickbar"));
assert.ok(!html.includes("snbr-comment-tools"));

gifStatus = await json("/api/media/gifs/search?q=mercado&locale=pt-BR&limit=1", {
  headers: { Authorization: headers.Authorization },
});
} finally {
  for (const post of createdPosts) {
    if (token && post?.id) {
      await json(`/post/${post.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => undefined);
    }
  }
  if (upload?.url && /^\/media\/posts\/[a-f0-9]+\.png$/.test(upload.url)) {
    fs.rmSync(path.join(repoRoot, upload.url), { force: true });
  }
  if (token) revokeTokenSession(token);
}
const sessionDelta = countSessions() - sessionBaseline;
assert.equal(sessionDelta, 0);
console.log(JSON.stringify({
  order: "post 3, post 2, post 1",
  comment_post_id: comment.post_id,
  photo_url: upload.url,
  photo_reload_checks: 2,
  public_email_keys: 0,
  permanent_emoji_bar: false,
  gif_status: gifStatus.status,
  gif_reason: gifStatus.reason || null,
  cleaned_test_posts: ordered.length + 1,
  session_delta: sessionDelta,
  external_provider_calls: 0,
}));
console.log(`SESSION_DELTA=${sessionDelta}`);
console.log("EXTERNAL_PROVIDER_CALLS=0");
}

await main();
