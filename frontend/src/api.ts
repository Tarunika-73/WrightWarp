// Thin typed client for the WrightWarp API. All paths are same-origin.
import { useEffect, useState } from "react";

export const API = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

export async function getJSON<T>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
  const url = new URL(path.startsWith("/") ? path : `${API}/${path}`, window.location.origin);
  Object.entries(params ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    let code: string | undefined;
    try {
      const body = await res.json();
      message = body?.error?.message ?? body?.detail ?? message;
      code = body?.error?.code;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message, code);
  }
  return res.json() as Promise<T>;
}

export interface LoadState<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
}

/** Fetch on mount and whenever `deps` change. */
export function useApi<T>(path: string | null, params?: Record<string, string | number | undefined | null>, deps: unknown[] = []): LoadState<T> {
  const [state, setState] = useState<LoadState<T>>({ data: null, error: null, loading: !!path });
  const key = JSON.stringify([path, params]);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    getJSON<T>(path, params)
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, error, loading: false }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ...deps]);
  return state;
}

// ---- shared response types (subset of what the API returns)
export interface IndexPoint {
  [key: string]: string | number | undefined;
  period: string;
  start: string;
  value: number;
  n_obs?: number;
  n_items?: number;
  n_routes?: number;
  price?: number;
}

export interface IndexSeries {
  series_id: string;
  run_id: string;
  methodology: string;
  frequency: string;
  scope: string;
  scope_key: string;
  base_year: number;
  data_label: string;
  weighting_version: string;
  weighting_label: string;
  calculation_version: string;
  calculated_at: string;
  points: IndexPoint[];
}

export interface Meta {
  demo_mode: boolean;
  data_notice: string;
  base_year: number;
  booking_windows: { name: string; days: number }[];
  routes: string[];
  methodologies: { name: string; label: string; description: string; requires_weights: boolean }[];
  default_methodology: string;
  weighting: { version: string; label: string; is_official: boolean; source: string; description: string; unit: string };
  environment: string;
}
