import axios from 'axios';
import type {
  AdrListResponse,
  AdrRequest,
  AdrResponse,
  HealthResponse,
} from './types';

// In dev (Vite), leave VITE_API_URL unset and rely on the proxy.
// In docker / prod, point at the backend explicitly.
const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
});

export async function health(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health');
  return data;
}

export async function generateAdr(req: AdrRequest): Promise<AdrResponse> {
  const { data } = await client.post<AdrResponse>('/generate', req);
  return data;
}

export async function listAdrs(): Promise<AdrListResponse> {
  const { data } = await client.get<AdrListResponse>('/adrs');
  return data;
}

export { API_BASE };