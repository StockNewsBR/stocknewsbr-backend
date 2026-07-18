import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "components/workspace-shell.tsx"), "utf8");
const types = fs.readFileSync(path.join(root, "lib/types.ts"), "utf8");

assert.match(source, /useState\(false\).*composerEmojiOpen|composerEmojiOpen.*useState\(false\)/s);
assert.ok(!source.includes("snbr-emoji-quickbar"));
assert.ok(!source.includes("COMPOSER_QUICK_EMOJIS"));
assert.match(source, /commentComposers\[post\.id\]\?\.active\s*\?\s*\(/);
assert.match(source, /data-comment-composer=\{post\.id\}/);
assert.match(source, /data-comment-input=\{post\.id\}/);
assert.match(source, /Touro/);
assert.match(source, /Urso/);
assert.match(source, /Adicionar foto à resposta/);
assert.match(source, /Adicionar emoji à resposta/);
assert.ok(!source.includes("post.user_email"));
assert.ok(!source.includes("comment.user_email"));
assert.ok(!types.includes("user_email"));
assert.ok(source.includes("Escreva sua ideia para ${selectedTicker}"));
assert.ok(source.includes("Write your idea for ${selectedTicker}"));
assert.ok(source.includes("Busca de GIF indisponível no momento"));
assert.ok(source.includes("const [pollOpen, setPollOpen] = useState(false)"));
assert.ok(source.includes("const [accessOpen, setAccessOpen] = useState(false)"));
assert.match(source, /<h3>✦ \{isUsLocale \? "Vote" : "Votar"\}<\/h3>/);
assert.match(source, /aria-expanded=\{pollOpen\}/);
assert.match(source, /aria-expanded=\{accessOpen\}/);
assert.match(source, /<textarea\s+data-comment-input=\{post\.id\}/);

const discussion = source.slice(source.indexOf("function renderDiscussionList"), source.indexOf("function renderSearchTab"));
assert.equal((discussion.match(/<SentimentLabel/g) || []).length, 1, "post sentiment must render once");
assert.ok(!discussion.includes("snbr-social-guardian-pill"));
assert.ok(!discussion.includes("Guardian Amarelo"));
assert.ok(!discussion.includes("Guardian Verde"));

const mainFileChange = source.match(/onChange=\{\(event\) => \{\s*setPostFile[\s\S]*?setSelectedGif\(null\);\s*\}\}/)?.[0] || "";
assert.ok(mainFileChange && !mainFileChange.includes("setPostText"), "selecting a photo must preserve post text");
const removeAttachment = source.match(/aria-label=\{isUsLocale \? "Remove attachment"[\s\S]*?type="button"/)?.[0] || "";
assert.ok(removeAttachment && !removeAttachment.includes("setPostText"), "removing media must preserve post text");
assert.match(source, /selectCommentFile\(post\.id, event\.target\.files\?\.\[0\] \|\| null\)/);
assert.match(source, /text: `\$\{sentiment\} \$\{applyEmojiShortcuts\(text\)\}`\.trim\(\),\s*image_url: imageUrl/);

console.log("mission-31a-social-composer-regression: ok");
