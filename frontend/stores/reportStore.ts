'use client';

import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface CachedReport {
  id: string;
  query?: string;
  report: string;
  citations: string[];
  reportType?: string;
  createdAt: number;
}

function loadFromStorage(): Record<string, CachedReport> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem('reports');
    return raw ? (JSON.parse(raw) as Record<string, CachedReport>) : {};
  } catch {
    return {};
  }
}

function saveToStorage(reports: Record<string, CachedReport>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem('reports', JSON.stringify(reports));
  } catch {
    // localStorage 不可用时静默忽略
  }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface ReportState {
  reports: Record<string, CachedReport>;
  saveReport: (id: string, report: string, citations: string[], query?: string, reportType?: string) => void;
  getReport: (id: string) => CachedReport | null;
}

export const useReportStore = create<ReportState>((set, get) => ({
  reports: typeof window !== 'undefined' ? loadFromStorage() : {},

  saveReport: (id, report, citations, query?, reportType?) => {
    const updated = {
      ...get().reports,
      [id]: { id, query, report, citations, reportType, createdAt: Date.now() },
    };
    saveToStorage(updated);
    set({ reports: updated });
  },

  getReport: (id) => {
    const cached = get().reports[id];
    if (cached) return cached;
    const all = loadFromStorage();
    return all[id] ?? null;
  },
}));
