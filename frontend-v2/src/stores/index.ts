/**
 * Barrel export for all Pinia stores.
 *
 * Centralises the import surface so consumers can write:
 *     import { useCommandStore } from '@/stores'
 * instead of remembering individual file paths.
 *
 * Re-exports are listed alphabetically by store name for predictability.
 */
export { useAuthStore } from './auth'
export { useCommandStore } from './command'
export { useLocaleStore } from './locale'
export { useQuickNavStore } from './quicknav'
export { useThemeStore } from './theme'
export { useUiStore } from './ui'
export { useUploadStore } from './upload'
export { useApiStore } from './api'