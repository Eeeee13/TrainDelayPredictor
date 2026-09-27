import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
const directory = await mkdtemp(join(tmpdir(), 'vehicle-animation-tests-'));
try {
  const outfile = join(directory, 'tests.mjs');
  await build({ entryPoints: [new URL('./vehicleAnimator.test.ts', import.meta.url).pathname], outfile, bundle: true, platform: 'node', format: 'esm' });
  const result = spawnSync(process.execPath, ['--test', outfile], { stdio: 'inherit' });
  process.exitCode = result.status ?? 1;
} finally {
  await rm(directory, { recursive: true, force: true });
}
