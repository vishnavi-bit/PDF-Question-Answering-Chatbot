import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export const THEME_STORAGE_KEY = 'pdfbot-theme'
export const THEMES = ['light', 'dark']

/** Saved choice from this browser, or null. Storage can be blocked, so every read is guarded. */
export function readSavedTheme() {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY)
    return THEMES.includes(value) ? value : null
  } catch {
    return null
  }
}

function saveTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Private mode or blocked storage: the theme still works for this visit.
  }
}

function systemTheme() {
  try {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/** Applies a theme to the page (<html data-theme="...">). */
export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme)
}

const ThemeContext = createContext(null)

/**
 * Light and dark themes. The user's choice is remembered in this browser.
 * With no saved choice, the operating system's setting is used.
 */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => readSavedTheme() || systemTheme())

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark'
      saveTheme(next)
      return next
    })
  }, [])

  const value = useMemo(() => ({ theme, setTheme: (next) => { saveTheme(next); setTheme(next) }, toggleTheme }), [theme, toggleTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used inside ThemeProvider')
  return context
}
