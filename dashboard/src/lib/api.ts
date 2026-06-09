// API client for the Store Intelligence API. T-31.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function getMetrics(storeId: string, forDate?: string) {
  const q = forDate ? `?for_date=${forDate}` : "";
  return apiFetch(`/stores/${storeId}/metrics${q}`);
}

export async function getFunnel(storeId: string, forDate?: string) {
  const q = forDate ? `?for_date=${forDate}` : "";
  return apiFetch(`/stores/${storeId}/funnel${q}`);
}

export async function getHeatmap(storeId: string, forDate?: string) {
  const q = forDate ? `?for_date=${forDate}` : "";
  return apiFetch(`/stores/${storeId}/heatmap${q}`);
}

export async function getAnomalies(storeId: string) {
  return apiFetch(`/stores/${storeId}/anomalies`);
}

export async function getHealth() {
  return apiFetch(`/health`);
}
