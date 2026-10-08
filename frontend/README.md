# MyRep — Frontend (Layer 1 + Layer 2.1)

Initial Next.js frontend for MyRep, providing profile management and document upload integrated with the FastAPI backend.

## Tech Stack

- **Framework:** Next.js (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **State Management:** React local state (`useState`, `useEffect`)

## Architecture

```
Browser (Next.js)
       ↓ HTTP (JSON & multipart/form-data)
FastAPI Backend (http://127.0.0.1:8000)
       ↓
MySQL Database (metadata) + Local Storage (PDF files)
```

The browser **never** connects directly to MySQL and holds no database credentials. All communication is routed through FastAPI.

## Capabilities

1. **Profile Viewing & Editing:**
   - Load any existing profile by its UUID.
   - Display and edit: `name`, `headline`, `about`.
   - View and edit structured JSON fields: `skills`, `experience`, `projects`, `education`, `contact_preferences`.
   - Save updates via `PUT /api/v1/profiles/{profile_id}`.

2. **Document Upload & Listing:**
   - Upload PDF files via multipart `POST /api/v1/profiles/{profile_id}/documents`.
   - List all uploaded documents for a profile via `GET /api/v1/profiles/{profile_id}/documents`.
   - Real-time client-side validation (PDF format, size constraints) with loading and error states.

## Setup and Running

### 1. Configure Environment

Copy `.env.local.example` to `.env.local`:

```bash
cp .env.local.example .env.local
```

Ensure `NEXT_PUBLIC_API_BASE_URL` points to your running FastAPI backend:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 2. Install Dependencies

```bash
cd frontend
npm install
```

### 3. Start Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Backend Endpoints Consumed

- `POST /api/v1/profiles/` — Create profile
- `GET /api/v1/profiles/{profile_id}` — Get profile
- `PUT /api/v1/profiles/{profile_id}` — Update profile
- `POST /api/v1/profiles/{profile_id}/documents` — Upload PDF document
- `GET /api/v1/profiles/{profile_id}/documents` — List documents for profile
- `GET /api/v1/documents/{document_id}` — Get document metadata
