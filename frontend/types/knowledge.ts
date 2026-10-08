export type IndexingStatus = 'NOT_INDEXED' | 'INDEXING' | 'INDEXED' | 'FAILED';

export interface DocumentStatusItem {
  id: string;
  filename: string;
  indexing_status: IndexingStatus;
  indexed_at: string | null;
  indexed_chunks: number | null;
  indexing_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeStatus {
  profile_id: string;
  total_documents: number;
  indexed_documents: number;
  not_indexed_documents: number;
  failed_documents: number;
  rag_ready: boolean;
}

export interface DocumentIndexResponse {
  document_id: string;
  profile_id: string;
  indexed_chunks: number;
  collection: string;
}
