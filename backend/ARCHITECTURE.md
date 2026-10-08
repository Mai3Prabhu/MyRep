# MyRep Architecture

## What is MyRep?

MyRep is a multi-user AI Professional Representative. Given a profile and uploaded PDF documents (resumes, portfolios, CVs), it enables semantic search over that person's professional content and answers questions by retrieving relevant evidence from their documents and generating a grounded response.

---

## Current Pipeline (Layers 1–2.8)

```
PDF Upload
    ↓
MySQL: Document metadata stored
    ↓
PDF Extraction (pypdf, page-by-page)
    ↓
Text Chunking (paragraph-aware, bounded to CHUNK_SIZE=1000 chars)
    ↓
Gemini Embedding 2 (768-dimensional vectors, asymmetric format)
    ↓
Qdrant Cloud (cosine similarity index, payload-filtered by profile_id)
    ↓
Semantic Search: top-k chunks for a query × profile
```

---

## Data Store Responsibilities

### MySQL

MySQL is the **source of truth for structured application data**:

- Profile records (name, headline, about, skills, experience, etc.)
- Document metadata (filename, content_type, file_size, storage_path, profile_id)
- Relationships and foreign keys

MySQL is **not** used for:
- Storing embeddings (large float arrays are not a relational database concern)
- Semantic similarity queries (SQL does not support cosine similarity at scale)

### Local Storage

Original PDF files are written to disk under `storage/documents/{profile_id}/`.
The path is stored in MySQL as a relative path. The client never supplies a
filesystem path — it only provides a `document_id`, and the server derives
the path from the trusted MySQL record.

### Qdrant Cloud

Qdrant is the **vector indexing and semantic retrieval layer**:

- Stores 768-dimensional embeddings as "points"
- Each point has a payload (metadata) and a vector
- Supports cosine similarity search with server-side payload filters
- Used exclusively for semantic retrieval — not for profile metadata

Qdrant is **not** used for:
- Storing original documents or structured profile data
- Enforcing application-level access control (profiles, ownership)
- Any SQL-style relational queries

---

## Why One Shared Qdrant Collection?

The collection is named **`myrep_knowledge`** and holds chunks from all profiles.

**Why not one collection per profile?**

- Qdrant Cloud clusters have collection limits; creating one per user doesn't scale.
- Qdrant's payload filtering is designed for exactly this use case.
- A single collection is simpler to monitor, backup, and manage.
- Adding a new profile requires no Qdrant schema changes.

**How is isolation enforced?**

Every indexed point carries a `profile_id` in its payload. Every search query
**must** include a Qdrant server-side filter:

```python
Filter(must=[FieldCondition(key="profile_id", match=MatchValue(value=str(profile_id)))])
```

This is enforced inside `qdrant_service.search_chunks()` and cannot be bypassed
by the caller. Cross-profile retrieval is architecturally impossible through the
public API.

---

## Why is `profile_id` Stored in Qdrant But NOT Embedded?

**Stored in payload:** `profile_id` is tenant-isolation metadata used for
filtering. Qdrant applies the filter before computing similarity scores —
it is a precise equality match, not a semantic signal.

**Not embedded in the vector:** The embedding vector represents the *semantic
content* of the text. Including identifiers like `profile_id`, `document_id`,
`chunk_index`, or `page_number` would pollute the semantic space with
non-semantic information, degrading retrieval quality.

The embedded text uses only the document's filename and chunk content:

```
title: resume.pdf | text: Managed a team of 8 engineers...
```

---

## Why Cosine Similarity?

Gemini Embedding 2 with Matryoshka truncation produces L2-normalized vectors
at reduced dimensions. For unit-norm vectors, cosine similarity and dot product
are equivalent. Cosine similarity is:

- The standard metric for dense retrieval with normalized embeddings
- Scale-invariant (direction matters, not magnitude)
- Well-supported by Qdrant with HNSW indexing for fast approximate search

---

## Why Deterministic Point IDs?

Each Qdrant point's ID is derived from `(document_id, chunk_index)` using UUID v5:

```python
uuid.uuid5(NAMESPACE, f"{document_id}:{chunk_index}")
```

