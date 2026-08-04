import assert from "node:assert/strict";
import fs from "node:fs";

const component = fs.readFileSync(new URL("../components/image-lightbox.tsx", import.meta.url), "utf8");
const shell = fs.readFileSync(new URL("../components/workspace-shell.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

assert.match(shell, /<ImageLightbox src=\{resolveMediaUrl\(post\.image_url\)\}/);
assert.match(shell, /<ImageLightbox src=\{resolveMediaUrl\(comment\.image_url\)\}/);
assert.match(component, /aria-label=\{english \? "Enlarge image" : "Ampliar imagem"\}/);
assert.match(component, /onCancel=.*close\(\)/s);
assert.match(component, /event\.target === event\.currentTarget/);
assert.match(component, /className="snbr-lightbox-stage"[\s\S]*?onClick=/);
assert.match(component, /onWheel=/);
assert.match(component, /onDoubleClick=/);
assert.match(component, /setPointerCapture/);
assert.match(component, /document\.body\.style\.overflow = "hidden"/);
assert.match(api, /url\.startsWith\("\/media\/"\) \? `\$\{resolveApiBase\(\)\}\$\{url\}`/);

console.log("image lightbox regression: ok");
