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
  truncated_runs: string[];
  replica_approved: boolean;
  base_image_id: string | null;
  qa_verdicts: Record<string, QaVerdict>;
  latest_run: RunSummary | null;
  missing_swatches: string[];
}

export interface QaVerdict {
  verdict: 'pass' | 'regenerate' | 'needs_human' | 'error' | null;
  gates_as?: string;
  reason?: string;
  scores?: Record<string, number>;
  geometry?: string | null;
  qa_status: 'pending' | 'judging' | 'done';
  judged_at?: string;
}

export interface RunSummary {
  run_id: string;
  status: 'running' | 'done' | 'truncated';
  started_at: string;
  images_submitted: number;
  unconsented_images: number;
  planned: number;
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
  image_id: string;
  attempt: number;
}

export interface ProjectError {
  wood_name: string;
  error: string;
}

export interface GenerationStatus {
  status: 'idle' | 'running' | 'done';
  completed: number;
  total: number;
  results: { index: number; wood_name: string; image_id: string }[];
  errors: ProjectError[];
  retrying_indices: number[];
  replica_approved: boolean;
  qa_verdicts: Record<string, QaVerdict>;
}

// Fixed reject-reason vocabulary — mirrors backend/qa/labels.py REASONS.
export const REJECT_REASONS = [
  'geometry_drift',
  'profile_character',
  'material_realism',
  'artifacts',
  'other',
] as const;

export interface Approval {
  image_id: string;
  project_id: string;
  kind: 'replica' | 'variant';
  verdict: 'approved' | 'rejected';
  reasons: string[];
  note: string;
  decided_at: string;
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

export interface CoverageGap {
  expected: number;
  generated: number;
  missing: string[];
  excluded: string[];
}

export interface CoverageProduct {
  title: string;
  net_sales: number;
  quantity: number;
  covered: boolean;
  matched_project_ids: string[];
  approved_count: number;
  approved_total: number;
  on_shopify: boolean | null;
  shopify_listings: ShopifyListing[];
  variations_complete: boolean;
  in_shopify: boolean;
  canonical_project_id: string | null;
  excluded_colors: string[];
  gap: CoverageGap | null;
  stale: boolean;
}

export interface CoverageCategory {
  key: string;
  label: string;
  covered: number;
  total: number;
  variations_complete: number;
  in_shopify_count: number;
  products: CoverageProduct[];
}

export interface CoverageResponse {
  categories: CoverageCategory[];
  shopify_source: 'live' | 'csv' | null;
  shopify_synced_at: string | null;
  shopify_admin_url: string | null;
  shopify_error: string | null;
}

// A live Shopify product matched to a coverage row (from Refresh from Shopify).
export interface ShopifyListing {
  handle: string;
  title: string;
  status: string;
  wood_count: number;
  ai_wood_count: number;
  fully_imaged: boolean;
  missing_woods: string[];
  mismatched_woods: string[];
}

// QA endpoints (/api/qa/*)
export interface ReliabilityRates {
  decisive_n: number;
  agreement_rate: number | null;
  deferral_n: number;
  deferral_rate: number | null;
  null_n: number;
  disagreements: number;
}

export interface ReliabilityAggregates {
  total: ReliabilityRates;
  by_kind: Record<string, ReliabilityRates>;
  by_style_class: Record<string, ReliabilityRates>;
}

export interface QueueVariant {
  image_id: string;
  index: number;
  wood_name: string;
  attempt: number;
  verdict: QaVerdict;
}

export interface QueueProject {
  project_id: string;
  project_name: string;
  has_sample: boolean;
  replica: { image_id: string | null; pending: boolean; verdict: QaVerdict | null };
  variants: QueueVariant[];
  pending_count: number;
}

export interface ReviewQueueData {
  projects: QueueProject[];
  total_pending: number;
}
