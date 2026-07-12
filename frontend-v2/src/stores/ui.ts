import { defineStore } from 'pinia'

/**
 * Pinia store: ui
 *
 * Drives app-wide UI affordances that don't belong to a domain store:
 *  - Global modal flags (search palette open, shortcut help open,
 *    upload drawer open, command palette state)
 *  - Toast queue (lightweight; Naive UI's useMessage is the canonical
 *    surface, but this lets us inspect/replay toasts in tests)
 *  - Notification center (bell dropdown state + recent notifications)
 *  - User menu (avatar dropdown state)
 *  - Sidebar collapse flag
 *
 * Persistence: ephemeral by design — reloading closes all modals.
 * The store is just a typed registry of cross-component flags.
 */

export interface ToastEntry {
  id: string
  type: 'info' | 'success' | 'warning' | 'error'
  content: string
  /** ms epoch — drives auto-dismiss. */
  createdAt: number
  /** ms; 0 = no auto-dismiss. */
  duration: number
}

/**
 * P20-O: Notification entry surfaced by the bell. Matches the wire shape
 * used by /api/v1/notifications and the WebSocket stream
 * (`/ws/notifications`).
 */
export interface NotificationEntry {
  id: string
  title: string
  body?: string
  /** info | success | warning | error — Naive UI tag colour. */
  level: 'info' | 'success' | 'warning' | 'error'
  read: boolean
  /** ISO-8601 string; the bell sorts by this desc. */
  createdAt: string
  /** Optional deep link target; the bell pushes router if present. */
  link?: string
  /** Source service tag — e.g. annotation, project, billing. */
  source?: string
}

interface UiState {
  searchPaletteOpen: boolean
  shortcutHelpOpen: boolean
  uploadDrawerOpen: boolean
  /** When true, command palette listens for ⌘K / Ctrl+K. */
  globalSearchEnabled: boolean
  toasts: ToastEntry[]
  /** P20-O: notification center state. */
  notifications: NotificationEntry[]
  /** P20-O: caps the number of notifications kept in memory. */
  notificationMax: number
  /** P20-O: bell dropdown is open. */
  notificationCenterOpen: boolean
  /** P20-O: WebSocket status for the bell (visible to user). */
  notificationStreamStatus: 'idle' | 'connecting' | 'open' | 'closed' | 'error'
  /** P20-O: user avatar menu open. */
  userMenuOpen: boolean
  /** P20-O: whether the sidebar is collapsed (mirrors NLayoutSider). */
  sidebarCollapsed: boolean
}

function makeId(): string {
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export const useUiStore = defineStore('ui', {
  state: (): UiState => ({
    searchPaletteOpen: false,
    shortcutHelpOpen: false,
    uploadDrawerOpen: false,
    globalSearchEnabled: true,
    toasts: [],
    notifications: [],
    notificationMax: 50,
    notificationCenterOpen: false,
    notificationStreamStatus: 'idle',
    userMenuOpen: false,
    sidebarCollapsed: false,
  }),

  getters: {
    /** Unread count, exposed for the bell badge. */
    unreadCount: (state) => state.notifications.filter((n) => !n.read).length,
    /** Sorted desc by createdAt; the dropdown shows this. */
    recentNotifications: (state) =>
      [...state.notifications].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)),
  },

  actions: {
    openSearchPalette(): void {
      this.searchPaletteOpen = true
    },
    closeSearchPalette(): void {
      this.searchPaletteOpen = false
    },
    toggleSearchPalette(): void {
      this.searchPaletteOpen = !this.searchPaletteOpen
    },
    openShortcutHelp(): void {
      this.shortcutHelpOpen = true
    },
    closeShortcutHelp(): void {
      this.shortcutHelpOpen = false
    },
    openUploadDrawer(): void {
      this.uploadDrawerOpen = true
    },
    closeUploadDrawer(): void {
      this.uploadDrawerOpen = false
    },
    setGlobalSearchEnabled(v: boolean): void {
      this.globalSearchEnabled = !!v
    },

    pushToast(entry: Omit<ToastEntry, 'id' | 'createdAt'> & { id?: string; createdAt?: number }): string {
      const id = entry.id ?? makeId()
      const t: ToastEntry = {
        id,
        type: entry.type,
        content: entry.content,
        duration: entry.duration,
        createdAt: entry.createdAt ?? Date.now(),
      }
      this.toasts.push(t)
      if (this.toasts.length > 50) {
        this.toasts = this.toasts.slice(-50)
      }
      return id
    },
    dismissToast(id: string): void {
      this.toasts = this.toasts.filter((t) => t.id !== id)
    },
    clearToasts(): void {
      this.toasts = []
    },

    // ============================================================
    // P20-O: notification center actions
    // ============================================================
    openNotificationCenter(): void {
      this.notificationCenterOpen = true
    },
    closeNotificationCenter(): void {
      this.notificationCenterOpen = false
    },
    toggleNotificationCenter(): void {
      this.notificationCenterOpen = !this.notificationCenterOpen
    },
    setNotificationStreamStatus(s: UiState['notificationStreamStatus']): void {
      this.notificationStreamStatus = s
    },
    pushNotification(entry: NotificationEntry): void {
      // De-dup by id, keep ordering stable, cap at notificationMax.
      const filtered = this.notifications.filter((n) => n.id !== entry.id)
      filtered.unshift(entry)
      this.notifications = filtered.slice(0, this.notificationMax)
    },
    markNotificationRead(id: string): void {
      const target = this.notifications.find((n) => n.id === id)
      if (target) target.read = true
    },
    markAllNotificationsRead(): void {
      this.notifications = this.notifications.map((n) => ({ ...n, read: true }))
    },
    clearNotifications(): void {
      this.notifications = []
    },

    // ============================================================
    // P20-O: user menu actions
    // ============================================================
    openUserMenu(): void {
      this.userMenuOpen = true
    },
    closeUserMenu(): void {
      this.userMenuOpen = false
    },
    toggleUserMenu(): void {
      this.userMenuOpen = !this.userMenuOpen
    },

    // ============================================================
    // P20-O: sidebar collapse
    // ============================================================
    setSidebarCollapsed(v: boolean): void {
      this.sidebarCollapsed = !!v
    },
    toggleSidebar(): void {
      this.sidebarCollapsed = !this.sidebarCollapsed
    },
  },
})
