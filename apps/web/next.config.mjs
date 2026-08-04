import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * outputFileTracingRoot must point at the monorepo root (the directory that
 * contains apps/web and apps/mobile), not at the user's home directory. The
 * Next.js build otherwise walks up the filesystem, finds /home/dcima/package-lock.json
 * (an unrelated lockfile outside the repo) and incorrectly infers that as the
 * workspace root, emitting the "multiple lockfiles" warning.
 *
 * The path is derived from this config file so it stays portable across WSL,
 * Linux CI, and any other checkout path. apps/web/next.config.mjs -> ../.. is
 * the monorepo root containing apps/*.
 */
const monorepoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: monorepoRoot,
};

export default nextConfig;
