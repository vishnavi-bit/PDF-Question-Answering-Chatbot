import axios from 'axios'

// All requests go to /api. In development Vite forwards them to the backend;
// in Docker the FastAPI server serves both the app and the API.
const client = axios.create({
  baseURL: '/api',
  timeout: 180000,
})

/**
 * Turn any Axios/network error into a short message for the user.
 * Internal details never reach the screen.
 */
export function getErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (error && error.response) {
    const detail = error.response.data && error.response.data.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail[0] && detail[0].msg) return String(detail[0].msg)
    if (error.response.status === 413) return 'The file is too large to upload.'
    if (error.response.status === 404) return 'The requested item was not found.'
    if (error.response.status === 429) return 'Too many requests. Please wait a moment and try again.'
    return fallback
  }
  if (error && error.code === 'ECONNABORTED') return 'The request took too long. Please try again.'
  if (error && error.request) {
    return 'Cannot reach the server. Make sure the backend is running on http://localhost:8000.'
  }
  return fallback
}

export const api = {
  health: () => client.get('/health').then((r) => r.data),

  uploadDocument: (file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return client
      .post('/documents/upload', form, {
        onUploadProgress: (event) => {
          if (onProgress && event.total) onProgress(Math.round((event.loaded * 100) / event.total))
        },
      })
      .then((r) => r.data)
  },

  listDocuments: () => client.get('/documents').then((r) => r.data),
  getDocument: (documentId) => client.get(`/documents/${documentId}`).then((r) => r.data),
  deleteDocument: (documentId) => client.delete(`/documents/${documentId}`).then(() => undefined),
  documentFileUrl: (documentId) => `/api/documents/${documentId}/file`,
  summarizeDocument: (documentId, mode) =>
    client.post(`/documents/${documentId}/summary`, { mode }).then((r) => r.data),

  sendChat: (payload) => client.post('/chat', payload).then((r) => r.data),
  listConversations: (query = '') =>
    client.get('/conversations', { params: query ? { q: query } : undefined }).then((r) => r.data),
  getConversation: (conversationId) => client.get(`/conversations/${conversationId}`).then((r) => r.data),
  renameConversation: (conversationId, title) =>
    client.patch(`/conversations/${conversationId}`, { title }).then((r) => r.data),
  deleteConversation: (conversationId) =>
    client.delete(`/conversations/${conversationId}`).then(() => undefined),
  setMessageFeedback: (messageId, feedback) =>
    client.put(`/messages/${messageId}/feedback`, { feedback }).then((r) => r.data),

  // Study Assistant
  studyNotes: (body) => client.post('/study/notes', body).then((r) => r.data),
  createQuiz: (body) => client.post('/study/quizzes', body).then((r) => r.data),
  getQuiz: (quizId) => client.get(`/study/quizzes/${quizId}`).then((r) => r.data),
  submitQuiz: (quizId, answers) =>
    client.post(`/study/quizzes/${quizId}/attempts`, { answers }).then((r) => r.data),
  createFlashcards: (body) => client.post('/study/flashcards', body).then((r) => r.data),
  getFlashcards: (deckId) => client.get(`/study/flashcards/${deckId}`).then((r) => r.data),
  setFlashcardStudied: (deckId, cardIndex, studied) =>
    client.put(`/study/flashcards/${deckId}/progress`, { card_index: cardIndex, studied }).then((r) => r.data),
  createExam: (body) => client.post('/study/exams', body).then((r) => r.data),
  explainTopic: (body) => client.post('/study/explain', body).then((r) => r.data),
  studyProgress: () => client.get('/study/progress').then((r) => r.data),

  // Phase 4: saved notes, review, mock exams, saved questions, learning path
  saveNotes: (body) => client.post('/study/notes/saved', body).then((r) => r.data),
  listSavedNotes: () => client.get('/study/notes').then((r) => r.data),
  getSavedNotes: (noteId) => client.get(`/study/notes/${noteId}`).then((r) => r.data),
  updateSavedNotes: (noteId, body) => client.put(`/study/notes/${noteId}`, body).then((r) => r.data),
  deleteSavedNotes: (noteId) => client.delete(`/study/notes/${noteId}`).then(() => undefined),
  setFlashcardReview: (deckId, cardIndex, status) =>
    client.put(`/study/flashcards/${deckId}/review`, { card_index: cardIndex, status }).then((r) => r.data),
  revisionToday: () => client.get('/study/revision/today').then((r) => r.data),
  revisionUpcoming: (days = 7) => client.get('/study/revision/upcoming', { params: { days } }).then((r) => r.data),
  createRevisionPlan: (deckId) => client.post('/study/revision-plans', { deck_id: deckId }).then((r) => r.data),
  completeRevisionTask: (planId, completed) =>
    client.post(`/study/revision-plans/${planId}/complete`, { completed }).then((r) => r.data),
  learningPath: () => client.get('/study/learning-path').then((r) => r.data),
  saveQuestion: (body) => client.post('/study/saved-questions', body).then((r) => r.data),
  listSavedQuestions: () => client.get('/study/saved-questions').then((r) => r.data),
  deleteSavedQuestion: (questionId) => client.delete(`/study/saved-questions/${questionId}`).then(() => undefined),
  createMockExam: (body) => client.post('/study/mock-exams', body).then((r) => r.data),
  getMockExam: (examId) => client.get(`/study/mock-exams/${examId}`).then((r) => r.data),
  deleteMockExam: (examId) => client.delete(`/study/mock-exams/${examId}`).then(() => undefined),
  startMockExam: (examId) => client.post(`/study/mock-exams/${examId}/start`).then((r) => r.data),
  submitMockExam: (attemptId, body) =>
    client.post(`/study/mock-exam-attempts/${attemptId}/submit`, body).then((r) => r.data),
  getMockAttempt: (attemptId) => client.get(`/study/mock-exam-attempts/${attemptId}`).then((r) => r.data),
  listMockAttempts: () => client.get('/study/mock-exam-attempts').then((r) => r.data),

  // Phase 5: mind maps and PDF exports
  createMindMap: (body) => client.post('/study/mind-maps', body).then((r) => r.data),
  listMindMaps: () => client.get('/study/mind-maps').then((r) => r.data),
  getMindMap: (mapId) => client.get(`/study/mind-maps/${mapId}`).then((r) => r.data),
  renameMindMap: (mapId, title) => client.put(`/study/mind-maps/${mapId}`, { title }).then((r) => r.data),
  deleteMindMap: (mapId) => client.delete(`/study/mind-maps/${mapId}`).then(() => undefined),
  exportPdf: (kind, itemId) => {
    const path = itemId === undefined ? `/study/export/${kind}.pdf` : `/study/export/${kind}/${itemId}.pdf`
    return client.get(path, { responseType: 'blob' }).then((r) => r.data)
  },
}
