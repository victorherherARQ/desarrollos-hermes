export type WeightPoint = { date: string; value: number };
export type MetricResponse = {
  metric: string;
  period_days: number;
  points: WeightPoint[];
};
export type IngestResponse = {
  inserted: number;
  updated: number;
  skipped: number;
  total: number;
};
export type HealthResponse = {
  status: 'ok' | 'degraded';
  db: boolean;
  version: string;
};
export type CSVPreviewRow = {
  row_number: number;
  date: string | null;
  weight_kg: number | null;
  body_fat_pct: number | null;
  bmi: number | null;
  errors: string[];
};
export type CSVPreviewResponse = {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  rows: CSVPreviewRow[];
};