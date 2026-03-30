import fs from "node:fs";
import path from "node:path";

const serverDir = path.join(process.cwd(), ".next", "server");
const chunkDir = path.join(serverDir, "chunks");

if (!fs.existsSync(serverDir) || !fs.existsSync(chunkDir)) {
  process.exit(0);
}

const entries = fs.readdirSync(chunkDir, { withFileTypes: true });
const staticChunksDir = path.join(process.cwd(), ".next", "static", "chunks");

for (const entry of entries) {
  if (!entry.isFile() || !entry.name.endsWith(".js")) continue;

  const source = path.join(chunkDir, entry.name);
  const target = path.join(serverDir, entry.name);

  fs.copyFileSync(source, target);
}

const legacyClientChunkAliases = {
  "478": [
    "478-355f6c2217832b99.js",
    "478-ed1d87b6da30a916.js",
  ],
};

if (fs.existsSync(staticChunksDir)) {
  const staticEntries = fs.readdirSync(staticChunksDir);

  for (const [chunkId, aliases] of Object.entries(legacyClientChunkAliases)) {
    const currentChunk = staticEntries.find((name) => name.startsWith(`${chunkId}-`) && name.endsWith(".js"));
    if (!currentChunk) continue;

    const source = path.join(staticChunksDir, currentChunk);

    for (const alias of aliases) {
      if (alias === currentChunk) continue;
      const target = path.join(staticChunksDir, alias);
      fs.copyFileSync(source, target);
    }
  }
}

console.log("Synced Next server chunks to root server directory.");
