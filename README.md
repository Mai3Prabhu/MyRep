# MyRep

**Your AI professional representative.** MyRep lets you set up a professional profile, upload documents like your resume, and share a public AI rep that answers questions about you by chat or voice, using only what you've verified.

> The AI isn't the source of truth. Your profile is, and the AI only reads from it.

## Features

- **Profile builder**: structured profile (experience, projects, skills) with a public visibility toggle
- **Document knowledge base**: upload PDFs, which are extracted, chunked, embedded and indexed per profile
- **Grounded chat (RAG)**: answers cite evidence from your documents and stay within it
- **Voice agent**: real-time speech-to-text and text-to-speech conversations with your rep
- **Shareable public page** at `/rep/{profile_id}` with chat, voice and conversation summaries

## Tech stack

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, TypeScript |
| Backend | FastAPI, SQLAlchemy, MySQL |
| AI | Google Gemini (embeddings and generation), LangGraph agent |
| Vector search | Qdrant Cloud |
| Voice | Sarvam AI (Saaras STT, Bulbul TTS) |

## Getting started

**Prerequisites:** Python 3.11+, Node.js 20+, MySQL, and API keys for Gemini, Qdrant and Sarvam.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then fill in your DB URL and API keys
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`, with interactive docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

### Tests

```bash
cd backend && pytest
```

## Project structure

```
backend/    FastAPI app: API routes, RAG pipeline, LangGraph agent, voice services
frontend/   Next.js app: profile editor, knowledge base, public chat and voice pages
```

For more detail, see [`backend/README.md`](backend/README.md) and [`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md).