**Benefits:**
- Re-indexing the same chunk overwrites the old point (upsert semantics)
- No random IDs that would cause unbounded growth on repeated indexing
- Idempotent: the same document always produces the same point IDs

---

## Indexing Flow

```
POST /api/v1/documents/{document_id}/index
    ↓
MySQL: fetch Document → get profile_id (NEVER from client)
    ↓
Filesystem: load PDF from trusted path (stored in MySQL)
    ↓
pdf_extraction_service: extract text page-by-page
    ↓
chunking_service: split into bounded chunks (≤1000 chars, overlap=100)
    ↓
embedding_service.embed_chunks(): batch Gemini API call
    → format: "title: {filename} | text: {chunk_text}"
    → output: 768-dimensional L2-normalized vectors
    ↓
qdrant_service.index_embedded_chunks():
    1. Upsert new points with full payload  ← FIRST (old index preserved if this fails)
    2. Delete stale points: document_id == X AND chunk_index >= new_chunk_count
    ↓
Response: { document_id, profile_id, indexed_chunks, collection }
```

**Why upsert-first?**
The original delete-then-upsert approach had a window where a document was unindexed: if upsert failed after a successful delete, all indexed content for that document was lost until the next re-upload. With upsert-first, deterministic point IDs (`uuid5`) ensure the new chunks overwrite existing ones in-place. Only after a confirmed successful upsert are stale points (from a document that now has fewer chunks) cleaned up with a targeted `Range(gte=new_chunk_count)` filter. A failed stale-cleanup is harmless — the extra old-index points carry lower relevance rank and are corrected on the next re-index.

---

## Query / Retrieval Flow

```
POST /api/v1/profiles/{profile_id}/search
Body: { "query": "...", "top_k": 5 }
    ↓
MySQL: validate profile exists (raises 404 if not)
    ↓
embedding_service.embed_query():
    → format: "task: search result | query: {query}"
    → output: 768-dimensional L2-normalized vector
    ↓
qdrant_service.search_chunks():
    → cosine similarity search
    → filter: profile_id == requested_profile_id (server-side)
    → limit: top_k
    ↓
Response: { query, profile_id, results: [{ document_id, filename, page_number, chunk_index, text, score }] }
```

---

## RAG Answer Generation Flow (Layers 2.7 / 2.8)

```
POST /api/v1/profiles/{profile_id}/ask
Body: { "question": "..." }
    ↓
rag_service.answer_question():
    │
    ├─ search_service.search_profile()           ← Layer 2.6 retrieval
    │      → MySQL profile validation (404 if not found)
    │      → Gemini embed_query (query format)
    │      → Qdrant search_chunks (profile-isolated, top_k chunks)
    │
    ├─ evidence_service.deduplicate_chunks()      ← Layer 2.8
    │      → Remove (document_id, chunk_index) duplicates
    │      → First (highest-ranked) occurrence wins
    │
    ├─ evidence_service.assess_evidence()         ← Layer 2.8
    │      → Filter empty/whitespace-only text
    │      → Apply RAG_MIN_SCORE threshold (default 0.0 = disabled)
    │      → Returns EvidenceState
    │
    ├─ if NO_EVIDENCE or WEAK_EVIDENCE:
    │      → AskResponse(answer="insufficient information", sources=[],
    │                    evidence_status="no_evidence" | "weak_evidence")
    │      → Gemini is NEVER called
    │
    ├─ evidence_service.apply_context_budget()    ← Layer 2.8
    │      → Retain chunks in descending relevance order
    │      → Stop at first chunk exceeding RAG_MAX_CONTEXT_CHARS
    │
    └─ generation_service.generate_answer()       ← Layer 2.7
           → _format_evidence(): numbered "--- SOURCE N ---" blocks
           → client.models.generate_content(
                   model=GEMINI_GENERATION_MODEL,
                   contents=prompt,
                   config=GenerateContentConfig(
                       system_instruction=_SYSTEM_INSTRUCTION,
                       temperature=GENERATION_TEMPERATURE,
                       max_output_tokens=GENERATION_MAX_TOKENS,
                   )
             )
    ↓
Response: {
    question,
    answer,
    evidence_status: "evidence_available",
    sources: [{ document_id, filename, page_number, chunk_index, score }, ...]
}
```

