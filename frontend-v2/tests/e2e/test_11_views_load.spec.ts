import { test, expect, type Page } from '@playwright/test'

/**
 * test_11_views_load.spec.ts
 * P0-7 verification — 11 stub views from P0-7-W1 must render without
 * crashing. We stub the backend so the SPA doesn't fail on missing APIs;
 * what we verify is that the Vue/Naive UI render path completes and
 * the ErrorBoundary does NOT trip.
 *
 * The 11 routes map to: Annotation, Billing, Dataset, Engines, Monitoring,
 * Review, Scoring, Settings, Tasks, Users, Workflows.
 */

const VIEWS: { name: string; path: string; containsAny: string[] }[] = [
  { name: 'Annotation', path: '/annotation', containsAny: ['标注', 'annotation', '数据', '任务'] },
  { name: 'Billing',    path: '/billing',    containsAny: ['计费', '订单', '套餐', 'billing', 'plan'] },
  { name: 'Dataset',    path: '/dataset',    containsAny: ['数据', 'dataset', '记录'] },
  { name: 'Engines',    path: '/engines',    containsAny: ['引擎', 'engine', '算子', 'operator'] },
  { name: 'Monitoring', path: '/monitoring', containsAny: ['监控', '监控指标', 'monitoring', '指标'] },
  { name: 'Review',     path: '/review',     containsAny: ['审核', 'review', '队列'] },
  { name: 'Scoring',    path: '/scoring',    containsAny: ['评分', 'scoring', '打分'] },
  { name: 'Settings',   path: '/settings',   containsAny: ['设置', 'settings', '配置'] },
  { name: 'Tasks',      path: '/tasks',      containsAny: ['任务', 'task', '队列'] },
  { name: 'Users',      path: '/users',      containsAny: ['用户', 'user', '角色', 'role'] },
  { name: 'Workflows',  path: '/workflows',  containsAny: ['工作流', 'workflow', '模板'] }
]

/**
 * Install a fake auth session into localStorage and stub the most common
 * /api/v1/* endpoints to return empty/paginated data. The 11 views call
 * many APIs; we catch-all 200 to keep them rendering.
 */
async function preparePage(page: Page): Promise<void> {
  // Fake auth — must be set before the SPA loads so the router guard passes.
  await page.addInitScript(() => {
    localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token')
    localStorage.setItem(
      'imdf.auth.user',
      JSON.stringify({ id: 1, name: 'e2e', role: 'admin' })
    )
  })

  // Stub all API calls so backend is not required.
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (url.includes('/login') || url.includes('/auth')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'playwright-fake-token',
          refresh_token: 'fake',
          user: { id: 1, name: 'e2e', role: 'admin' }
        })
      })
    }
    // Default: empty paginated response
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
        total: 0,
        page: 1,
        page_size: 20
      })
    })
  })
}

for (const view of VIEWS) {
  test(`P0-7: ${view.name} (${view.path}) renders without crash`, async ({ page }) => {
    await preparePage(page)
    await page.goto(view.path, { waitUntil: 'domcontentloaded' })

    // Wait for the layout shell to appear (header / sidebar).
    await expect(page.locator('.n-layout, .app-shell, header').first()).toBeVisible({ timeout: 15_000 })

    // ErrorBoundary must NOT trip on a healthy view.
    const boundary = page.locator('.error-boundary')
    await expect(boundary).toHaveCount(0)

    // Page should contain at least one recognizable text fragment.
    const bodyText = (await page.locator('body').innerText()).toLowerCase()
    const matched = view.containsAny.some((kw) => bodyText.includes(kw.toLowerCase()))
    expect(matched, `expected body to contain one of ${view.containsAny.join('|')}`).toBe(true)
  })
}
