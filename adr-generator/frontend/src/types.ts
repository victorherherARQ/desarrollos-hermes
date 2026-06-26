export interface AdrRequest {
  title: string;
  context: string;
  technologies: string[];
  preliminary_decision: string;
  options_to_evaluate?: string[];
  status?: 'proposed' | 'accepted' | 'rejected' | 'deprecated' | 'superseded';
  deciders?: string[];
  date?: string;
}

export interface AdrResponse {
  adr_number: number;
  filename: string;
  content: string;
  branch: string;
  commit_sha: string | null;
  pr_url: string | null;
}

export interface HealthResponse {
  status: string;
  model: string;
  github_enabled: boolean;
}

export interface AdrListItem {
  number: number;
  filename: string;
  status?: string | null;
  title?: string | null;
}

export interface AdrListResponse {
  adrs: AdrListItem[];
}