/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CONSOLE_DEMO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
