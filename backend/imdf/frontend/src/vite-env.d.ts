/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
  readonly VITE_T8_STRICT_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module 'virtual:t8-local-extensions' {
  import type { ComponentType } from 'react';
  export const LocalModalSlot: ComponentType;
  export const LocalTopbarSlot: ComponentType<{ isPixel: boolean; isDark: boolean }>;
}

declare module '*.css';
declare module '*.svg';
declare module '*.png';
declare module '*.jpg';
