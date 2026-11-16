import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DocumentCard from '../DocumentCard'

vi.mock('../../services/api', () => ({
  api: { documentFileUrl: (id) => `/api/documents/${id}/file` },
  getErrorMessage: (error, fallback) => fallback,
}))

const READY = {
  id: 'd1',
  filename: 'specs.pdf',
  file_size: 2048,
  page_count: 3,
  total_chunks: 4,
  processing_status: 'ready',
  error_message: null,
  table_count: 0,
  pages_without_text: 0,
}

describe('DocumentCard extraction details (Phase 7)', () => {
  it('shows the number of indexed tables', () => {
    render(<DocumentCard document={{ ...READY, table_count: 2 }} />)
    expect(screen.getByTestId('extraction-details')).toHaveTextContent('2 tables indexed')
  })

  it('shows pages without text, which may be scanned images', () => {
    render(<DocumentCard document={{ ...READY, pages_without_text: 1 }} />)
    expect(screen.getByTestId('extraction-details')).toHaveTextContent('1 page with no text (may be scanned images)')
  })

  it('shows nothing extra for a plain text PDF', () => {
    render(<DocumentCard document={READY} />)
    expect(screen.queryByTestId('extraction-details')).toBeNull()
  })
})