**Evidence state semantics:**

| State | Meaning | Gemini called? |
|-------|---------|----------------|
| `no_evidence` | No chunks retrieved or all had empty text | No |
| `weak_evidence` | Chunks exist but all scored below RAG_MIN_SCORE | No |
| `evidence_available` | At least one usable, above-threshold chunk found | Yes |

**Grounding contract:**
The system instruction explicitly prohibits Gemini from inventing professional claims. The LLM is NOT the source of truth — uploaded documents are.

**Profile isolation:**
`profile_id` is taken from the MySQL-validated path parameter and passed directly to `search_service`. It is never extracted from the question text.

**Prompt injection protection (Layer 2.8):**
Uploaded documents are untrusted content. The system instruction explicitly classifies retrieved `--- SOURCE N ---` blocks as untrusted DATA and instructs Gemini to ignore any directives found within them.

**Partial and conflicting evidence (Layer 2.8):**
- Partial: LLM answers supported sub-questions and explicitly acknowledges unsupported ones
- Conflicting: LLM presents the conflict, does not invent a resolution

**Retrieval relevance ≠ factual truth:**
A cosine similarity score means "semantically close to the query". It does NOT mean "factually correct". Scores are used only as a retrieval signal. The LLM is instructed to evaluate the text content, not the score.

**Service separation:**

| Service | Responsibility |
|---------|---------------|
| `search_service` | Query embedding + Qdrant retrieval + profile validation |
| `evidence_service` | Deduplication + assessment + context budget (pure Python, no external calls) |
| `generation_service` | Prompt formatting + Gemini generate_content |
| `rag_service` | Orchestration of all three services above |

**LangChain decision:**
Deliberately deferred through Layer 2.8. Direct `google-genai` SDK is cleaner and more transparent for single-turn grounded generation. LangChain would add an abstraction layer without meaningful benefit at this stage. Will be re-evaluated after the RAG behavior is stable.

---

## Asymmetric Embedding Format

Gemini Embedding 2 is designed for **asymmetric retrieval**: documents and
queries are encoded differently so they map into the same semantic space
optimally.

| Type     | Format                                         |
|----------|------------------------------------------------|
| Document | `title: {filename} \| text: {chunk_text}`       |
| Query    | `task: search result \| query: {user_question}` |

---

---

## Layer 4 — Public / Recruiter View

A shareable professional representative at `/rep/{profile_id}`.

This is **not** the private management UI. Public visitors never receive
edit, upload, indexing, or internal metadata controls.

### Visibility flag

```
Profile.is_public  default False
```

Existing profiles stay private until the owner turns **Public profile** on
from the private dashboard. There is no authentication around this toggle
yet — it is an MVP visibility switch, not an authorization system.

Private and missing profiles both return HTTP 404 with the same message
(`Profile not found.`) so callers cannot enumerate private profiles.

### Public vs private security boundary

| Surface | Path | Audience |
|---------|------|----------|
| Private management | `/api/v1/profiles/...`, `/api/v1/documents/...` | Profile owner (MVP: anyone with the UUID) |
| Public representation | `/api/v1/public/profiles/{id}` | Recruiters / visitors |
| Public conversation | `/api/v1/public/profiles/{id}/ask` | Recruiters / visitors |

The public API uses dedicated schemas (`PublicProfile`, `PublicAskResponse`).
It does **not** reuse `ProfileResponse` or private `AskResponse`.

`PublicProfile` includes: name, headline, about, skills, experience,
projects, education, and a boolean `knowledge_ready`.

It does **not** include: contact_preferences, created_at, updated_at,
storage paths, indexing errors, document IDs, Qdrant IDs.

### Public chat (Layer 4.1)

```
Visitor
  → GET /api/v1/public/profiles/{id}     (must be is_public)
  → POST /api/v1/public/profiles/{id}/ask
       → public_service.require public
       → rag_service.answer_question()   (same evidence pipeline)
       → strip source document_id / score / chunk_index
```

Public chat:
- reuses the existing RAG / evidence / generation pipeline
- uses the same session-only conversation history
- is profile-isolated via the URL path `profile_id`
- does not persist visitor conversations
- cannot mutate profile data

