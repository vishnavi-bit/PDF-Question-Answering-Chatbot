/**
 * Small preferences stored in this browser (answer length, sidebar state).
 * Storage can be blocked, so every read and write is guarded and falls back to defaults.
 */

export const PREF_KEYS = {
  answerStyle: 'pdfbot-answer-style',
  sidebarCollapsed: 'pdfbot-sidebar-collapsed',
}

export function readPreference(key, fallback, allowed = null) {
  try {
    const value = window.localStorage.getItem(key)
    if (value === null) return fallback
    if (allowed && !allowed.includes(value)) return fallback
    return value
  } catch {
    return fallback
  }
}

export function writePreference(key, value) {
  try {
    window.localStorage.setItem(key, String(value))
  } catch {
    // blocked storage: the choice lasts for this visit only
  }
}

/** Current answer length: "short" or "detailed" (default). */
export function currentAnswerStyle() {
  return readPreference(PREF_KEYS.answerStyle, 'detailed', ['short', 'detailed'])
}
