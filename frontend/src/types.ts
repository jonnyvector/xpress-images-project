export interface Project {
  id: string;
  name: string;
  product_type: string;
  material_type: string;
  door_style: string | null;
  corner_style: string;
  style_notes: string;
  gemini_model: string;
  selected_swatches: string[];
  upload_filename: string | null;
  has_signature: boolean;
  has_base_image: boolean;
  learning_status: 'idle' | 'running' | 'done' | 'error';
  learning_error: string | null;
  generation_status: 'idle' | 'running' | 'done';
  generation_completed: number;
  generation_total: number;
  results: ProjectResult[];
  errors: ProjectError[];
  retrying_indices: number[];
  signature_version: number;
  version_count: number;
}

export interface SignatureVersion {
  version: number;
  created_at: string;
  material_type: string;
  door_style: string | null;
  corner_style: string;
  style_notes: string;
  result_count: number;
}

export interface ProjectResult {
  index: number;
  wood_name: string;
}

export interface ProjectError {
  wood_name: string;
  error: string;
}

export interface GenerationStatus {
  status: 'idle' | 'running' | 'done';
  completed: number;
  total: number;
  results: { index: number; wood_name: string }[];
  errors: ProjectError[];
  retrying_indices: number[];
}

export interface Swatch {
  key: string;
  name: string;
  description?: string;
  swatch_image_url: string;
  reference_image_url?: string;
  is_virtual: boolean;
  swatch_key?: string;
}

export interface Style {
  key: string;
  name: string;
  category: string;
}