### Source exposure

Private `/ask` sources may include document_id, chunk_index, and score.
Public `/ask` sources contain only:

    filename (basename only)
    page_number

### Rate limiting

Public AI endpoints are unauthenticated and will need rate limiting before
production. Redis / gateway rate limiting is **deferred** — do not treat
the current public `/ask` as production-safe against abuse.

---

## Layer 5 — LangGraph Agent Orchestration

LangGraph decides **what kind of request this is** and **which application
step runs next**. It does not replace RAG.

```
USER QUESTION
     |
classify_intent     (rules + optional LangChain structured classification)
     |
     +-- knowledge --> rewrite_query --> retrieve_knowledge --> assess
     |                      |                   |
     |                      |            enough / insufficient
     |                      |                   |
     |                      +--> generate_answer   clarify
     |
     +-- contact --> route_contact
     |                 |-- no public method -> safe refusal
     |                 |-- public method -> offer + require confirm
     |                 +-- confirmed -> create_contact_request (PENDING)
     |
     +-- unsupported --> handle_unsupported (no retrieval, no rewrite)
```

`rewrite_query` runs only on the knowledge path. CONTACT and UNSUPPORTED skip it.

### How existing RAG is reused

`rewrite_query` calls `query_rewrite_service.rewrite_for_retrieval()`.

`retrieve_knowledge` calls `rag_service.retrieve_evidence()` with
`retrieval_query` (search + dedupe + assess + budget).

`generate_answer` calls `rag_service.generate_grounded_answer()` with the
**original** user question.

`clarify` uses `rag_service.insufficient_response()`.

`rag_service.answer_question()` remains independently usable.

The graph never calls Qdrant, Gemini embeddings, or generation_service directly.

### LangChain usage

- `ClassifiedIntent` structured output via `langchain-google-genai` when
  the API key is present and rules do not already match.
- `StructuredTool` `create_contact_request` — typed, no generic executor.
  The application invokes the tool; the model cannot pick `profile_id`.

Direct `google-genai` generation/embedding is unchanged.

### Graph state

`profile_id`, `question`, `retrieval_query`, `query_rewritten`, bounded
`conversation_history`, `intent`, `retrieved_chunks`, `evidence_status`,
`answer`, `source_references`, `contact_status`, `channel`. No API keys,
no storage paths, no full profile dump.

### Contact permission model (Layer 5.1)

`contact_preferences` is unstructured JSON. The **only** shareable methods
are values under an explicit nested object:

```
{ "public": { "email": "...", "linkedin": "...", "website": "..." } }
```

Keys such as `email`, `phone`, `preferred`, `allow_inquiries` are private.

No email provider exists. Recording a request stores status **PENDING**.
The assistant must say it was recorded, not delivered. COMPLETED is reserved
for a future delivery integration.

Private and public `/ask` endpoints share this graph. Visibility is enforced
by `public_service` before the graph runs.

---

## API Endpoints (Layers 1–8)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/profiles/` | Create profile |
| GET | `/api/v1/profiles/{id}` | Get profile |
| PUT | `/api/v1/profiles/{id}` | Update profile |
| DELETE | `/api/v1/profiles/{id}` | Delete profile |
| POST | `/api/v1/profiles/{id}/documents` | Upload PDF |
| GET | `/api/v1/profiles/{id}/documents` | List documents |
| GET | `/api/v1/profiles/{id}/documents/status` | **Document indexing status** |
| GET | `/api/v1/profiles/{id}/knowledge-status` | **Knowledge readiness** |
| GET | `/api/v1/documents/{id}` | Get document metadata |
| POST | `/api/v1/documents/{id}/extract` | Extract text (dev) |
| POST | `/api/v1/documents/{id}/chunks` | Chunk text (dev) |
| POST | `/api/v1/documents/{id}/embeddings` | Generate embeddings (dev) |
| POST | `/api/v1/documents/{id}/index` | **Index into Qdrant** |
| POST | `/api/v1/profiles/{id}/search` | **Semantic search** |
| POST | `/api/v1/profiles/{id}/ask` | **LangGraph orchestration (RAG / contact / unsupported)** |
| GET | `/api/v1/public/profiles/{id}` | **Public professional profile** |
| POST | `/api/v1/public/profiles/{id}/ask` | **Public ask via the same graph; sanitized sources** |
| GET | `/api/v1/voice/ready` | **Whether Sarvam is configured (no secrets)** |
| WS | `/api/v1/voice/profiles/{id}/live` | **Private Sarvam voice session** |
| WS | `/api/v1/public/profiles/{id}/voice/live` | **Public Sarvam voice session (`is_public` required)** |

