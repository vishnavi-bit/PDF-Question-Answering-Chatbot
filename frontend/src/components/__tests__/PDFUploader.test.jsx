import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import PDFUploader, { validatePdfFile } from '../PDFUploader'

function makeFile(name, content = 'hello', type = 'application/pdf') {
  return new File([content], name, { type })
}

describe('PDFUploader', () => {
  it('rejects non-PDF files and does not call onFiles', () => {
    const onFiles = vi.fn()
    render(<PDFUploader onFiles={onFiles} />)

    const input = screen.getByTestId('pdf-input')
    fireEvent.change(input, { target: { files: [makeFile('notes.docx', 'x', 'application/msword')] } })

    expect(onFiles).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('"notes.docx" is not a PDF')
  })

  it('passes valid PDF files to onFiles', () => {
    const onFiles = vi.fn()
    render(<PDFUploader onFiles={onFiles} />)

    const pdf = makeFile('report.pdf')
    fireEvent.change(screen.getByTestId('pdf-input'), { target: { files: [pdf] } })

    expect(onFiles).toHaveBeenCalledTimes(1)
    expect(onFiles.mock.calls[0][0]).toEqual([pdf])
  })

  it('keeps valid files and reports invalid ones in the same drop', () => {
    const onFiles = vi.fn()
    render(<PDFUploader onFiles={onFiles} />)

    const good = makeFile('good.pdf')
    const bad = makeFile('bad.txt', 'x', 'text/plain')
    fireEvent.drop(screen.getByTestId('pdf-dropzone'), { dataTransfer: { files: [good, bad] } })

    expect(onFiles.mock.calls[0][0]).toEqual([good])
    expect(screen.getByRole('alert')).toHaveTextContent('"bad.txt" is not a PDF')
  })

  it('does nothing when disabled', () => {
    const onFiles = vi.fn()
    render(<PDFUploader onFiles={onFiles} disabled />)
    fireEvent.drop(screen.getByTestId('pdf-dropzone'), { dataTransfer: { files: [makeFile('a.pdf')] } })
    expect(onFiles).not.toHaveBeenCalled()
  })
})

describe('validatePdfFile', () => {
  it('rejects empty PDFs', () => {
    expect(validatePdfFile(makeFile('empty.pdf', ''))).toMatch(/is empty/)
  })

  it('accepts a normal PDF', () => {
    expect(validatePdfFile(makeFile('ok.PDF'))).toBe('')
  })
})
