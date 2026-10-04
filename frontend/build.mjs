import { cp, mkdir, rm, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve('.');
const dist = resolve(root, 'dist');
const apiUrl = (process.env.ASSURLEY_API_URL || '').replace(/\/$/, '');

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

await cp(resolve(root, 'src'), dist, { recursive: true });
await mkdir(resolve(dist, 'assets'), { recursive: true });
await cp(resolve(root, 'public', 'assets'), resolve(dist, 'assets'), { recursive: true });

// Inject the production backend URL at build time.
// If empty, the frontend uses same-origin /api routes (useful for local/dev fallback).
const configPath = resolve(dist, 'config.js');
const config = await readFile(configPath, 'utf8');
await writeFile(
  configPath,
  config.replace('__ASSURLEY_API_URL__', apiUrl)
);

console.log(`Assurley production bundle created in dist/ (API: ${apiUrl || 'same-origin /api'})`);
