/**
 * Browser check for the chat interface (Phase 2). Uses the Chrome installed on this computer.
 *
 * Run it while the app is running (for example the backend on port 8100 and Vite on port 5174):
 *   $env:BASE_URL="http://localhost:5174"; node scripts/chat-browser-check.mjs
 *
 * It sends real questions to Gemini (the live checks), and mocks some network failures to
 * check the error screens. Screenshots are written to SHOTS_DIR (default: ./browser-shots).
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5174'
const SHOTS_DIR = process.env.SHOTS_DIR || join(process.cwd(), 'browser-shots')
mkdirSync(SHOTS_DIR, { recursive: true })

const results = []
function record(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}
async function shot(page, name) {
  await page.screenshot({ path: join(SHOTS_DIR, `${name}.png`), fullPage: false })
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })

async function newPage(width, height) {
  const context = await browser.newContext({ viewport: { width, height } })
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE_URL })
  const page = await context.newPage()
  return { context, page }
}

async function waitForAnswerDone(page, timeout = 120000) {
  // the answer is finished when the "Regenerate" action appears on the latest answer
  await page.getByRole('button', { name: 'Regenerate' }).first().waitFor({ timeout })
}

async function askQuestion(page, text) {
  const box = page.getByLabel('Your question')
  await box.fill(text)
  await box.press('Enter')
}

// ------------------------------------------------------------ desktop, light theme
{
  const { context, page } = await newPage(1280, 820)
  page.setDefaultTimeout(30000)
  await page.goto(`${BASE_URL}/chat`)
  await page.evaluate(() => window.localStorage.setItem('pdfbot-theme', 'light'))
  await page.reload()

  const welcome = page.getByRole('heading', { name: 'What would you like to learn from your PDFs?' })
  const welcomeShown = await welcome.waitFor({ timeout: 20000 }).then(() => true).catch(() => false)
  record('welcome screen shows with PDFs ready', welcomeShown)
  await shot(page, '01-welcome-light')

  // document selection: select all, then clear
  await page.getByRole('button', { name: 'Select all' }).click()
  record('select all sets the scope chip', (await page.getByTestId('scope-chip').textContent()).includes('3 selected'))
  await page.getByRole('button', { name: 'Clear', exact: true }).click()
  record('clear returns to all PDFs', (await page.getByTestId('scope-chip').textContent()).includes('all 3'))

  // live question with streaming and citations
  await askQuestion(page, 'How long is the guarantee on the garden hose?')
  const stopButton = page.getByRole('button', { name: 'Stop answering' })
  record('streaming starts (Stop button shown)', await stopButton.waitFor({ timeout: 30000 }).then(() => true).catch(() => false))
  await shot(page, '02-streaming-light')
  await waitForAnswerDone(page)
  const answer = page.getByTestId('assistant-message').last()
  const answerText = (await answer.textContent()) || ''
  record('live answer mentions the five-year guarantee', /five years/i.test(answerText), answerText.slice(0, 80))
  const card = page.getByTestId('citation-card').first()
  record('citation card shows file name and page', (await card.textContent()).includes('garden_hose.pdf') && (await card.textContent()).includes('Page 1'))
  await shot(page, '03-answer-with-citation-light')

  // open the source page beside the chat
  await card.getByRole('button', { name: /Open at page 1/ }).click()
  const viewer = page.locator('iframe[title^="PDF:"]')
  await viewer.waitFor()
  record('open at page shows the PDF viewer at that page', ((await viewer.getAttribute('src')) || '').includes('#page=1'))
  await shot(page, '04-viewer-open-light')
  await page.getByRole('button', { name: 'Close PDF viewer' }).click()

  // feedback and copy
  await page.getByRole('button', { name: 'Helpful answer' }).last().click()
  record('helpful feedback is marked', (await page.getByRole('button', { name: 'Helpful answer' }).last().getAttribute('aria-pressed')) === 'true')
  await page.getByRole('button', { name: 'Copy answer' }).last().click()
  const copyLabel = await page.getByRole('button', { name: /Copied|Copy failed/ }).last().waitFor({ timeout: 5000 }).then(() => page.getByRole('button', { name: /Copied|Copy failed/ }).last().textContent()).catch(() => 'no feedback')
  record('copy shows Copied', copyLabel === 'Copied', copyLabel)

  // follow-up suggestions are shown
  record('follow-up suggestions are shown', await page.getByLabel('Follow-up questions').isVisible())

  // regenerate replaces the answer, and does not add messages
  const countBefore = await page.getByTestId('assistant-message').count()
  await page.getByRole('button', { name: 'Regenerate' }).last().click()
  await page.getByText('Writing a new answer').waitFor({ timeout: 30000 }).catch(() => {})
  await waitForAnswerDone(page)
  const countAfter = await page.getByTestId('assistant-message').count()
  record('regenerate keeps one answer per question', countBefore === countAfter, `${countBefore} -> ${countAfter}`)
  record('regenerated answer still cites the guarantee', /five years/i.test((await page.getByTestId('assistant-message').last().textContent()) || ''))

  // Markdown: a list question
  await askQuestion(page, 'List three key points from the blender manual as bullet points.')
  await waitForAnswerDone(page)
  const listItems = await page.getByTestId('assistant-message').last().locator('li').count()
  record('Markdown bullet points are rendered as a list', listItems >= 2, `${listItems} items`)
  await shot(page, '05-markdown-light')

  // conversation search in the sidebar
  await page.getByRole('searchbox', { name: 'Search conversations' }).fill('garden')
  await page.waitForTimeout(700)
  record('conversation search finds the chat by message text', (await page.getByRole('complementary', { name: 'Sidebar' }).textContent()).toLowerCase().includes('guarantee'))
  await page.getByRole('searchbox', { name: 'Search conversations' }).fill('')

  // dark mode from settings
  await page.getByRole('button', { name: /settings/i }).click()
  await page.getByRole('button', { name: 'Dark', exact: true }).click()
  const theme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
  const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  record('dark mode applies the dark theme', theme === 'dark' && bodyBg !== 'rgb(248, 250, 252)', `${theme}, body ${bodyBg}`)
  await shot(page, '06-dark-desktop')
  // the dark choice must survive a reload, then switch back to light
  await page.reload()
  record('dark theme choice is remembered after reload', (await page.evaluate(() => document.documentElement.getAttribute('data-theme'))) === 'dark')
  await page.getByRole('button', { name: /settings/i }).click()
  await page.getByRole('button', { name: 'Light', exact: true }).click()
  record('switching back to light works', (await page.evaluate(() => document.documentElement.getAttribute('data-theme'))) === 'light')

  await context.close()
}

// ------------------------------------------------------------ error and stop states (mocked network)
{
  const { context, page } = await newPage(1280, 820)
  page.setDefaultTimeout(30000)
  await page.goto(`${BASE_URL}/chat`)

  await page.route('**/api/chat/stream', (route) =>
    route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Gemini is temporarily unavailable. Please try again in about 45 seconds.' }) }),
  )
  await askQuestion(page, 'What does the warranty cover?')
  const alert503 = page.getByRole('alert')
  await alert503.waitFor()
  record('503 shows a clear message', (await alert503.textContent()).includes('temporarily unavailable'))
  record('503 offers Try again', await page.getByRole('button', { name: 'Try again' }).isVisible())
  await shot(page, '07-error-503')
  await page.unroute('**/api/chat/stream')

  await page.route('**/api/chat/stream', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: meta\ndata: {"retrieval":{}}\n\nevent: delta\ndata: {"text":"Partial answer before the connection"}\n\n',
    }),
  )
  await askQuestion(page, 'What does the warranty cover?')
  await page.getByRole('alert').waitFor()
  record('interrupted answer shows an error, not a fake answer', (await page.getByRole('alert').textContent()).includes('interrupted'))
  record('interrupted answer is not kept as a saved answer', (await page.getByTestId('assistant-message').count()) === 0)
  await shot(page, '08-error-interrupted')
  await page.unroute('**/api/chat/stream')

  // Stop while waiting for the first word
  let pendingRoute = null
  await page.route('**/api/chat/stream', (route) => {
    pendingRoute = route // never answered: the request stays open until the student stops
  })
  await askQuestion(page, 'What does the warranty cover?')
  await page.getByText('Searching your PDFs').waitFor()
  await shot(page, '09-waiting-typing-indicator')
  await page.getByRole('button', { name: 'Stop answering' }).click()
  await page.getByText('You stopped this answer').waitFor()
  record('Stop keeps the message clearly marked as not saved', true)
  await shot(page, '10-stopped')
  await page.unroute('**/api/chat/stream')

  await context.close()
}

