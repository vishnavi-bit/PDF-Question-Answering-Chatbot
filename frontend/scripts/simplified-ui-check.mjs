/**
 * Browser check for the PDF Chatbot and simplified Study Assistant.
 * Uses the Chrome installed on this computer.
 *
 *   $env:BASE_URL="http://localhost:5174"; node scripts/simplified-ui-check.mjs
 *
 * Gemini-dependent answers (notes, quiz, flashcards, exam, explanations, summaries, comparisons) are MOCKED in the
 * browser, and each check says MOCKED. The page layout, navigation, buttons and phone and dark layouts are real.
 * This script does not change your data. Screenshots go to SHOTS_DIR (default ./browser-shots).
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5174'
const SHOTS_DIR = process.env.SHOTS_DIR || join(process.cwd(), 'browser-shots')
mkdirSync(SHOTS_DIR, { recursive: true })

const results = []
const record = (name, ok, detail = '') => {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}
const shot = (page, name) => page.screenshot({ path: join(SHOTS_DIR, `${name}.png`) })

const SOURCE = { source_id: 'S1', document_id: 'd1', filename: 'manual.pdf', page_number: 3 }
const NOTE = {
  id: 1, title: 'Overview notes (MOCKED)', mode: 'overview', length: 'detailed', document_ids: ['d1'],
  body: {
    overview: 'The product has a two year warranty (MOCKED).',
    key_points: [{ text: 'The motor is 750 watts (MOCKED).', sources: [SOURCE] }],
    definitions: [], chapters: [], simple_explanations: [],
  },
}
const QUIZ = {
  id: 2, title: 'Quiz (MOCKED)', document_ids: ['d1'],
  questions: [{ index: 0, question: 'What is covered (MOCKED)?', options: ['Motor', 'Paint', 'Cord', 'Lid'], topic: 'Warranty' }],
}
const QUIZ_RESULT = {
  attempt_id: 1, total: 1, correct: 1, percent: 100,
  items: [{ index: 0, question: QUIZ.questions[0].question, options: QUIZ.questions[0].options, chosen: 0, correct_index: 0,
    is_correct: true, explanation: 'The motor is covered (MOCKED).', topic: 'Warranty', sources: [SOURCE] }],
}
const DECK = {
  id: 3, title: 'Flashcards (MOCKED)', document_ids: ['d1'], studied_indices: [],
  cards: [{ index: 0, question: 'Warranty length (MOCKED)?', answer: 'Two years.', sources: [SOURCE], status: 'new', due_date: null }],
}
const PAPER = {
  id: 4, title: 'Mock exam (MOCKED)', difficulty: 'medium', duration_minutes: 20, document_ids: ['d1'], descriptive: [],
  mcq: [{ index: 0, question: 'Warranty length (MOCKED)?', options: ['1 year', '2 years', '3 years', '4 years'], topic: 'Warranty' }],
}
const EXAM_RESULT = {
  attempt_id: 7, exam_id: 4, exam_title: PAPER.title, correct: 1, total_mcq: 1, percent: 100, descriptive: [], note: '',
  auto_submitted: false, late: false,
  mcq: [{ index: 0, question: PAPER.mcq[0].question, options: PAPER.mcq[0].options, topic: 'Warranty', chosen: 1,
    correct_index: 1, is_correct: true, explanation: 'Two years (MOCKED).', sources: [SOURCE] }],
}
const SUMMARY = {
  document_id: 'd1', filename: 'manual.pdf', sections_found: 1,
  sections: [
    { key: 'purpose', title: 'Purpose', found: true, note: null, points: [{ text: 'It explains the device (MOCKED).', sources: [SOURCE] }] },
    { key: 'method', title: 'Method', found: false, note: 'Not stated in this PDF.', points: [] },
    { key: 'results', title: 'Results', found: false, note: 'Not stated in this PDF.', points: [] },
    { key: 'limitations', title: 'Limitations', found: false, note: 'Not stated in this PDF.', points: [] },
    { key: 'conclusion', title: 'Conclusion', found: false, note: 'Not stated in this PDF.', points: [] },
  ],
}
const COMPARE = {
  documents: [{ document_id: 'd1', filename: 'manual.pdf' }, { document_id: 'd2', filename: 'paper.pdf' }],
  aspects: [{ key: 'data', title: 'Data', rows: [{ document_id: 'd1', filename: 'manual.pdf', text: 'Uses 750 watts (MOCKED).', sources: [SOURCE] }], missing: [] },
    { key: 'purpose', title: 'Purpose', rows: [], missing: [] }],
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const pageErrors = []

async function newPage(width, height, theme = 'light') {
  const context = await browser.newContext({ viewport: { width, height } })
  const page = await context.newPage()
  page.on('pageerror', (error) => pageErrors.push(String(error)))
  await page.addInitScript((value) => {
    try { window.localStorage.setItem('pdfbot-theme', value) } catch { /* private window */ }
  }, theme)
  page.setDefaultTimeout(30000)
  return { context, page }
}

