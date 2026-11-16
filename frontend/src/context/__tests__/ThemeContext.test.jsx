import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { THEME_STORAGE_KEY, ThemeProvider, applyTheme, readSavedTheme, useTheme } from '../ThemeContext'
import Navbar from '../../components/Navbar'

const mocks = vi.hoisted(() => ({
  api: { health: vi.fn().mockResolvedValue({ gemini_api_key_configured: true }) },
}))
vi.mock('../../services/api', () => ({ api: mocks.api, getErrorMessage: (e, f) => f }))

function mockSystemDark(dark) {
  window.matchMedia = vi.fn().mockImplementation(() => ({ matches: dark, addEventListener() {}, removeEventListener() {} }))
}

function ThemeProbe() {
  const { theme, toggleTheme } = useTheme()
  return <button type="button" onClick={toggleTheme}>theme:{theme}</button>
}

describe('ThemeContext', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    mockSystemDark(false)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete window.matchMedia
  })

  it('uses the operating system setting when nothing is saved', () => {
    mockSystemDark(true)
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('defaults to light when there is no preference and no system setting', () => {
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('a saved choice wins over the operating system setting', () => {
    mockSystemDark(true)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light')
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('ignores an invalid saved value', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'purple')
    expect(readSavedTheme()).toBeNull()
  })

  it('toggling switches the theme and remembers the choice', () => {
    render(<ThemeProvider><ThemeProbe /></ThemeProvider>)

    fireEvent.click(screen.getByRole('button', { name: 'theme:light' }))

    expect(screen.getByRole('button', { name: 'theme:dark' })).toBeInTheDocument()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  })

  it('still works when browser storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })

    render(<ThemeProvider><ThemeProbe /></ThemeProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'theme:light' }))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('applyTheme sets the attribute used by the CSS tokens', () => {
    applyTheme('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    applyTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})

describe('Navbar theme toggle', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    mockSystemDark(false)
  })

  it('switches between dark and light mode and keeps the choice', async () => {
    render(
      <MemoryRouter>
        <ThemeProvider>
          <Navbar title="Home" onMenuClick={() => {}} />
        </ThemeProvider>
      </MemoryRouter>,
    )
    await act(async () => {})

    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')

    fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
