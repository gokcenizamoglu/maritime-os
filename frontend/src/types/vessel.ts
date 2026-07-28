export interface Vessel {
  id: number;
  name: string;
  imo_number: string;
  customer: number;
  customer_name: string;
  current_flag: number | null;
  current_flag_name: string | null;
  vessel_type: string;
  created_at: string;
  updated_at: string;
}
