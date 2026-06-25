import { test, expect } from '@playwright/test'

test('smoke: root page loads', async ({ page }) => {
  await page.goto('http://127.0.0.1:5183/', { waitUntil: 'domcontentloaded', timeout: 30_000 })
  const title = await page.title()
  expect(title.length).toBeGreaterThan(0)
})
