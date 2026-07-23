'use client';

import { create } from 'zustand';
import { get as apiGet, post as apiPost, del as apiDel } from '@/lib/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fetchWithTimeout(url: string, options: RequestInit, timeoutMs = 15000): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(url, { ...options, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Session {
  session_id: string;
  title: string;
  created_at: string;
  report_count: number;
}

interface SessionState {
  sessions: Session[];
  loading: boolean;
  userId: string;
  loadSessions: (userId: string) => Promise<void>;
  createSession: (userId: string, title?: string) => Promise<string | null>;
  deleteSession: (id: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  loading: false,
  userId: '',

  loadSessions: async (userId: string) => {
    set({ loading: true, userId });
    try {
      const data = await apiGet('/session/sessions', { user_id: userId });
      const raw: Record<string, unknown>[] = Array.isArray(data)
        ? data
        : Array.isArray((data as Record<string, unknown>)?.sessions)
          ? (data as Record<string, unknown>).sessions as Record<string, unknown>[]
          : [];
      const sessions: Session[] = raw.map((item) => ({
        session_id: typeof item.session_id === 'string' ? item.session_id : '',
        title: typeof item.title === 'string' ? item.title : '',
        created_at: typeof item.created_at === 'string' ? item.created_at : '',
        report_count: typeof item.report_count === 'number' ? item.report_count : 0,
      }));
      set({ sessions, loading: false });
    } catch (err) {
      console.error('[sessionStore] 加载会话列表失败:', err);
      set({ loading: false });
    }
  },

  createSession: async (userId: string, title?: string) => {
    try {
      const data = await apiPost('/session/create', {
        user_id: userId,
        title: title || '新会话',
      });
      const session = data as Record<string, unknown>;
      const sessionId = typeof session?.session_id === 'string' ? session.session_id : null;
      if (sessionId) {
        await get().loadSessions(userId);
      }
      return sessionId;
    } catch (err) {
      console.error('[sessionStore] 创建会话失败:', err);
      return null;
    }
  },

  deleteSession: async (id: string) => {
    const { userId } = get();
    try {
      await apiDel(`/session/session/${id}`, { user_id: userId || 'anonymous' });
      set((state) => ({
        sessions: state.sessions.filter((s) => s.session_id !== id),
      }));
    } catch (err) {
      console.error('[sessionStore] 删除会话失败:', err);
    }
  },
}));
