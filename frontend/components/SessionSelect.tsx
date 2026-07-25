'use client';

import { useSessionStore } from '@/stores/sessionStore';
import { useCallback, useEffect, useRef, useState } from 'react';

// 模块级守卫：Strict Mode unmount+remount 时不会重置
let _globalAutoCreated = false;

interface SessionSelectProps {
  value: string;
  onChange: (sessionId: string) => void;
  disabled?: boolean;
}

export function SessionSelect({ value, onChange, disabled = false }: SessionSelectProps) {
  const { sessions, loading, loadSessions, createSession, deleteSession } = useSessionStore();
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // --- 加载会话列表 ---
  const firstLoadDone = useRef(false);
  useEffect(() => {
    loadSessions('anonymous').finally(() => {
      firstLoadDone.current = true;
    });
  }, [loadSessions]);

  // --- 无会话时自动创建一个（加载完成后触发一次）---
  // --- 加载完成后：清理空会话 + 自动选中最新非空会话 ---
  useEffect(() => {
    if (!loading && firstLoadDone.current && sessions.length > 0 && !value && !_globalAutoCreated) {
      _globalAutoCreated = true;
      // 1. 清理所有空会话（fire-and-forget，不阻塞自动选中）
      const emptyIds = sessions.filter((s) => s.report_count === 0).map((s) => s.session_id);
      emptyIds.forEach((id) => { deleteSession(id); });

      // 2. 直接创建新会话
      createSession('anonymous').then((id) => {
        if (id) onChange(id);
      });
    }
  }, [loading, sessions, value, deleteSession, createSession, onChange]);

  // --- 新建会话 ---
  const handleCreate = useCallback(async () => {
    setCreating(true);
    try {
      const id = await createSession('anonymous');
      if (id) onChange(id);
    } finally {
      setCreating(false);
    }
  }, [createSession, onChange]);

  // --- 确认删除会话 ---
  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    await deleteSession(deleteTarget);
    if (value === deleteTarget) {
      const remaining = sessions.filter((s) => s.session_id !== deleteTarget);
      onChange(remaining.length > 0 ? remaining[0].session_id : '');
    }
    setDeleteTarget(null);
  }, [deleteSession, deleteTarget, value, onChange, sessions]);

  // --- 删除会话（打开确认弹窗）---
  const handleDelete = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setDeleteTarget(id);
  }, []);

  return (
    <div className="space-y-1.5">
      {/* 会话列表 */}
      <div className="max-h-[33vh] overflow-y-auto space-y-1 scrollbar-hide">
        {loading ? (
          <div className="px-3 py-3 text-sm text-slate-400">加载中...</div>
        ) : sessions.length === 0 ? (
          <div className="px-3 py-3 text-sm text-slate-400">暂无会话</div>
        ) : (
          sessions.map((s) => (
            <button
              key={s.session_id}
              type="button"
              className={`w-full px-3 py-2 text-left text-sm flex items-center group transition-all duration-300 ease-out rounded-lg border-l-2 ${
                value === s.session_id
                  ? 'bg-amber-500/8 border-l-amber-400 text-amber-200'
                  : 'bg-slate-700/30 border-l-transparent text-slate-200 hover:bg-slate-700/50 hover:border-l-slate-500'
              } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              onClick={() => {
                if (disabled) return;
                // 切换前清理旧空会话
                const oldSession = sessions.find((sess) => sess.session_id === value);
                if (oldSession && oldSession.report_count === 0) {
                  deleteSession(value);
                }
                onChange(s.session_id);
              }}
              disabled={disabled}
            >
              <span className="truncate flex-1">{s.title}</span>
              <span className="ml-2 text-xs text-slate-400 shrink-0">
                ({s.report_count})
              </span>
              <span
                className="ml-2 text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition shrink-0 cursor-pointer"
                onClick={(e) => handleDelete(e, s.session_id)}
                title="删除会话"
              >
                ✕
              </span>
            </button>
          ))
        )}
      </div>

      {/* 新建会话按钮 */}
      <button
        type="button"
        className="w-full px-3 py-2 text-left text-sm text-blue-400 hover:text-blue-300
          bg-slate-700/20 hover:bg-slate-700/40 rounded-lg transition-all duration-300
          font-medium disabled:opacity-50 disabled:cursor-not-allowed border border-dashed border-slate-600/40"
        onClick={handleCreate}
        disabled={disabled || creating}
      >
        {disabled ? '生成中...' : creating ? '创建中...' : '+ 新建会话'}
      </button>

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setDeleteTarget(null)}>
          <div
            className="bg-slate-700 border border-slate-600 rounded-xl shadow-xl p-6 mx-4 w-80"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm text-slate-200 mb-5 text-center">
              删除后，该对话将不可恢复
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                className="flex-1 px-4 py-2 rounded-lg border border-slate-500 text-sm text-slate-200 hover:bg-slate-600 transition"
                onClick={() => setDeleteTarget(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 text-white text-sm hover:bg-red-500 transition"
                onClick={handleConfirmDelete}
              >
                删除该对话
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