---

## Layer 3.5 — MyRep Chat UI

A dedicated chat experience at `/profile/chat?id=UUID`.

### Component structure

```
app/profile/chat/page.tsx        — chat page (full-height, session-scoped)
components/chat/
    ChatWindow.tsx               — scrollable message list + auto-scroll
    ChatMessage.tsx              — user/assistant bubble with Markdown rendering
    ChatInput.tsx                — auto-resizing textarea (Enter=send, Shift+Enter=newline)
    SourceReferences.tsx         — provenance list under assistant messages
    SuggestedQuestions.tsx       — shown when no messages exist
```

### Design principles

- Professional, not "ChatGPT clone" — framed as "Talk to this person's AI representative"
- No fake streaming, no token animation — answer appears when ready
- Markdown rendered via `react-markdown` + `remark-gfm` (safe, no `dangerouslySetInnerHTML`)
- Sources shown as `filename · page N` for provenance transparency
- Evidence status translated into user-friendly notes (not raw enum values)
- Knowledge readiness warning if profile has no indexed documents

### Navigation

- Profile page has a "Talk to MyRep →" CTA linking to `/profile/chat?id=...`
- Chat header has "← Knowledge Base" back link

---

## Layer 3.6 — Session-Based Conversational Context

### What it is

A lightweight, session-only conversation memory that helps Gemini interpret
follow-up questions by resolving pronouns and references to earlier topics.

### What it is NOT

- NOT persistent memory (refresh clears the conversation)
- NOT long-term memory (no MySQL storage)
- NOT agent memory (no LangGraph)
- NOT authoritative evidence (previous assistant messages are not facts)

### Architecture

```
Frontend React state           Backend
─────────────────────          ──────────────────────────────────────────────
ChatMessage[]                  AskRequest.conversation_history
(session-only)        ──────>  (bounded list[ConversationTurn])
                                    |
                               rag_service.answer_question()
                                    |-- bounds to MAX_CONVERSATION_MESSAGES
                                    |-- passes to generation_service only
                                    |-- search_service receives question ONLY
                               generation_service.generate_answer()
                                    |-- includes CONVERSATION CONTEXT section
                                    |-- labelled "for reference only"
                                    |-- NOT mixed with VERIFIED EVIDENCE
```

### Evidence vs. context: strict separation

| Source | Role | Authoritative? |
|--------|------|---------------|
| Retrieved Qdrant chunks | VERIFIED PROFESSIONAL EVIDENCE | Yes |
| Conversation history turns | CONVERSATION CONTEXT | No — reference only |

The system instruction explicitly tells Gemini that previous assistant messages
are not authoritative facts and that professional claims must come from the
VERIFIED EVIDENCE blocks only.

### History bounding

- Hard cap of 50 turns enforced by Pydantic schema (`max_length=50`)
- Configurable soft cap: `MAX_CONVERSATION_MESSAGES=10` (backend env var)
- `rag_service` silently drops older turns (`history[-N:]`)
- Frontend sends at most `MAX_HISTORY_TO_SEND=10` turns

### Retrieval query vs original question (Layer 7)

Conversation history does **not** go to Qdrant. Follow-ups may first be
rewritten into a self-contained `retrieval_query`. Qdrant still embeds that
string only. Generation still receives the original user question, the
bounded history, and retrieved evidence.

Standalone questions skip the rewriter (no extra Gemini call). Rewrite
failures fall back to the original question. See Layer 7.

**Documented limitation:** Query rewriting is heuristic + a short Gemini
completion. It is an optimization, not measured retrieval-quality gain.

### Conversation security

Conversation history is treated as untrusted user input:
- Captured in the CONVERSATION CONTEXT prompt block (not the system instruction)
- Explicitly labelled as contextual aid, not as instructions
- A previous assistant message containing "ignore previous instructions" is
  treated as document content to evaluate, not as a command to execute

