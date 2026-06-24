<template>
  <template v-if="allowed">
    <slot />
  </template>
  <template v-else>
    <slot name="fallback" />
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

interface Props {
  /** Required role(s); user passes if their role is in the list */
  roles?: Array<'admin' | 'annotator' | 'reviewer' | 'engineer' | 'guest'>
  /** Required permission(s); user passes if any matches */
  permissions?: string[]
  /** When true, render in fallback mode (e.g. read-only) instead of hiding */
  fallbackHide?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  roles: () => [],
  permissions: () => [],
  fallbackHide: false
})

const auth = useAuthStore()

const allowed = computed<boolean>(() => {
  if (!auth.isAuthenticated) return false
  if (props.roles.length === 0 && props.permissions.length === 0) return true
  if (props.roles.length > 0 && !props.roles.includes(auth.role)) return false
  if (props.permissions.length > 0) {
    const userPerms: string[] = (auth.user?.role ? [auth.user.role] : [])
    return props.permissions.some((p) => userPerms.includes(p))
  }
  return true
})
</script>
