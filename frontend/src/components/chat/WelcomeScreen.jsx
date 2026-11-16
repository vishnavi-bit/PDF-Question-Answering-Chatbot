import { FileText, MessageSquare } from 'lucide-react'
import PDFUploader from '../PDFUploader'

/** Shown before the first message: example questions from the student's PDFs, or an upload box. */
export function exampleQuestions(documents) {
  const ready = documents.filter((doc) => doc.processing_status === 'ready')
  if (ready.length === 0) return []
  const first = ready[0].filename
  const examples = [
    `Summarize ${first}`,
    'What are the main topics covered in my PDFs?',
    'Which important terms or definitions are explained?',
  ]
  if (ready.length > 1) examples.push('What do my PDFs say about the same topic?')
  return examples.slice(0, 4)
}

export default function WelcomeScreen({ documents, onExample, onUpload, uploading = false, disabled = false }) {
  const ready = documents.filter((doc) => doc.processing_status === 'ready')
  const examples = exampleQuestions(documents)

  return (
    <section className="animate-fade-up flex flex-col items-center px-2 pb-4 pt-6 text-center" aria-labelledby="welcome-heading">
      <span className="brand-gradient mb-4 flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg shadow-indigo-200">
        <MessageSquare size={24} aria-hidden="true" />
      </span>
      <h2 id="welcome-heading" className="text-2xl font-bold tracking-tight text-slate-900">
        {ready.length > 0 ? 'What would you like to learn from your PDFs?' : 'Start by adding a PDF'}
      </h2>
      <p className="mt-2 max-w-lg text-sm text-slate-500">
        {ready.length > 0
          ? 'Ask in plain English. Every answer names the PDF and page it came from, and you can open that page beside the chat.'
          : 'Upload one or more PDFs. Then ask a question and get an answer with page citations.'}
      </p>

      {ready.length > 0 ? (
        <div className="mt-6 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
          {examples.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onExample(question)}
              disabled={disabled}
              className="card flex items-start gap-3 px-4 py-3 text-left text-sm text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50"
            >
              <FileText size={16} className="mt-0.5 shrink-0 text-indigo-500" aria-hidden="true" />
              <span>{question}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="mt-6 w-full max-w-xl text-left">
          <PDFUploader onFiles={onUpload} disabled={uploading} progress={uploading ? 'Processing your PDF…' : null} />
        </div>
      )}
    </section>
  )
}
