export interface TemplateVariant {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
  is_default: boolean;
  published_version_id: number | null;
  published_version_number: number | null;
}

export interface ServiceOffering {
  id: number;
  service_type: number;
  service_type_name: string;
  flag: number | null;
  flag_name: string | null;
  flag_relationship: number | null;
  flag_relationship_label: string | null;
  display_name: string;
  description: string;
  status: string;
  accepts_new_requests: boolean;
  valid_from: string | null;
  valid_until: string | null;
  template_variants: TemplateVariant[];
  created_at: string;
  updated_at: string;
}
