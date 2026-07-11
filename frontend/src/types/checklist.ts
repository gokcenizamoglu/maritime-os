/**
 * Matches `checklists/serializers.py::ChecklistItemSerializer` exactly.
 * `GET /api/checklist-items/?service_request={id}` — the query param IS
 * genuinely implemented server-side (backend/checklists/views.py::
 * ChecklistItemViewSet.get_queryset), unlike documents (see types/document.ts note).
 */
export interface ChecklistItem {
  id: number;
  document_type: number;
  document_type_name: string;
  required_count: number;
  is_complete: boolean;
  mapped_document_count: number;
}