### Conversation reset

"Clear conversation" on the chat page clears React state only. It does NOT:
- Delete profile data
- Delete uploaded documents
- Remove Qdrant vectors
- Touch MySQL

---

## What Is Intentionally NOT Implemented Yet

| Feature | Reason |
|---------|--------|
| Persistent conversation storage | Session-only is sufficient for MVP |
| Reranking / hybrid search | Clean baseline first |
| Query expansion / HyDE | Layer 7 only rewrites follow-ups; not full expansion |
| Email / CRM delivery of contact requests | Requests are recorded as PENDING only |
| Authentication / authorization | Not in scope for MVP |
| Production rate limiting | Required before exposing public `/ask` or voice webhooks in production |
| Visitor accounts / analytics | Public chat/voice is session-only |
| Alembic migrations | Manual `create_all` + startup migration is sufficient for MVP |
| Phone / outbound calling | Voice MVP is in-browser only |
| LangSmith / RAGAS / eval DB | Layer 8 is an in-repo fixture harness, not an external eval platform |
| Production latency SLOs | Harness `perf_counter` figures are not production latency |

---

## Environment Variables

```
# MySQL
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/myrep

# Gemini (Layers 2.4–2.8)
GEMINI_API_KEY=...
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=768

# Qdrant Cloud (Layers 2.5–2.6)
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=...
QDRANT_COLLECTION=myrep_knowledge
RETRIEVAL_TOP_K=5

# Gemini Generation (Layer 2.7)
GEMINI_GENERATION_MODEL=gemini-2.5-flash
GENERATION_TEMPERATURE=0.1
GENERATION_MAX_TOKENS=1024

# RAG Evidence Control (Layer 2.8)
# RAG_MIN_SCORE=0.0       # 0.0 = disabled; 0.4–0.5 = moderate; 0.6+ = strict
# RAG_MAX_CONTEXT_CHARS=10000  # 0 = unlimited

# Session conversation context (Layer 3.6)
# MAX_CONVERSATION_MESSAGES=10  # most recent turns forwarded to generation

# Sarvam AI voice (Layer 6) — server-side only
# SARVAM_API_KEY=...
# SARVAM_STT_MODEL=saaras:v3-realtime
# SARVAM_TTS_MODEL=bulbul:v3
# SARVAM_TTS_LANGUAGE=en-IN
# SARVAM_TTS_SPEAKER=shubh

# Chunking
CHUNK_SIZE=1000
CHUNK_OVERLAP=100
```

---

## Layer 6 — Voice MyRep (Sarvam)

Sarvam is the voice modality. MyRep remains the application brain.

```
Microphone (16 kHz PCM16)
    ↓
Browser WebSocket (no API keys)
    ↓
FastAPI  WS  /voice/.../live   — path profile_id, public/private gate
    ↓
Sarvam Saaras realtime STT  (saaras:v3-realtime)
    ↓
transcript.partial → UI only
transcript.final   → voice_service.answer_turn()
    ↓
agent_service.handle_question(channel="voice")
    ↓
existing LangGraph → RAG / contact / unsupported
    ↓
answer text
    ↓
Sarvam Bulbul v3 streaming TTS
    ↓
audio chunks → browser playback
```

### What Sarvam handles vs what MyRep handles

| Sarvam | MyRep |
|--------|-------|
| Speech-to-text (Saaras) | Profile identity (path parameter) |
| Text-to-speech (Bulbul v3) | Public/private visibility |
| VAD / utterance boundaries | LangGraph routing |
| Interim transcripts | RAG, evidence, grounding |
| | Contact PENDING records |

### Profile identity

The WebSocket path `{profile_id}` is the only profile identity. Public live sessions call `public_service` first (`is_public` required). A claimed id in a client message is ignored.

Official Sarvam realtime STT (`wss://api.sarvam.ai/speech-to-text-realtime/ws`) currently accepts only `saaras:v3-realtime`. `saaras:v4` is the recommended REST/batch model and is not the accepted value on this WebSocket. TTS uses Bulbul v3 (`shubh`, `en-IN`, 24 kHz MP3 chunks).

