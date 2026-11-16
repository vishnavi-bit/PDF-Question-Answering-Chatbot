import { useRef, useState } from 'react'
import { FileUp, Loader2 } from 'lucide-react'

export const MAX_UPLOAD_MB = 20

/** Returns an error message for a file that cannot be uploaded, or '' when it is fine. */
export function validatePdfFile(file) {
  if (!file.name || !file.name.toLowerCase().endsWith('.pdf')) {
    return `"${file.name}" is not a PDF. Only .pdf files are accepted.`
  }
  if (file.size === 0) {
    return `"${file.name}" is empty.`
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `"${file.name}" is larger than ${MAX_UPLOAD_MB} MB.`
  }
  return ''
}

/**
 * Drag-and-drop area plus a file picker. Only valid PDFs are passed to onFiles.
 */
export default function PDFUploader({ onFiles, disabled = false, progress = null }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [problems, setProblems] = useState([])

  const handleFiles = (fileList) => {
    const files = Array.from(fileList || [])
    if (files.length === 0) return
    const errors = []
    const valid = []
    for (const file of files) {
      const problem = validatePdfFile(file)
      if (problem) errors.push(problem)
      else valid.push(file)
    }
    setProblems(errors)
    if (valid.length > 0) onFiles(valid)
  }

  const onDrop = (event) => {
    event.preventDefault()
    setDragging(false)
    if (!disabled) handleFiles(event.dataTransfer.files)
  }

  const openPicker = () => {
    if (!disabled && inputRef.current) inputRef.current.click()
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onClick={(event) => {
          // ignore clicks that come from the hidden file input itself
          if (event.target !== inputRef.current) openPicker()
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            openPicker()
          }
        }}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        data-testid="pdf-dropzone"
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-6 py-10 text-center transition focus:outline-none focus-visible:ring-4 focus-visible:ring-indigo-200 ${
          dragging ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-white hover:border-indigo-400 hover:bg-indigo-50/40'
        } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
      >
        <div className="brand-gradient flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg shadow-indigo-200">
          {progress ? <Loader2 size={26} className="animate-spin" aria-hidden="true" /> : <FileUp size={26} aria-hidden="true" />}
        </div>
        <div>
          <p className="font-semibold text-slate-900">{progress ? progress : 'Drag and drop PDF files here'}</p>
          <p className="mt-1 text-sm text-slate-500">
            or <span className="font-medium text-indigo-600">browse your computer</span> · PDF only · up to {MAX_UPLOAD_MB} MB each
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="hidden"
          data-testid="pdf-input"
          disabled={disabled}
          onChange={(event) => {
            handleFiles(event.target.files)
            event.target.value = ''
          }}
        />
      </div>

      {problems.length > 0 && (
        <ul role="alert" className="mt-3 space-y-1 text-sm text-rose-600">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