// Each route returns a MOCKED answer, so no real Gemini call is made here.
async function mockStudy(page) {
  const json = (body, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('**/api/study/notes/saved', (r) => (r.request().method() === 'POST' ? r.fulfill(json(NOTE, 201)) : r.fallback()))
  await page.route('**/api/study/notes/1', (r) => (r.request().method() === 'PUT' ? r.fulfill(json(NOTE)) : r.fallback()))
  await page.route('**/api/study/quizzes', (r) => (r.request().method() === 'POST' ? r.fulfill(json(QUIZ, 201)) : r.fallback()))
  await page.route('**/api/study/quizzes/2/attempts', (r) => r.fulfill(json(QUIZ_RESULT, 201)))
  await page.route('**/api/study/flashcards', (r) => (r.request().method() === 'POST' ? r.fulfill(json(DECK, 201)) : r.fallback()))
  await page.route('**/api/study/flashcards/3/review', (r) => r.fulfill(json({ card_index: 0, status: 'known', due_date: '2026-11-17', interval_days: 1, ease_factor: 2.5, repetitions: 1 })))
  await page.route('**/api/study/flashcards/3/review', (r) => r.fulfill(json({ card_index: 0, status: 'known', due_date: '2026-11-17', interval_days: 1, ease_factor: 2.5, repetitions: 1 })))
  await page.route('**/api/study/mock-exams', (r) => (r.request().method() === 'POST' ? r.fulfill(json(PAPER, 201)) : r.fallback()))
  await page.route('**/api/study/mock-exams/4/start', (r) => r.fulfill(json({
    attempt_id: 7, exam_id: 4, deadline: new Date(Date.now() + 120000).toISOString(), duration_seconds: 1200,
  }, 201)))
  await page.route('**/api/study/mock-exam-attempts/7/submit', (r) => r.fulfill(json(EXAM_RESULT)))
  await page.route('**/api/study/explain', (r) => r.fulfill(json({
    topic: 'warranty', found: true, explanation: 'A warranty is a promise to repair (MOCKED).', example: 'A blender is repaired free.',
    sources: [SOURCE],
  })))
  await page.route('**/api/study/exams', (r) => r.fulfill(json({
    id: 5, title: 'Important questions (MOCKED)', document_ids: ['d1'],
    questions: [{ index: 0, kind: 'short', question: 'What is the warranty (MOCKED)?', answer: 'Two years.', sources: [SOURCE] }],
  }, 201)))
}

// ------------------------------------------------------------ Study Assistant, desktop
{
  const { context, page } = await newPage(1280, 900, 'light')
  await mockStudy(page)
  await page.goto(`${BASE_URL}/study`)
  await page.locator('h2', { hasText: 'Study Assistant' }).waitFor()

  const tabNames = ['Study Notes', 'Quiz', 'Flashcards', 'Mock Exam', 'Explain a Topic', 'Important Questions']
  const counts = await Promise.all(tabNames.map((n) => page.getByRole('button', { name: n, exact: true }).count()))
  record('Study Assistant shows the six simple tools', counts.every((c) => c === 1))
  const hidden = await Promise.all(['Progress', 'Revision', 'Mind map'].map((n) => page.getByRole('button', { name: n, exact: true }).count()))
  record('advanced tools (Progress, Revision, Mind map) are not in the menu', hidden.every((c) => c === 0))

  // Study notes
  await page.getByRole('button', { name: 'Generate Notes' }).click()
  record('notes: overview is editable after Generate Notes (MOCKED)', (await page.getByLabel('Overview').inputValue()).includes('warranty'))
  record('notes: Short and Detailed choice is shown', (await page.getByRole('button', { name: 'Short', exact: true }).count()) === 1)
  record('notes: Download PDF button is shown', (await page.getByRole('button', { name: 'Download PDF' }).count()) === 1)
  await shot(page, 'simple-01-notes')

  // Quiz
  await page.getByRole('button', { name: 'Quiz', exact: true }).click()
  const countOptions = await page.getByLabel('Number of quiz questions').locator('option').allTextContents()
  record('quiz: offers 5, 10 or 20 questions', JSON.stringify(countOptions) === JSON.stringify(['5', '10', '20']), countOptions.join(','))
  await page.getByRole('button', { name: 'Generate Quiz' }).click()
  await page.getByLabel(/Motor/).click()
  await page.getByRole('button', { name: 'Submit answers' }).click()
  record('quiz: score is shown after submit (MOCKED)', (await page.getByTestId('score').innerText()).includes('1 of 1'))
  await shot(page, 'simple-02-quiz')

  // Flashcards
  await page.getByRole('button', { name: 'Flashcards', exact: true }).click()
  await page.getByRole('button', { name: 'Create Flashcards' }).click()
  await page.getByTestId('card-face').waitFor()
  await page.getByRole('button', { name: 'Known', exact: true }).click()
  await page.getByTestId('card-status').filter({ hasText: /^Known$/ }).waitFor()
  record('flashcards: Known is saved and shown (MOCKED)', true)
  record('flashcards: Need Practice button is shown', (await page.getByRole('button', { name: 'Need Practice', exact: true }).count()) === 1)

  // Mock exam
  await page.getByRole('button', { name: 'Mock Exam', exact: true }).click()
  record('mock exam: difficulty and time choices are shown',
    (await page.getByLabel('Mock exam difficulty').count()) === 1 && (await page.getByLabel('Exam time').count()) === 1)
  await page.getByRole('button', { name: 'Start Mock Exam' }).click()
  record('mock exam: timer is shown after start (MOCKED)', await page.getByTestId('exam-timer').waitFor().then(() => true).catch(() => false))
  await page.getByLabel(/2 years/).click()
  await page.getByRole('button', { name: 'Submit exam' }).click()
  record('mock exam: final score is shown (MOCKED)', (await page.getByTestId('mock-score').innerText()).includes('1 of 1'))
  await shot(page, 'simple-03-mock-exam')

  // Explain a topic
  await page.getByRole('button', { name: 'Explain a Topic', exact: true }).click()
  await page.getByLabel('Topic to explain').fill('warranty')
  await page.getByRole('button', { name: 'Explain', exact: true }).click()
  record('explain: explanation and example are shown (MOCKED)', await page.getByTestId('explain-result').waitFor().then(() => true).catch(() => false))
  record('explain: no follow-up box or step list', (await page.getByLabel(/follow-up/i).count()) === 0)

  // Important questions
  await page.getByRole('button', { name: 'Important Questions', exact: true }).click()
  record('important questions: Short Answer and Long Answer choice', (await page.getByRole('button', { name: 'Short Answer' }).count()) === 1
    && (await page.getByRole('button', { name: 'Long Answer' }).count()) === 1)
  await page.getByRole('button', { name: 'Generate Questions' }).click()
  await page.getByRole('button', { name: 'Show answer' }).click()
  record('important questions: answer shown on request (MOCKED)', (await page.getByText('Two years.').count()) === 1)
  await shot(page, 'simple-04-important-questions')

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  record('Study desktop: no horizontal page scroll', overflow <= 1, `overflow ${overflow}px`)
  await context.close()
}

// ------------------------------------------------------------ phone portrait and dark theme
for (const path of ['/study', '/chat']) {
  const { context, page } = await newPage(390, 844, 'dark')
  await mockStudy(page)
  await page.goto(`${BASE_URL}${path}`)
  await page.locator('h2').first().waitFor()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  record(`${path} phone dark: no horizontal page scroll`, overflow <= 1, `overflow ${overflow}px`)
  const background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  record(`${path} phone dark: dark background`, background !== 'rgb(255, 255, 255)', background)
  await shot(page, `simple-07-phone-dark${path.replace('/', '-')}`)
  await context.close()
}

record('no uncaught page errors', pageErrors.length === 0, pageErrors.slice(0, 3).join(' | ') || 'none')
await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length} of ${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