### Turn lifecycle (`voice_runtime._LiveSession`)

```
LISTENING --accepted final--> THINKING --first TTS audio--> SPEAKING
    ^                                                         |
    |                     turn finished, audio sent           v
    +---- playback_done(turn_id) / interrupt(turn_id) --- AWAITING_PLAYBACK
```

- STT events are read in their own loop; each turn runs as a separate task.
  (Previously the turn ran inside the event loop, so finals that arrived
  mid-turn were queued and replayed as new turns afterwards — the cause of
  the repeated "I don't have enough information" replies.)
- Microphone audio is forwarded to STT only in LISTENING.
- A final starts a turn only in LISTENING and only if new audio arrived since
  LISTENING began. Other finals are dropped and logged
  (`voice_final_dropped reason=phase_*|no_new_audio|echo_of_answer`).
  The echo check compares against the last **answer**, never the last
  question, so a visitor can ask the same question twice.
- Every turn-scoped message carries `turn_id`; an interrupted or superseded
  turn sends nothing more. One accepted final = one agent run.
- The browser reports `playback_done` when its audio drains. If it never
  does, the server returns to LISTENING after the audio it sent could have
  played (liveness only).

### Interruptions

The visitor taps **Stop** (client `interrupt{turn_id}`): playback stops, the
turn is invalidated, and the session returns to LISTENING. No agent call is
made or repeated. Voice barge-in is not enabled: the microphone stays muted
while the Rep speaks. Interrupting does **not** roll back an already-persisted
`ContactRequest`. If the visitor interrupts before confirming contact, no
request is created.

### Conversation summary ("What we've discussed")

`conversation_summary_service.build_turn_summary` produces a deterministic
per-turn digest (`AskResponse.summary`, `PublicAskResponse.summary`, voice
`answer.summary`). No model call. Entities/technologies must appear in an
affirmative sentence of the Rep's answer **and** in a vocabulary of names
from public-safe profile fields plus a fixed technology lexicon. "Not enough
information" answers contribute only the question. The frontend merges
digests per session; nothing is persisted or fed back into generation.

### Evidence excerpts

Private sources carry a short verbatim `excerpt` of the consulted chunk.
Public sources remain filename + page only (`PublicSourceReference`).

### Frontend

- `/rep/[profile_id]/voice` — public
- `/profile/voice?id=` — private
- Shared `components/voice/VoicePanel.tsx`
- `SARVAM_API_KEY` never reaches the browser (`NEXT_PUBLIC_SARVAM_API_KEY` is not used)

---

## Layer 7 — Conversation-Aware Query Rewriting

Follow-up questions like "Why did she use it?" are poor embedding queries.
Layer 7 rewrites **retrieval** only. It does not become evidence and does
not replace the original question.

```
original question
       ↓
query rewrite when needed   (knowledge intent only)
       ↓
retrieval_query
       ↓
existing retrieve_evidence (profile_id filter unchanged)
       ↓
evidence
       ↓
original question + conversation + evidence
       ↓
generation
```

### original_question vs retrieval_query

| Field | Used for |
|-------|----------|
| `question` (original) | Intent classification, generation, contact text |
| `retrieval_query` | Embedding + Qdrant search only |

The rewriter never receives or returns `profile_id`. Isolation stays in
`retrieve_evidence` / `search_service`.

### When rewriting is skipped

- Empty conversation history
- Standalone / self-contained questions (e.g. "What is FastAPI?", "Tell me about MindMate.")
- CONTACT and UNSUPPORTED intents (no rewrite node)

### Fallback

Gemini timeout, empty output, malformed output, or invented entities not
present in the question/history → `retrieval_query = original question`.
Rewriting is an optimization; a failure must not fail the user request.

### History is not evidence

The rewriter may use history to resolve "she" / "it" / "that project".
It must not treat assistant turns as verified professional facts.
Grounding still comes from retrieved chunks.

### Voice and public/private

Text and voice share `query_rewrite_service` via the same graph.
Public vs private authorization stays outside the rewriter.

---

## Layer 8 — Evaluation and Lightweight Observability

