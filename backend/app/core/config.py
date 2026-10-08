from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables or a .env file.
    Pydantic-settings automatically reads these from the environment,
    so we never hardcode secrets in source code.
    """

    DATABASE_URL: str
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Document storage
    DOCUMENT_STORAGE_PATH: str = "storage/documents"
    MAX_DOCUMENT_SIZE_MB: int = 10

    # Text chunking (Layer 2.3)
    # CHUNK_SIZE: maximum number of characters per chunk. Paragraphs are kept
    # whole where possible; oversized paragraphs are split at sentence/word
    # boundaries. ~1000 chars ≈ 150–200 words — a good baseline for Gemini
    # embeddings in Layer 2.4.
    CHUNK_SIZE: int = 1000
    # CHUNK_OVERLAP: characters from the end of the previous chunk prepended
    # to the next chunk. Reduces context loss at chunk boundaries. 100 chars
    # ≈ 1–2 sentences of carry-over context.
    CHUNK_OVERLAP: int = 100

    # Gemini Embeddings (Layer 2.4)
    # GEMINI_API_KEY: secret key for the Google AI / Gemini API.
    # Must never be exposed to the frontend or logged.
    GEMINI_API_KEY: str = ""
    # GEMINI_EMBEDDING_MODEL: the current stable embedding model.
    # Use "gemini-embedding-2" — do not hardcode inside the service.
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    # EMBEDDING_DIMENSION: Matryoshka truncation target.
    # Gemini Embedding 2 default is 3072; we use 768 for efficiency.
    # Reduced dimensions are automatically L2-normalised by the model.
    # Qdrant collection creation (Layer 2.5) must use this same value.
    EMBEDDING_DIMENSION: int = 768

    # Qdrant (Layers 2.5 and 2.6)
    # QDRANT_URL: URL of the Qdrant Cloud cluster.
    QDRANT_URL: str = ""
    # QDRANT_API_KEY: Qdrant Cloud API key.
    # Must never be exposed to the frontend or logged.
    QDRANT_API_KEY: str = ""
    # QDRANT_COLLECTION: single shared collection for all profiles.
    # Profile isolation is enforced via payload filter on profile_id,
    # not by separate collections.
    QDRANT_COLLECTION: str = "myrep_knowledge"
    # RETRIEVAL_TOP_K: default number of chunks returned by semantic search.
    RETRIEVAL_TOP_K: int = 5

    # Gemini Generation (Layer 2.7)
    # GEMINI_GENERATION_MODEL: the model used to generate answers.
    # gemini-2.5-flash is closed to new keys. gemini-3.8-flash is listed but
    # often returns 503 under load. gemini-3.5-flash answers reliably.
    GEMINI_GENERATION_MODEL: str = "gemini-3.5-flash"
    # GENERATION_TEMPERATURE: controls randomness (0.0 = deterministic).
    # Low temperature (0.1) is appropriate for factual, grounded generation.
    GENERATION_TEMPERATURE: float = 0.1
    # GENERATION_MAX_TOKENS: hard ceiling on generated output length.
    GENERATION_MAX_TOKENS: int = 1024

    # RAG Evidence Control (Layer 2.8)
    # RAG_MIN_SCORE: minimum cosine similarity score for a retrieved chunk to be
    # considered usable evidence.  For Gemini Embedding 2 with COSINE in Qdrant,
    # the score is cosine similarity ∈ [-1, 1], typically [0, 1] in practice.
    # Default 0.0 disables threshold filtering entirely, preserving Layer 2.7
    # behavior.  Operators should tune this after observing real score
    # distributions; a value around 0.4–0.5 is a reasonable starting point.
    # Chunks below this threshold are classified as WEAK_EVIDENCE and do not
    # reach the generation step.
    RAG_MIN_SCORE: float = 0.0
    # RAG_MAX_CONTEXT_CHARS: maximum total characters of evidence text passed to
    # Gemini in a single generation call.  Chunks are included greedily in
    # descending relevance order; the first chunk that would exceed this limit
    # stops the inclusion.  0 = no limit.
    # Default 10000 chars ≈ 10 × default CHUNK_SIZE — generous but bounded.
    RAG_MAX_CONTEXT_CHARS: int = 10000

    # Session conversation context (Layer 3.6)
    # MAX_CONVERSATION_MESSAGES: maximum number of recent conversation turns
    # forwarded to Gemini for follow-up question context.  Only the most recent
    # N messages are used; older history is silently dropped.
    # Conversation history is contextual aid only — it is NOT professional evidence.
    # Increase for richer multi-turn context, decrease to reduce token usage.
    MAX_CONVERSATION_MESSAGES: int = 10

    # Sarvam AI voice (Layer 6) — STT/TTS only. Key stays server-side.
    # Realtime STT WebSocket currently accepts saaras:v3-realtime only.
    SARVAM_API_KEY: str = ""
    SARVAM_STT_MODEL: str = "saaras:v3-realtime"
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    SARVAM_TTS_LANGUAGE: str = "en-IN"
    SARVAM_TTS_SPEAKER: str = "shubh"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Silently ignore env vars that are not yet declared as fields.
        # This allows future layers to add configuration (e.g. Qdrant, LangGraph)
        # to .env without breaking the Settings validation for earlier layers.
        extra="ignore",
    )

    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a Python list, split on commas."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


# Single shared instance used throughout the app.
settings = Settings()
