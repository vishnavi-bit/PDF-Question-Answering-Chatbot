# Setup guide (step by step, Windows PowerShell)

This guide assumes you are starting from nothing. Every command is run in **PowerShell**, from the project folder unless it says otherwise.

Project folder used in the examples:

```powershell
cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot"
```

## 0. What you need installed

| Tool | Version used while building | Check with |
| --- | --- | --- |
| Python | 3.11 | `py -3.11 --version` |
| Node.js | 22 (npm 10 included) | `node --version` |
| Docker Desktop (optional, for Docker only) | 29 | `docker --version` |
| A Google AI Studio Gemini API key (needed to get answers) | — | see step 3 |

Install Python 3.11 from python.org and Node.js LTS from nodejs.org if they are missing.

## 1. Allow PowerShell to run local scripts (one time only)

PowerShell blocks the virtual-environment activation script by default. Run this once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## 2. Set up the backend

```powershell
cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot\backend"

# Create a private Python environment in backend\.venv (it is not uploaded anywhere)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install the packages (this downloads PyTorch, so it can take a few minutes)
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create your settings file from the template:

```powershell
Copy-Item .env.example .env
```

Create the database tables (the server also does this automatically on start):

```powershell
python -m app.database.init_db
```

Start the backend:

```powershell
uvicorn app.main:app --reload --port 8000
```

Keep this window open. Check it works by opening **http://localhost:8000/api/health** in your browser, or open the API documentation at **http://localhost:8000/docs**.

## 3. Get a free Gemini API key and add it

1. Open **https://aistudio.google.com/apikey** and sign in with your Google account.
2. Click **Create API key**, then copy the key. Keep it private.
3. Open the settings file:

   ```powershell
   cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot\backend"
   notepad .env
   ```

4. After `GEMINI_API_KEY=`, paste your key on the same line. No quotes and no spaces.
5. Leave `GEMINI_MODEL=gemini-3.6-flash` as it is, unless you have checked another model in AI Studio.
6. Save the file and **restart the backend** (press `Ctrl+C` in its window, then run `uvicorn app.main:app --reload --port 8000` again).

**Free-tier notes:** free usage depends on Google's current model availability, quotas and terms. Limits are shown per project on the AI Studio rate-limit page. Google may use free-tier requests to improve its products. If the free quota runs out, the app shows a rate-limit message until it resets.

Without a key, the app still works for uploading and searching. It shows "Gemini key not set" in the top bar, and questions return a clear message.

Never share your `.env` file, and never paste the key into frontend code.

## 4. Set up and start the frontend

Open a **second** PowerShell window:

```powershell
cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot\frontend"
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. The frontend forwards every `/api` request to the backend on port 8000, so both windows must be running.

## 5. Try it

1. Click **Upload PDF** (or drag a PDF onto the Home page).
2. Wait for the status to show **Ready**. Scanned PDFs show "OCR needed" (see the README).
3. Click **Start chatting**, type a question and press **Enter**.
4. Click a source chip such as `[S1] manual.pdf · page 3` to open the PDF at that page.

## 6. Run the automated tests

Backend (no API key or internet needed; Gemini and the embedding model are replaced by fakes):

```powershell
cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot\backend"
.\.venv\Scripts\Activate.ps1
python -m pytest -v
```

To also run the test that uses the real embedding model (downloads it the first time):

```powershell
$env:RUN_REAL_MODEL = "1"
python -m pytest tests\test_embedding.py -v
Remove-Item Env:RUN_REAL_MODEL
```

Frontend:

```powershell
cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot\frontend"
npm test
```

Production build of the frontend:

```powershell
npm run build
```

## 7. Run with Docker (optional)

Make sure Docker Desktop is running, then:

```powershell
cd "C:\Users\SIDDVATAM VISHNAVI\OneDrive\Desktop\pdf chatbot"
docker compose up --build
```

Open **http://localhost:8000**. Your uploads, vectors and database are stored in the `storage` folder on your computer. To stop: press `Ctrl+C`, then run `docker compose down`.

The first build downloads PyTorch (CPU build) and the embedding model, so it can take 10 minutes or more.

## Where your data is stored

| What | Location (local run) |
| --- | --- |
| Uploaded PDFs | `storage\uploads\` (random file names) |
| Vector search index | `storage\chroma_db\` |
| Documents, chats, messages | `backend\data\app.db` (SQLite) |
| Embedding model | Hugging Face cache in your user folder (`%USERPROFILE%\.cache\huggingface`) |

Change the locations in `backend\.env` (`DATABASE_URL`, `UPLOAD_DIRECTORY`, `CHROMA_PERSIST_DIRECTORY`).

## Common problems

| Problem | Fix |
| --- | --- |
| `cannot be loaded because running scripts is disabled` | Run step 1 (`Set-ExecutionPolicy`). |
| `py : The term 'py' is not recognized` | Install Python 3.11 and tick "Add to PATH", or use the full path to `python.exe`. |
| Top bar says **Backend offline** | The backend window is closed or not on port 8000. Start it again (step 2). |
| Top bar says **Gemini key not set** | Add `GEMINI_API_KEY` to `backend\.env` and restart the backend (step 3). |
| Question says the key was rejected | Check the key in `backend\.env` (no spaces, no quotes) and that it is active in Google AI Studio (https://aistudio.google.com/apikey). |
| "rate limit" message | Wait a minute and try again. |
| Gemini temporarily unavailable (503) or did not finish in time (504) | The backend already retried up to 3 times. Wait a minute and ask again, or ask a shorter, more specific question. |
| Upload says **OCR needed** | The PDF is a scan with no selectable text. See the README for options. |
| Upload says **password protected** | Remove the password (for example by printing it to a new PDF) and upload again. |
| First question after start is slow | The embedding model loads the first time. Later questions are faster. |
| Port 8000 or 5173 already in use | Close the other program, or start on another port (`--port 8001`, and set `VITE_API_PROXY=http://localhost:8001` before `npm run dev`). |

## 8. VS Code tasks (optional)

If you use VS Code, the project has ready-made tasks in `.vscode/tasks.json`. Press **Ctrl+Shift+P**, choose **Tasks: Run Task**, then pick:

- **Run Backend**: starts the API on http://localhost:8000 (API docs at http://localhost:8000/docs).
- **Run Frontend**: starts the app on http://localhost:5173.
- **Run Full Project**: starts both, each in its own terminal. **Ctrl+Shift+B** runs this task.
- **Stop Servers**: stops the backend and frontend started by these tasks. Other programs on those ports are not stopped.

If port 8000 or 5173 is already in use, the task says so and starts nothing. Stop the old server with **Stop Servers** first.