Evaluation was added **before** BM25, hybrid search, or reranking so future
retrieval work can be measured against a documented baseline. This layer
does not add retrieval features, a second graph, LangSmith, RAGAS, an
evaluation database, BM25, or reranking.

### Three independent result types

Evaluation output and this section distinguish three things. They must not
be collapsed into one quality score.

| Result type | What it is | What it is not |
|-------------|------------|----------------|
| **1. Behavioral / regression** | Intent routing, rewrite skip/fallback, isolation, contact privacy, unsupported refusal, voice using the same graph | Retrieval accuracy |
| **2. Fixture-based retrieval baseline** | Keyword overlap over a static fixture corpus filtered by `profile_id` | **Not** Qdrant cosine search. **Not** Gemini embedding quality. **Not** production retrieval accuracy |
| **3. Harness latency measurements** | `time.perf_counter` around mocked graph invocations in the eval harness | **Not** production latency. **Not** an SLO |

Fixture retrieval results must never be described as Qdrant/Gemini production
retrieval accuracy. Harness latency must never be described as production
latency or an SLO.

### Dataset

About 25 deterministic cases in `tests/evaluation/cases.py`, covering:
DIRECT_FACTUAL, TECHNICAL_FACTUAL, CONVERSATIONAL_FOLLOWUP,
MULTI_TURN_ENTITY_REFERENCE, STANDALONE_QUERY, AMBIGUOUS_FOLLOWUP,
UNSUPPORTED_FACT, NO_EVIDENCE, CONFLICTING_EVIDENCE, CONTACT_REQUEST,
PUBLIC_PROFILE_ISOLATION, PROFILE_ISOLATION, VOICE_PATH.

Two fixture profiles. Keyword overlap is filtered by `profile_id`.
Generation and rewrite Gemini calls are mocked so the runner does not hit
live APIs.

### Metrics (pass/fail + counts, no composite score)

- Behavioral: intent, rewrite skip/entity preservation, unsupported refusal, isolation, contact status, voice same graph
- Fixture retrieval: relevant fixture chunk found (keyword overlap), evidence_status vs expected, retrieved_chunk_count
- Harness: average and P95 `harness_total_latency_ms`

CI fails only on **behavioral** regressions. Fixture misses are reported in
section 2; they are not production recall.

### How to run

```
pytest tests/evaluation/ -s
```

Results are in-memory only. Nothing is written to MySQL.

### Observability (production request path)

Lightweight correlation only. No tracing backend.

| Piece | Location |
|-------|----------|
| `request_id` (`contextvars`) | `app/core/request_context.py` |
| Bind at entry | `agent_service.handle_question` via `request_scope()` — private, public, and voice all enter here |
| Stage timing | Existing nodes + `rag_service` + `query_rewrite_service` (`time.perf_counter`) |

Logged (structured, no secrets): `request_id`, `profile_id`, `channel`,
`intent`, `rewrite_applied`, `retrieval_query_len` (length only — not the
query text), `retrieved_chunk_count`, `evidence_status`, `success`,
`error_type`, `latency_ms` / `total_latency_ms`.

Never logged: `GEMINI_API_KEY`, `QDRANT_API_KEY`, `SARVAM_API_KEY`, full
question/history, prompts, raw `retrieval_query` text, document bodies,
`storage_path`.

`request_id` is log correlation only. It is not used for retrieval,
generation, or authorization.

### Why advanced retrieval is deferred

A fixture keyword baseline cannot identify a Qdrant/Gemini recall bottleneck.
Until live retrieval is measured separately, BM25, hybrid search, and
reranking would be unearned complexity.

### Where evaluation lives

Evaluation is **not** a production module and **not** an HTTP endpoint.

```
backend/tests/evaluation/
    corpus.py      fixture chunks (keyword overlap, profile_id filtered)
    cases.py       deterministic cases (≥20)
    harness.py     runs the existing LangGraph with retrieval/generation mocked
    test_evaluation_runner.py   prints the labeled report; fails CI on behavioral regressions only
```

The harness patches `search_profile`, Gemini generation/rewrite, and intent
LLM classification. It invokes `agent_service.handle_question` (and
`public_service.ask_public_profile` for public-gate cases). Voice cases set
`channel="voice"` on the same graph.

