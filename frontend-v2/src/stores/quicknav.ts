import { defineStore } from 'pinia'

/**
 * Pinia store: quickNav
 *
 * Drives the collapsible sidebar:
 *  - Sidebar collapsed/expanded state
 *  - Recent items (auto-tracked from router navigation, capped at 20)
 *  - Favorites (user-starred routes, capped at 50)
 *
 * All state is persisted to localStorage under a single namespaced key
 * so a refresh restores everything exactly as it was. Reads are
 * guarded so server-side rendering / unit tests (no localStorage)
 * still work.
 */

export interface NavItem {
  /** Path that vue-router can resolve. */
  path: string
  /** Display title. */
  title: string
  /** Optional icon glyph (single character is enough; we render via span.menu-icon). */
  icon?: string
  /** Subtitle / hint for tooltip and a11y. */
  hint?: string
  /** When set, the item is rendered as a favorite (starred) instead of recent. */
  favorite?: boolean
  /** Last-visited timestamp (ms epoch) — drives recency sort. */
  visitedAt?: number
}

interface QuickNavState {
  collapsed: boolean
  recent: NavItem[]
  favorites: NavItem[]
  /** Recently closed session hint, in case the user wants to re-open it. */
  lastVisitedPath: string
}

const STORAGE_KEY = 'vdp.quicknav.v1'
const MAX_RECENT = 20
const MAX_FAVORITES = 50

interface Persisted {
  collapsed: boolean
  recent: NavItem[]
  favorites: NavItem[]
  lastVisitedPath: string
}

function loadState(): Persisted {
  const empty: Persisted = { collapsed: false, recent: [], favorites: [], lastVisitedPath: '/' }
  if (typeof localStorage === 'undefined') return empty
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return empty
    const parsed = JSON.parse(raw) as Partial<Persisted>
    return {
      collapsed: !!parsed.collapsed,
      recent: Array.isArray(parsed.recent) ? parsed.recent.slice(0, MAX_RECENT) : [],
      favorites: Array.isArray(parsed.favorites) ? parsed.favorites.slice(0, MAX_FAVORITES) : [],
      lastVisitedPath: typeof parsed.lastVisitedPath === 'string' ? parsed.lastVisitedPath : '/',
    }
  } catch {
    return empty
  }
}

function persist(state: Persisted): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* quota / private mode — silently ignore */
  }
}

export const useQuickNavStore = defineStore('quickNav', {
  state: (): QuickNavState => loadState(),

  getters: {
    /** Top-N recent by visitedAt desc. */
    topRecent: (state) => {
      return [...state.recent]
        .sort((a, b) => (b.visitedAt || 0) - (a.visitedAt || 0))
        .slice(0, 10)
    },
    /** Starred favorites, alphabetical for stable order. */
    sortedFavorites: (state) => {
      return [...state.favorites].sort((a, b) => a.title.localeCompare(b.title))
    },
    /** True if a given path is already a favorite. */
    isFavorite: (state) => (path: string): boolean =>
      state.favorites.some((f) => f.path === path),
  },

  actions: {
    /** Toggle sidebar collapsed/expanded. */
    toggleCollapsed(): void {
      this.collapsed = !this.collapsed
      this.save()
    },

    setCollapsed(v: boolean): void {
      this.collapsed = !!v
      this.save()
    },

    /** Record a visit. Deduplicates by path (most-recent first). */
    trackVisit(item: Omit<NavItem, 'favorite' | 'visitedAt'>): void {
      if (!item.path || !item.title) return
      this.lastVisitedPath = item.path
      const idx = this.recent.findIndex((r) => r.path === item.path)
      if (idx >= 0) {
        this.recent.splice(idx, 1)
      }
      this.recent.unshift({ ...item, visitedAt: Date.now() })
      if (this.recent.length > MAX_RECENT) {
        this.recent = this.recent.slice(0, MAX_RECENT)
      }
      this.save()
    },

    addFavorite(item: Omit<NavItem, 'favorite' | 'visitedAt'>): boolean {
      if (!item.path || !item.title) return false
      if (this.favorites.some((f) => f.path === item.path)) return false
      this.favorites.push({ ...item, favorite: true })
      if (this.favorites.length > MAX_FAVORITES) {
        // Remove the oldest favorite (by title sort) — keep user explicit choices
        this.favorites.sort((a, b) => a.title.localeCompare(b.title))
        this.favorites.shift()
      }
      this.save()
      return true
    },

    removeFavorite(path: string): void {
      this.favorites = this.favorites.filter((f) => f.path !== path)
      this.save()
    },

    toggleFavorite(item: Omit<NavItem, 'favorite' | 'visitedAt'>): boolean {
      if (this.isFavorite(item.path)) {
        this.removeFavorite(item.path)
        return false
      }
      return this.addFavorite(item)
    },

    clearRecent(): void {
      this.recent = []
      this.save()
    },

    save(): void {
      persist({
        collapsed: this.collapsed,
        recent: this.recent,
        favorites: this.favorites,
        lastVisitedPath: this.lastVisitedPath,
      })
    },
  },
})