// ------------------------------------------------------------ responsive layouts
for (const [name, width, height] of [['mobile', 390, 844], ['tablet', 820, 1100]]) {
  const { context, page } = await newPage(width, height)
  page.setDefaultTimeout(30000)
  await page.goto(`${BASE_URL}/chat`)
  await page.getByRole('heading', { name: 'What would you like to learn from your PDFs?' }).waitFor()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  record(`${name}: no horizontal scrolling`, overflow <= 1, `overflow ${overflow}px`)
  await shot(page, `11-${name}-welcome`)
  if (name === 'mobile') {
    const asideBox = await page.getByRole('complementary', { name: 'Sidebar' }).boundingBox()
    record('mobile: sidebar is hidden until opened', asideBox.x < 0 || asideBox.width === 0, `x=${asideBox.x}`)
    await page.getByRole('button', { name: 'Open sidebar' }).click()
    await page.waitForTimeout(300)
    const open = await page.getByRole('complementary', { name: 'Sidebar' }).boundingBox()
    record('mobile: sidebar opens from the menu button', open.x >= 0)
    await shot(page, '12-mobile-sidebar')
  }
  await context.close()
}

// ------------------------------------------------------------ desktop collapse
{
  const { context, page } = await newPage(1280, 820)
  page.setDefaultTimeout(30000)
  await page.goto(`${BASE_URL}/chat`)
  await page.getByRole('button', { name: 'Collapse sidebar' }).first().click()
  record('desktop: sidebar collapses to icons', (await page.getByRole('complementary', { name: 'Sidebar' }).getAttribute('data-collapsed')) === 'true')
  await shot(page, '13-collapsed')
  await context.close()
}

await browser.close()
const failed = results.filter((result) => !result.ok)
console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`)
process.exit(failed.length ? 1 : 0)
