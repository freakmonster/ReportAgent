'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useSessionStore } from '@/stores/sessionStore';

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

      // 2. 选中第一个非空会话
      const nonEmptyFirst = sessions.find((s) => s.report_count > 0);
      if (nonEmptyFirst) {
        onChange(nonEmptyFirst.session_id);
      } else {
        // 全部为空 → 创建新的
        createSession('anonymous').then((id) => {
          if (id) onChange(id);
        });
      }
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
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* 会话列表 */}
      <div className="max-h-[33vh] overflow-y-auto">
        {loading ? (
          <div className="px-3 py-3 text-sm text-gray-400 dark:text-gray-500">加载中...</div>
        ) : sessions.length === 0 ? (
          <div className="px-3 py-3 text-sm text-gray-400 dark:text-gray-500">暂无会话</div>
        ) : (
          sessions.map((s) => (
            <button
              key={s.session_id}
              type="button"
              className={`w-full px-3 py-2 text-left text-sm flex items-center group transition ${
                value === s.session_id
                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
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
              <span className="ml-2 text-xs text-gray-400 dark:text-gray-500 shrink-0">
                ({s.report_count})
              </span>
              <span
                className="ml-2 text-gray-400 hover:text-red-500 dark:hover:text-red-400 opacity-0 group-hover:opacity-100 transition shrink-0 cursor-pointer"
                onClick={(e) => handleDelete(e, s.session_id)}
                title="删除会话"
              >
                ✕
              </span>
            </button>
          ))
        )}
      </div>

      {/* 分隔线 */}
      <div className="border-t border-gray-200 dark:border-gray-700" />

      {/* 新建会话按钮 */}
      <button
        type="button"
        className="w-full px-3 py-2 text-left text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition font-medium disabled:opacity-50"
        onClick={handleCreate}
        disabled={creating}
      >
        {creating ? '创建中...' : '+ 新建会话'}
      </button>

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40" onClick={() => setDeleteTarget(null)}>
          <div
            className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 mx-4 w-80"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-5 text-center">
              删除后，该对话将不可恢复
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                className="flex-1 px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                onClick={() => setDeleteTarget(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700 transition"
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
