import type { Project, Swatch, Style, GenerationStatus, SignatureVersion } from './types';

function getApiKey(): string {
  return localStorage.getItem('gemini_api_key') ?? '';
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

export function createProject(name: string, product_type: string): Promise<Project> {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name, product_type }),
  });
}

export async function deleteProject(id: string): Promise<void> {
  const apiKey = getApiKey();
  const headers: Record<string, string> = {};
  if (apiKey) headers['X-API-Key'] = apiKey;
  const res = await fetch(`/api/projects/${id}`, { method: 'DELETE', headers });
  if (!res.ok && res.status !== 404) {
    throw new Error(`${res.status}: ${await res.text()}`);
  }
}

export function updateProject(id: string, data: Partial<Pick<Project, 'name' | 'product_type' | 'door_style' | 'style_notes' | 'selected_swatches'>>): Promise<Project> {
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

export function learnStyle(id: string): Promise<Project> {
  return request<Project>(`/api/projects/${id}/learn`, { method: 'POST' });
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
  const apiKey = getApiKey();
  const headers: Record<string, string> = {};
  if (apiKey) headers['X-API-Key'] = apiKey;
  const res = await fetch(`/api/projects/${id}/results/${idx}`, { method: 'DELETE', headers });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
}

export async function getResultsZip(id: string, watermark: boolean = true): Promise<Blob> {
  const apiKey = getApiKey();
  const headers: Record<string, string> = {};
  if (apiKey) headers['X-API-Key'] = apiKey;
  const res = await fetch(`/api/projects/${id}/results/zip?watermark=${watermark}`, { headers });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.blob();
}

export async function saveResultsToFolder(
  id: string,
  watermark: boolean = true,
): Promise<{ saved_to: string; files: string[] }> {
  return request<{ saved_to: string; files: string[] }>(
    `/api/projects/${id}/results/save?watermark=${watermark}`,
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
export function listSwatches(): Promise<Swatch[]> {
  return request<Swatch[]>('/api/swatches');
}

export function listStyles(): Promise<Style[]> {
  return request<Style[]>('/api/styles');
}
