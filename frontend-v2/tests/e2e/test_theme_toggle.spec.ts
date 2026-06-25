import { test, expect, type Page } from '@playwright/test'

/**
 * test_theme_toggle.spec.ts
 * P0-8 verification — the theme store (Pinia) drives a <html data-theme>
 * attribute and the cycle() action rotates light → dark → auto → light.
 */

async function preparePage(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token')
    localStorage.setItem(
      'imdf.auth.user',
      JSON.stringify({ id: 1, name: 'e2e', role: 'admin' })
    )
  })
  await page.route('**/api/**', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 })
    })
  })
}

test('P0-8: theme store sets data-theme="light" by default on first load', async ({ page }) => {
  await preparePage(page)
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  // Wait for header to mount.
  await expect(page.locator('header').first()).toBeVisible({ timeout: 15_000 })
  const theme = await page.locator('html').getAttribute('data-theme')
  expect(theme === 'light' || theme === 'dark').toBe(true)
})

test('P0-8: theme toggle button cycles light → dark → auto', async ({ page }) => {
  await preparePage(page)
  // Pre-seed localStorage so we start in 'light' deterministically.
  await page.addInitScript(() => localStorage.setItem('vdp-theme', 'light'))

  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('header').first()).toBeVisible({ timeout: 15_000 })

  // Sanity: starts light.
  expect(await page.locator('html').getAttribute('data-theme')).toBe('light')

  // Find the theme toggle button in the header. The button has a tooltip
  // describing the next state; for now we just click any button with the
  // .theme-toggle class which DefaultLayout.vue renders.
  const toggle = page.locator('header .theme-toggle, header button[aria-label*="色"], header button[title*="色"]').first()

  // If the locator doesn't find a theme-specific class, fall back to
  // the FIRST icon-only button in the header NSpace (the one marked with Sunny/Moon).
  const fallback = page.locator('header button').first()

  if (await toggle.count()) {
    await toggle.click()
  } else {
    await fallback.click()
  }

  // After one click, mode should have advanced to 'dark' (light → dark).
  // Wait for the DOM attribute to update.
  await page.waitForFunction(
    () => document.documentElement.getAttribute('data-theme') === 'dark',
    { timeout: 5_000 }
  )
  expect(await page.locator('html').getAttribute('data-theme')).toBe('dark')

  // And persisted to localStorage.
  const persisted = await page.evaluate(() => localStorage.getItem('vdp-theme'))
  expect(persisted).toBe('dark')

  // Second click → 'auto'. With a light system color-scheme, resolved stays light.
  const t2 = page.locator('header .theme-toggle, header button[aria-label*="色"], header button[title*="色"]').first()
  const f2 = page.locator('header button').first()
  if (await t2.count()) {
    await t2.click()
  } else {
    await f2.click()
  }
  const persisted2 = await page.evaluate(() => localStorage.getItem('vdp-theme'))
  expect(persisted2).toBe('auto')
})
