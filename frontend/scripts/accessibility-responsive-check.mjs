/**
 * Phase 8 accessibility and responsive check. Uses the Chrome installed on this computer.
 *
 * For each main page, in light and dark themes, it runs axe-core (WCAG 2.0/2.1 A and AA rules) on
 * desktop and phone sizes, and checks for horizontal page scrolling at phone, tablet and landscape sizes.
 *
 *   $env:BASE_URL="http://localhost:5174"; node scripts/accessibility-responsive-check.mjs
 *
 * Uses only pages that load without Gemini. Screenshots go to SHOTS_DIR (default ./browser-shots).
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { chromium } from 'playwright-core'

const require = createRequire(import.meta.url)
const AXE_PATH = require.resolve('axe-core/axe.min.js')
const BASE_URL = process.env.BASE_URL || 'http://localhost:5174'
const SHOTS_DIR = process.env.SHOTS_DIR || join(process.cwd(), 'browser-shots')
mkdirSync(SHOTS_DIR, { recursive: true })

const PAGES = [
  { path: '/', name: 'home' },
  { path: '/chat', name: 'chat' },
  { path: '/history', name: 'history' },
  { path: '/study', name: 'study' },
]
const SIZES = {
  desktop: { width: 1280, height: 800 },
  tablet: { width: 768, height: 1024 },
  phone: { width: 390, height: 844 },
  landscape: { width: 844, height: 390 },
}
const THEMES = ['light', 'dark']

const results = []
const record = (name, ok, detail = '') => {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })

async function open(sizeName, theme, path) {
  const context = await browser.newContext({ viewport: SIZES[sizeName] })
  const page = await context.newPage()
  await page.addInitScript((value) => {
    try { window.localStorage.setItem('pdfbot-theme', value) } catch { /* private window */ }
  }, theme)
  page.setDefaultTimeout(30000)
  await page.goto(`${BASE_URL}${path}`)
  await page.waitForLoadState('networkidle').catch(() => {})
  return { context, page }
}

async function overflowOf(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
}

// ------------------------------------------------------------ axe on desktop and phone, both themes
for (const sizeName of ['desktop', 'phone']) {
  for (const theme of THEMES) {
    for (const { path, name } of PAGES) {
      const { context, page } = await open(sizeName, theme, path)
      await page.addScriptTag({ path: AXE_PATH })
      const violations = await page.evaluate(async () => {
        const run = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } })
        return run.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }))
      })
      const serious = violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
      record(`${name} · ${sizeName} · ${theme}: no serious or critical accessibility problems`, serious.length === 0,
        serious.length ? serious.map((v) => `${v.id} x${v.nodes}`).join(', ') : `${violations.length} minor issue(s)`)
      if (violations.length) console.log('      minor/other:', violations.map((v) => `${v.id}(${v.impact}) x${v.nodes}`).join(', '))
      await page.screenshot({ path: join(SHOTS_DIR, `a11y-${name}-${sizeName}-${theme}.png`) })
      await context.close()
    }
  }
}

// ------------------------------------------------------------ no horizontal scrolling at each size
for (const sizeName of ['tablet', 'phone', 'landscape']) {
  for (const { path, name } of PAGES) {
    const { context, page } = await open(sizeName, 'light', path)
    const overflow = await overflowOf(page)
    record(`${name} · ${sizeName}: no horizontal page scroll`, overflow <= 1, `overflow ${overflow}px`)
    await context.close()
  }
}

await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
