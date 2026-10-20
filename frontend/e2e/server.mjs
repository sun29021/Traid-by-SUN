// Starts a production Traid server for end-to-end tests on a throwaway data folder.
// Used by playwright.config.ts (webServer). Never points at the real data/ folder.
import { spawn } from 'node:child_process';
import { rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(here, '..', '..', 'backend');
const dataDir = resolve(here, '..', '.e2e-data');
const python =
  process.platform === 'win32'
    ? join(backendDir, '.venv', 'Scripts', 'python.exe')
    : join(backendDir, '.venv', 'bin', 'python');

rmSync(dataDir, { recursive: true, force: true });

const server = spawn(python, ['-m', 'app'], {
  cwd: backendDir,
  stdio: 'inherit',
  env: {
    ...process.env,
    TRAID_ENV: 'production',
    TRAID_PORT: process.env.E2E_PORT ?? '8766',
    TRAID_DATA_DIR: dataDir,
    TRAID_LOG_LEVEL: 'WARNING',
  },
});

const stop = () => server.kill();
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
process.on('exit', stop);
server.on('exit', (code) => process.exit(code ?? 0));
