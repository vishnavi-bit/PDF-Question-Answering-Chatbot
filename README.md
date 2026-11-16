


# PDF Question Answering Chatbot

An AI-powered application that allows users to upload PDF documents, ask questions, and get answers with source citations.

## Features

- Upload and read PDF documents.
- Ask questions about uploaded PDFs.
- Get answers using AI.
- Search relevant information using semantic search.
- Generate short and detailed study notes.
- Generate quizzes and check scores.
- Create flashcards.
- Explain topics in simple language.

## Technologies Used

- Frontend: React, Vite, Tailwind CSS
- Backend: Python, FastAPI
- AI: Google Gemini
- RAG: LangChain, Sentence Transformers
- Vector Database: ChromaDB
- Database: SQLite
- PDF Processing: PyMuPDF

## Workflow

1. Upload a PDF.
2. Extract and split PDF text into chunks.
3. Generate embeddings and store them in ChromaDB.
4. Retrieve relevant content based on user questions.
5. Generate AI answers with source citations.

## Installation and Setup

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd YOUR_PROJECT_FOLDER
```

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure API Key

Create a `.env` file inside the backend folder:

```env
GEMINI_API_KEY=your_gemini_api_key
```

### 4. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Start Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

### 6. Open Application

http://localhost:5173




