'use client';

import { SessionSelect } from '@/components/SessionSelect';
import { useWorkflowStore } from '@/stores/workflowStore';
import type { ModelOption, ReportType } from '@/types/api';
import { MODEL_LABELS } from '@/types/api';
import { useCallback, useRef, useState } from 'react';

const MODELS: ModelOption[] = ['deepseek-flash', 'deepseek-pro', 'qwen-8b', 'qwen-32b', 'qwen-max'];

export function TaskForm() {
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const error = useWorkflowStore((s) => s.error);
  const setForm = useWorkflowStore((s) => s.setForm);
  const startWorkflow = useWorkflowStore((s) => s.startWorkflow);

  const [query, setQuery] = useState('');
  const [selectFocused, setSelectFocused] = useState(false);
  const [model, setModel] = useState<ModelOption>('deepseek-flash');
  const [sessionId, setSessionId] = useState('');

  const handleSessionChange = useCallback((id: string) => {
    setSessionId(id);
    useWorkflowStore.setState({ sessionId: id });
  }, []);

  const isComposing = useRef(false);

  const handleTextChange = useCallback((value: string) => {
    if (!isComposing.current) {
      setQuery(value);
    }
  }, []);

  const handleCompositionEnd = useCallback(
    (e: React.CompositionEvent<HTMLTextAreaElement>) => {
      isComposing.current = false;
      const value = (e.target as HTMLTextAreaElement).value;
      setQuery(value);
    },
    [],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setForm({ query, reportType: '' as ReportType, model, sessionId });
    await startWorkflow();
  };

  const canSubmit = !isRunning && query.trim().length > 0 && sessionId.length > 0;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col h-full">
      {/* ── 上半部分：可滚动配置区 ── */}
      <div className="flex-1 overflow-y-auto p-6 pb-0 space-y-5">
        {/* 关联会话 */}
        <div>
          <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
            会话列表
          </label>
          <SessionSelect value={sessionId} onChange={handleSessionChange} disabled={isRunning} />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="px-3 py-2 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}
      </div>

      {/* ── 下半部分：固定输入栏 ── */}
      <div className="shrink-0 border-t border-gray-200 dark:border-gray-700 px-6 py-3 space-y-2">
        {/* AI 模型 — 融入输入栏顶部 */}
        <div className="relative">
          <select
            className="w-full px-3 py-1.5 text-xs border rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 bg-gray-50 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300 text-gray-500 disabled:opacity-50 appearance-none pr-7"
            value={model}
            onClick={() => setSelectFocused((prev) => !prev)}
            onChange={(e) => setModel(e.target.value as ModelOption)}
            disabled={isRunning}
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>
                {MODEL_LABELS[m]}
              </option>
            ))}
          </select>
          {/* 箭头：焦点时向上，失焦时向下 */}
          <svg
            className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points={selectFocused ? '18 15 12 9 6 15' : '18 9 12 15 6 9'} />
          </svg>
        </div>

        {/* textarea + 发送按钮 */}
        <div className="flex items-end gap-2">
        <textarea
          className="flex-1 h-17 px-3 py-2 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white disabled:opacity-50 text-sm"
          placeholder="输入..."
          value={query}
          onChange={(e) => handleTextChange(e.target.value)}
          onCompositionStart={() => { isComposing.current = true; }}
          onCompositionEnd={handleCompositionEnd}
          disabled={isRunning}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && canSubmit) {
              e.preventDefault();
              handleSubmit(e as unknown as React.FormEvent);
            }
          }}
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="w-10 h-10 shrink-0 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
          title="发送"
        >
          {isRunning ? (
            <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          )}
        </button>
        </div>

        {/* 输入提示 */}
        <p className="text-xs text-gray-400 dark:text-gray-500 leading-relaxed">
          试试这样说：<br />
          一般提问："最近黄金为什么涨"、"什么是深度学习"<br />
          深度研报："分析腾讯的未来增长点"、"新能源汽车产业链分析"<br />
          市场快讯："今日AI行业快讯"<br />
          财报分析："分析腾讯Q4财报"
        </p>
      </div>
    </form>
  );
}
