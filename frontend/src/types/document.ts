export interface DocumentRecord {
  id: number;
  original_filename: string;
  file: string;
  status: "unclassified" | "classified" | "validated";
  document_type: number | null;
  document_type_name: string | null;
  predicted_document_type: number | null;
  classification_confidence: number | null;
  checklist_item: number | null;
  uploaded_by_type: "customer" | "internal" | "system";
  created_at: string;
  is_superseded: boolean;
}
