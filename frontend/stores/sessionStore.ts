'use client';

import { create } from 'zustand';
import { get as apiGet, post as apiPost, del as apiDel } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Session {
  id: string;
  title: string;
  created_at: string;
  report_count: number;
}

interface SessionState {
  sessions: Session[];
  loading: boolean;
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

  loadSessions: async (userId: string) => {
    set({ loading: true });
    try {
      const data = await apiGet('/session/sessions', { user_id: userId });
      const sessions: Session[] = Array.isArray(data)
        ? data
        : Array.isArray((data as Record<string, unknown>)?.sessions)
          ? (data as Record<string, unknown>).sessions as Session[]
          : [];
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
      const id = typeof session?.id === 'string' ? session.id : null;
      if (id) {
        await get().loadSessions(userId);
      }
      return id;
    } catch (err) {
      console.error('[sessionStore] 创建会话失败:', err);
      return null;
    }
  },

  deleteSession: async (id: string) => {
    try {
      await apiDel(`/session/session/${id}`);
      // 重新加载列表（使用匿名用户作为默认 userId，或者不提供 userId 让后端处理）
      // 如果当前没有 userId 上下文，则直接从前端列表中移除
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== id),
      }));
    } catch (err) {
      console.error('[sessionStore] 删除会话失败:', err);
    }
  },
}));
