import { cp, mkdir, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
const root = resolve('.');
await rm(resolve(root,'dist'), {recursive:true, force:true});
await mkdir(resolve(root,'dist'), {recursive:true});
await cp(resolve(root,'src'), resolve(root,'dist'), {recursive:true});
await mkdir(resolve(root,'dist','assets'), {recursive:true});
await cp(resolve(root,'public','assets'), resolve(root,'dist','assets'), {recursive:true});
console.log('Assurley production bundle created in dist/');
