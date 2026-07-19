'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useSessionStore } from '@/stores/sessionStore';

interface SessionSelectProps {
  value: string;
  onChange: (sessionId: string) => void;
  disabled?: boolean;
}

export function SessionSelect({ value, onChange, disabled = false }: SessionSelectProps) {
  const { sessions, loading, loadSessions, createSession, deleteSession } = useSessionStore();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // --- 加载会话列表 ---
  useEffect(() => {
    loadSessions('anonymous');
  }, [loadSessions]);

  // --- 点击外部关闭下拉 ---
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  // --- 新建会话 ---
  const handleCreate = useCallback(async () => {
    setCreating(true);
    try {
      const id = await createSession('anonymous');
      if (id) {
        onChange(id);
      }
    } finally {
      setCreating(false);
      setOpen(false);
    }
  }, [createSession, onChange]);

  // --- 删除会话 ---
  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      if (!window.confirm('确定要删除该会话吗？')) return;
      await deleteSession(id);
      if (value === id) {
        onChange('');
      }
    },
    [deleteSession, value, onChange],
  );

  // --- 当前选中的会话标题 ---
  const selectedSession = sessions.find((s) => s.id === value);

  return (
    <div ref={containerRef} className="relative">
      {/* 触发器 */}
      <button
        type="button"
        className={`w-full px-3 py-2 border rounded-lg text-left flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white disabled:opacity-50 ${
          disabled ? 'cursor-not-allowed' : 'cursor-pointer'
        }`}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
      >
        <span className={selectedSession ? '' : 'text-gray-400 dark:text-gray-500'}>
          {selectedSession ? selectedSession.title : '不关联会话'}
        </span>
        <svg
          className={`w-4 h-4 ml-2 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* 下拉菜单 */}
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {/* "不关联会话" 选项 */}
          <button
            type="button"
            className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition ${
              value === '' ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-300'
            }`}
            onClick={() => {
              onChange('');
              setOpen(false);
            }}
          >
            不关联会话
          </button>

          {/* 分隔线 */}
          <div className="border-t border-gray-200 dark:border-gray-700" />

          {/* 会话列表 */}
          {loading ? (
            <div className="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">加载中...</div>
          ) : sessions.length === 0 ? (
            <div className="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">暂无会话</div>
          ) : (
            sessions.map((s) => (
              <div key={s.id} className="group flex items-center">
                <button
                  type="button"
                  className={`flex-1 px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition ${
                    value === s.id ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-300'
                  }`}
                  onClick={() => {
                    onChange(s.id);
                    setOpen(false);
                  }}
                >
                  <span>{s.title}</span>
                  <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                    ({s.report_count})
                  </span>
                </button>
                {/* 删除按钮 */}
                <button
                  type="button"
                  className="px-2 py-2 text-gray-400 hover:text-red-500 dark:hover:text-red-400 opacity-0 group-hover:opacity-100 transition"
                  onClick={(e) => handleDelete(e, s.id)}
                  title="删除会话"
                >
                  ✕
                </button>
              </div>
            ))
          )}

          {/* 分隔线 */}
          <div className="border-t border-gray-200 dark:border-gray-700" />

          {/* 新建会话按钮 */}
          <button
            type="button"
            className="w-full px-3 py-2 text-left text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition font-medium disabled:opacity-50"
            onClick={handleCreate}
            disabled={creating}
          >
            {creating ? '创建中...' : '+ 新建会话'}
          </button>
        </div>
      )}
    </div>
  );
}
