export interface DocumentItem {
  id: string;
  profile_id: string;
  filename: string;
  content_type: string;
  file_size: number;
  indexing_status: string;
  indexed_at: string | null;
  indexed_chunks: number | null;
  created_at: string;
  updated_at: string;
}
