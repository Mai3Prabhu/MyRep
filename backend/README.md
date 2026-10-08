# MyRep 

## What is MyRep?

MyRep is a multi-user AI Professional Representative. It lets a person configure their professional identity (profile, experience, projects, skills, etc.) and later deploy an AI voice representative that answers questions about them using verified information.

**Core principle:** The AI is not the source of truth. The user's stored profile is the source of truth. The AI reads from it.

---

## What Layer 1 does

Layer 1 is the foundation: a clean FastAPI backend that can create, read, update, and delete a user's professional profile in MySQL. No AI, no voice, no authentication yet.

Layer 2.1 adds document upload. A profile owner can upload PDF files. The file is stored on local disk and metadata is recorded in MySQL. No text extraction, embeddings, or RAG yet.

---

## Why FastAPI?

- Native async support and excellent performance
- Automatic request/response validation via Pydantic
- Auto-generated interactive docs at `/docs`
- Clean dependency injection (e.g. database sessions per request)

## Why MySQL?

- Relational structure for profile metadata (name, headline, etc.)
- Native JSON column type for flexible nested data (skills, experience, projects)
- Widely available and straightforward to run locally

---

## Directory structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router mounting, table creation
│   ├── core/
│   │   └── config.py        # Reads .env via pydantic-settings
│   ├── db/
│   │   ├── database.py      # SQLAlchemy engine, session factory, get_db dependency
│   │   └── models.py        # Profile + Document ORM models
│   ├── schemas/
│   │   ├── profile.py       # Pydantic schemas for profile request/response
│   │   └── document.py      # Pydantic schemas for document response
│   ├── api/
│   │   └── routes/
│   │       ├── profiles.py  # Profile CRUD route handlers
│   │       └── documents.py # Document upload and retrieval route handlers
│   └── services/
│       ├── profile_service.py   # Profile business logic
│       ├── document_service.py  # Document business logic + validation
│       └── storage_service.py   # File persistence (local disk; replaceable)
├── storage/
│   └── documents/           # Uploaded PDFs (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Environment setup

```bash
cd backend
cp .env.example .env
```

Edit `.env` with your MySQL credentials:

```
DATABASE_URL=mysql+pymysql://root:yourpassword@localhost:3306/myrep
CORS_ORIGINS=http://localhost:3000
DOCUMENT_STORAGE_PATH=storage/documents
MAX_DOCUMENT_SIZE_MB=10
```

---

## Start MySQL locally

If MySQL is not installed, install it from https://dev.mysql.com/downloads/.

Then create the database:

```bash
mysql -u root -p
CREATE DATABASE myrep;
EXIT;
```

---

## Install dependencies and start the server

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

The server starts at `http://localhost:8000`.

Tables are created automatically on first startup.

Interactive API docs: `http://localhost:8000/docs`

---

## Test the API

### Health check

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Create a profile

```bash
curl -X POST http://localhost:8000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Doe",
    "headline": "Senior Software Engineer",
    "about": "I build distributed systems and mentor teams.",
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "experience": [
      {
        "company": "Acme Corp",
        "role": "Senior Engineer",
        "start": "2020-01",
        "end": null,
        "description": "Led backend platform team."
      }
    ],
    "projects": [
      {
        "name": "OpenDeploy",
        "url": "https://github.com/jane/opendeploy",
        "description": "Open-source deployment tool."
      }
    ],
    "education": [
      {
        "institution": "State University",
        "degree": "B.Sc. Computer Science",
        "year": 2016
      }
    ],
    "contact_preferences": {
      "preferred_channel": "email",
      "open_to_work": true
    }
  }'
```

**Response (201):**
```json
{
  "id": "a1b2c3d4-...",
  "name": "Jane Doe",
  "headline": "Senior Software Engineer",
  ...
  "created_at": "2026-10-01T00:00:00Z",
  "updated_at": "2026-10-01T00:00:00Z"
}
```

### Retrieve a profile

```bash
curl http://localhost:8000/api/v1/profiles/<id>
```

### Update a profile

```bash
curl -X PUT http://localhost:8000/api/v1/profiles/<id> \
  -H "Content-Type: application/json" \
  -d '{"headline": "Staff Engineer"}'
```

### Delete a profile

```bash
curl -X DELETE http://localhost:8000/api/v1/profiles/<id>
# 204 No Content
```

### Profile not found

```bash
curl http://localhost:8000/api/v1/profiles/00000000-0000-0000-0000-000000000000
# {"detail": "Profile 00000000-0000-0000-0000-000000000000 not found."}
```

---

## Document upload (Layer 2.1)

### Upload a PDF to a profile

```bash
curl -X POST http://localhost:8000/api/v1/profiles/<profile_id>/documents \
  -F "file=@/path/to/resume.pdf"
```

**Response (201):**
```json
{
  "id": "d1e2f3...",
  "profile_id": "a1b2c3...",
  "filename": "resume.pdf",
  "content_type": "application/pdf",
  "file_size": 84321,
  "created_at": "2026-10-01T00:00:00Z",
  "updated_at": "2026-10-01T00:00:00Z"
}
```

### List documents for a profile

```bash
curl http://localhost:8000/api/v1/profiles/<profile_id>/documents
```

### Get a single document by ID

```bash
curl http://localhost:8000/api/v1/documents/<document_id>
```

### Validation errors

```bash
# Non-PDF → 415
curl -X POST http://localhost:8000/api/v1/profiles/<id>/documents -F "file=@image.png"

# File too large → 413
# (configurable via MAX_DOCUMENT_SIZE_MB in .env)

# Unknown profile → 404
curl -X POST http://localhost:8000/api/v1/profiles/00000000-0000-0000-0000-000000000000/documents \
  -F "file=@resume.pdf"
```

Uploaded files are stored at `storage/documents/{profile_id}/{uuid}_name.pdf` relative to the `backend/` directory.
