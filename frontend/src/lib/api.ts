const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function fetchAPI<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

import type {
  DashboardResponse,
  AnalysisReport,
  ReportListItem,
} from "./types";

export async function getDashboard(): Promise<DashboardResponse> {
  return fetchAPI<DashboardResponse>("/dashboard");
}

export async function getReports(
  symbol?: string,
  limit = 20
): Promise<ReportListItem[]> {
  const params = new URLSearchParams();
  if (symbol) params.set("symbol", symbol);
  params.set("limit", String(limit));
  return fetchAPI<ReportListItem[]>(`/reports?${params}`);
}

export async function getReport(id: string): Promise<AnalysisReport> {
  return fetchAPI<AnalysisReport>(`/reports/${encodeURIComponent(id)}`);
}

export async function getLatestReport(
  symbol: string
): Promise<AnalysisReport | null> {
  return fetchAPI<AnalysisReport | null>(`/reports/latest/${symbol}`);
}

export async function triggerAnalysis(
  symbol: string
): Promise<AnalysisReport> {
  const res = await fetch(`${API_BASE}/analyze/${symbol}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Analysis failed: ${res.statusText}`);
  return res.json();
}

