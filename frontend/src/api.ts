import type { Project, Swatch, Style, GenerationStatus, SignatureVersion } from './types';

function getApiKey(): string {
  return localStorage.getItem('gemini_api_key') ?? '';
}

// Auth headers for raw fetch() calls that can't use request() (blob/204 responses).
function authHeaders(): Record<string, string> {
  const apiKey = getApiKey();
  return apiKey ? { 'X-API-Key': apiKey } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const apiKey = getApiKey();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> ?? {}),
  };
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] ?? 'application/json';
  }
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// Projects
export function listProjects(): Promise<Project[]> {
  return request<Project[]>('/api/projects');
}

export function getProject(id: string): Promise<Project> {
  return request<Project>(`/api/projects/${id}`);
}

export function createProject(name: string, product_type: string, material_type: string = 'wood'): Promise<Project> {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name, product_type, material_type }),
  });
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`/api/projects/${id}`, { method: 'DELETE', headers: authHeaders() });
  if (!res.ok && res.status !== 404) {
    throw new Error(`${res.status}: ${await res.text()}`);
  }
}

export function updateProject(id: string, data: Partial<Pick<Project, 'name' | 'product_type' | 'material_type' | 'door_style' | 'corner_style' | 'style_notes' | 'gemini_model' | 'selected_swatches'>>): Promise<Project> {
  return request<Project>(`/api/projects/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function uploadDoorImage(id: string, file: File): Promise<Project> {
  const form = new FormData();
  form.append('file', file);
  return request<Project>(`/api/projects/${id}/upload`, {
    method: 'POST',
    body: form,
  });
}

export function learnStyle(id: string, learnInMaple: boolean = false): Promise<Project> {
  const params = learnInMaple ? '?learn_in_maple=true' : '';
  return request<Project>(`/api/projects/${id}/learn${params}`, { method: 'POST' });
}

export function startGeneration(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/projects/${id}/generate`, { method: 'POST' });
}

export function getGenerationStatus(id: string): Promise<GenerationStatus> {
  return request<GenerationStatus>(`/api/projects/${id}/generate/status`);
}

export function resetGeneration(id: string): Promise<GenerationStatus> {
  return request<GenerationStatus>(`/api/projects/${id}/generate/reset`, { method: 'POST' });
}

export function retryVariation(id: string, idx: number): Promise<GenerationStatus> {
  return request<GenerationStatus>(`/api/projects/${id}/results/${idx}/retry`, { method: 'POST' });
}

export async function discardResult(id: string, idx: number): Promise<void> {
  const res = await fetch(`/api/projects/${id}/results/${idx}`, { method: 'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

export async function getResultsZip(
  id: string,
  watermark: boolean = true,
  watermarkOffset: number = 0,
  imageScale: number = 1.0,
): Promise<Blob> {
  const res = await fetch(
    `/api/projects/${id}/results/zip?watermark=${watermark}&watermark_offset=${watermarkOffset}&image_scale=${imageScale}`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.blob();
}

export async function saveResultsToFolder(
  id: string,
  watermark: boolean = true,
  watermarkOffset: number = 0,
  imageScale: number = 1.0,
): Promise<{ saved_to: string; files: string[] }> {
  return request<{ saved_to: string; files: string[] }>(
    `/api/projects/${id}/results/save?watermark=${watermark}&watermark_offset=${watermarkOffset}&image_scale=${imageScale}`,
    { method: 'POST' },
  );
}

export function importResultsFromFolder(id: string, folder: string): Promise<{ imported: number; wood_names: string[] }> {
  return request<{ imported: number; wood_names: string[] }>(
    `/api/projects/${id}/results/import?folder=${encodeURIComponent(folder)}`,
    { method: 'POST' },
  );
}

// Versions
export function listVersions(id: string): Promise<SignatureVersion[]> {
  return request<SignatureVersion[]>(`/api/projects/${id}/versions`);
}

export function restoreVersion(id: string, version: number): Promise<Project> {
  return request<Project>(`/api/projects/${id}/versions/${version}/restore`, { method: 'POST' });
}

// Swatches & Styles
export function listSwatches(material: string = 'wood'): Promise<Swatch[]> {
  return request<Swatch[]>(`/api/swatches?material=${material}`);
}

export function listStyles(material: string = 'wood'): Promise<Style[]> {
  return request<Style[]>(`/api/styles?material=${material}`);
}
