import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../Sidebar'
import { ThemeProvider } from '../../context/ThemeContext'
import { PREF_KEYS, readPreference, writePreference } from '../../hooks/usePreferences'

const mocks = vi.hoisted(() => ({
  api: { listConversations: vi.fn() },
  state: {},
}))
vi.mock('../../services/api', () => ({ api: mocks.api, getErrorMessage: (e, f) => f }))
vi.mock('../../context/ChatContext', () => ({ useAppState: () => mocks.state }))

function renderSidebar() {
  render(
    <MemoryRouter>
      <ThemeProvider>
        <Sidebar open={false} onClose={() => {}} />
      </ThemeProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  mocks.api.listConversations.mockReset()
  mocks.api.listConversations.mockResolvedValue({ conversations: [], total: 0 })
  mocks.state.documents = [{ id: 'a', filename: 'warranty.pdf', processing_status: 'ready' }]
  mocks.state.selectedDocumentIds = []
  mocks.state.conversations = [{ id: 1, title: 'Warranty chat', message_count: 2 }]
  mocks.state.toggleDocument = vi.fn()
  mocks.state.setSelectedDocumentIds = vi.fn()
  mocks.state.uploadFiles = vi.fn()
  mocks.state.uploading = { active: false, done: 0, total: 0, currentName: '' }
  mocks.state.removeDocument = vi.fn()
})

describe('Sidebar collapse', () => {
  it('collapses to icons and remembers the choice', () => {
    renderSidebar()
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toHaveAttribute('data-collapsed', 'false')

    fireEvent.click(screen.getAllByRole('button', { name: 'Collapse sidebar' })[0])

    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toHaveAttribute('data-collapsed', 'true')
    expect(readPreference(PREF_KEYS.sidebarCollapsed, 'false')).toBe('true')
  })

  it('starts collapsed when that was the saved choice', () => {
    writePreference(PREF_KEYS.sidebarCollapsed, 'true')
    renderSidebar()
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toHaveAttribute('data-collapsed', 'true')
  })
})

describe('Sidebar settings', () => {
  it('switches the theme and saves it', () => {
    renderSidebar()
    fireEvent.click(screen.getByRole('button', { name: /settings/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Dark' }))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem('pdfbot-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('chooses the answer length and saves it for the next question', () => {
    renderSidebar()
    fireEvent.click(screen.getByRole('button', { name: /settings/i }))
    expect(screen.getByRole('button', { name: 'Detailed' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Short' }))

    expect(screen.getByRole('button', { name: 'Short' })).toHaveAttribute('aria-pressed', 'true')
    expect(window.localStorage.getItem(PREF_KEYS.answerStyle)).toBe('short')
  })
})

describe('Sidebar conversation search', () => {
  it('shows the normal list when the search is empty', () => {
    renderSidebar()
    expect(screen.getByRole('link', { name: 'Warranty chat' })).toBeInTheDocument()
    expect(mocks.api.listConversations).not.toHaveBeenCalled()
  })

  it('searches titles and messages on the server after a short pause', async () => {
    mocks.api.listConversations.mockResolvedValue({
      conversations: [{ id: 7, title: 'Blade care', message_count: 4 }],
      total: 1,
    })
    renderSidebar()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search conversations' }), { target: { value: 'blade' } })

    expect(await screen.findByRole('link', { name: 'Blade care' })).toBeInTheDocument()
    expect(mocks.api.listConversations).toHaveBeenCalledWith('blade')
  })

  it('says when nothing matches', async () => {
    mocks.api.listConversations.mockResolvedValue({ conversations: [], total: 0 })
    renderSidebar()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search conversations' }), { target: { value: 'zebra' } })
    expect(await screen.findByText('No chats match your search.')).toBeInTheDocument()
  })
})

describe('Sidebar Study link', () => {
  it('is still available from the sidebar', async () => {
    renderSidebar()
    await act(async () => {})
    expect(screen.getByRole('link', { name: /Study Assistant/ })).toHaveAttribute('href', '/study')
  })
})

describe('preferences', () => {
  it('ignores a saved answer length that is not allowed', () => {
    window.localStorage.setItem(PREF_KEYS.answerStyle, 'essay')
    expect(readPreference(PREF_KEYS.answerStyle, 'detailed', ['short', 'detailed'])).toBe('detailed')
  })

  it('still works when browser storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(readPreference('x', 'fallback')).toBe('fallback')
    expect(() => writePreference('x', 'y')).not.toThrow()
    vi.restoreAllMocks()
  })
})
