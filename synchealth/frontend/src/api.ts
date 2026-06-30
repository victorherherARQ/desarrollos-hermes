import type {
  CSVPreviewResponse,
  HealthResponse,
  IngestResponse,
  MetricResponse,
} from './types';

const API_BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postForm<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    throw new Error(`POST ${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health(): Promise<HealthResponse> {
    return get<HealthResponse>('/health');
  },
  metricsWeight(days: number): Promise<MetricResponse> {
    return get<MetricResponse>(`/metrics/weight?days=${days}`);
  },
  metricsBodyFat(days: number): Promise<MetricResponse> {
    return get<MetricResponse>(`/metrics/body_fat?days=${days}`);
  },
  metricsRestingHr(days: number): Promise<MetricResponse> {
    return get<MetricResponse>(`/metrics/resting_hr?days=${days}`);
  },
  metricsSleep(days: number): Promise<MetricResponse> {
    return get<MetricResponse>(`/metrics/sleep?days=${days}`);
  },
  metricsSteps(days: number): Promise<MetricResponse> {
    return get<MetricResponse>(`/metrics/steps?days=${days}`);
  },
  ingestWeight(rows: unknown[], source = 'manual'): Promise<IngestResponse> {
    return postJson<IngestResponse>('/ingest/weight', { rows, source });
  },
  ingestCsv(file: File): Promise<IngestResponse> {
    return postForm<IngestResponse>('/ingest/csv', file);
  },
  previewCsv(file: File): Promise<CSVPreviewResponse> {
    return postForm<CSVPreviewResponse>('/ingest/preview-csv', file);
  },
};