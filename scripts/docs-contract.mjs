import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const local = path.join(root, 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const executable = existsSync(local) ? local : process.platform === 'win32' ? 'py' : 'python3';
const prefix = executable === 'py' ? ['-3'] : [];
const flags = process.argv.slice(2);
if (flags.some(flag => !['--check', '--write', '--check-design', '--check-blueprint'].includes(flag))) {
  console.error('Unsupported documentation-check option');
  process.exit(2);
}
const result = spawnSync(executable, [...prefix, '-B', path.join(root, 'scripts/docs_contract.py'), ...flags], {
  cwd: root, stdio: 'inherit', shell: false, timeout: 60000,
});
if (result.error) console.error(`Documentation check could not start: ${result.error.code ?? 'unknown error'}`);
process.exit(result.status ?? 1);
