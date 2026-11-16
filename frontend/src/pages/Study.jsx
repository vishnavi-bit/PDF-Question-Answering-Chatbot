import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, FileQuestion, GraduationCap, Layers, Lightbulb, Timer } from 'lucide-react'
import { useAppState } from '../context/ChatContext'
import NotesPanel from '../components/study/NotesPanel'
import QuizPanel from '../components/study/QuizPanel'
import FlashcardPanel from '../components/study/FlashcardPanel'
import MockExamPanel from '../components/study/MockExamPanel'
import ExplainPanel from '../components/study/ExplainPanel'
import ExamPanel from '../components/study/ExamPanel'
import { scopeLabel } from '../components/study/StudyMessage'

/**
 * The tabs shown on the Study page. The simplified version keeps six tools.
 * Progress, Revision and Mind map still exist in the code and the API; add them back here to show them.
 */
const TABS = [
  { id: 'notes', label: 'Study Notes', icon: BookOpen },
  { id: 'quiz', label: 'Quiz', icon: GraduationCap },
  { id: 'flashcards', label: 'Flashcards', icon: Layers },
  { id: 'mock', label: 'Mock Exam', icon: Timer },
  { id: 'explain', label: 'Explain a Topic', icon: Lightbulb },
  { id: 'exam', label: 'Important Questions', icon: FileQuestion },
]

/** Study Assistant: notes, quiz, flashcards, mock exam, explanations and important questions. */
export default function Study() {
  const { documents, selectedDocumentIds } = useAppState()
  const [tab, setTab] = useState('notes')
  const readyCount = documents.filter((doc) => doc.processing_status === 'ready').length

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">Study Assistant</h2>
          <p className="mt-1 text-sm text-slate-500">
            Using: <span className="font-medium text-slate-700" data-testid="study-scope">{scopeLabel(selectedDocumentIds, documents)}</span>
            {' '}· to change PDFs, use the list on the left.
          </p>
        </div>
        {readyCount === 0 && (
          <Link to="/" className="rounded-xl bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700">
            Upload a PDF first
          </Link>
        )}
      </div>

      <nav aria-label="Study tools" className="-mx-1 flex gap-2 overflow-x-auto pb-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-current={tab === id ? 'page' : undefined}
            className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition ${
              tab === id ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200' : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:text-indigo-700'
            }`}
          >
            <Icon size={16} aria-hidden="true" /> {label}
          </button>
        ))}
      </nav>

      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        {tab === 'notes' && <NotesPanel documentIds={selectedDocumentIds} />}
        {tab === 'quiz' && <QuizPanel documentIds={selectedDocumentIds} />}
        {tab === 'flashcards' && <FlashcardPanel documentIds={selectedDocumentIds} />}
        {tab === 'mock' && <MockExamPanel documentIds={selectedDocumentIds} />}
        {tab === 'explain' && <ExplainPanel documentIds={selectedDocumentIds} />}
        {tab === 'exam' && <ExamPanel documentIds={selectedDocumentIds} />}
      </div>
    </div>
  )
}
