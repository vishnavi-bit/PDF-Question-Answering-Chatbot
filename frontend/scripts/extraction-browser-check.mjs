/**
 * Browser check for Phase 7 uploads: tables, pages without text, and OCR detection.
 * Uses the Chrome installed on this computer. It uploads real PDF files through the page.
 *
 * Run it against an isolated test backend (its own database folder), so your own documents are not touched:
 *   $env:BASE_URL="http://localhost:5174"; $env:SAMPLES_DIR="<folder with specs.pdf and blank.pdf>"
 *   node scripts/extraction-browser-check.mjs
 *
 * No Gemini call is made: uploading and indexing do not use Gemini.
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5174'
const SAMPLES_DIR = process.env.SAMPLES_DIR
const SHOTS_DIR = process.env.SHOTS_DIR || join(process.cwd(), 'browser-shots')
if (!SAMPLES_DIR) {
  console.error('Set SAMPLES_DIR to a folder that contains specs.pdf and blank.pdf')
  process.exit(2)
}
mkdirSync(SHOTS_DIR, { recursive: true })

const results = []
function record(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await context.newPage()
const pageErrors = []
page.on('pageerror', (error) => pageErrors.push(String(error)))
page.setDefaultTimeout(60000)

await page.goto(BASE_URL)
const input = page.getByTestId('pdf-input').first()
await input.setInputFiles(join(SAMPLES_DIR, 'specs.pdf'))
await page.goto(BASE_URL)
const tableLine = await page.getByTestId('extraction-details').filter({ hasText: 'table indexed' }).first().waitFor()
  .then(() => true).catch(() => false)
record('PDF with a ruled table shows "1 table indexed" after upload', tableLine)
await page.getByText('specs.pdf', { exact: false }).first().waitFor()
await page.screenshot({ path: join(SHOTS_DIR, 'extraction-01-table.png') })

await input.setInputFiles(join(SAMPLES_DIR, 'blank.pdf'))
const ocrMessage = await page.getByText(/Tesseract is not installed/).first().waitFor()
  .then(() => true).catch(() => false)
record('scanned or blank PDF explains that OCR is disabled because Tesseract is missing', ocrMessage)
await page.screenshot({ path: join(SHOTS_DIR, 'extraction-02-scanned.png') })

const health = await page.request.get(`${BASE_URL}/api/health`).then((r) => r.json())
record('health reports OCR as detected but disabled', health.ocr && health.ocr.ocr_enabled === false,
  `tesseract_installed=${health.ocr && health.ocr.tesseract_installed}`)

const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
record('desktop page has no horizontal scroll', overflow <= 1, `overflow ${overflow}px`)

record('no uncaught page errors', pageErrors.length === 0, pageErrors.slice(0, 3).join(' | ') || 'none')
await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
