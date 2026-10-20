/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public, build-time API base path. Never put secrets in VITE_ variables. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
