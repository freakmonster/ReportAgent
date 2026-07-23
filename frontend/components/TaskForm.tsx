'use client';

import { SessionSelect } from '@/components/SessionSelect';
import { useWorkflowStore } from '@/stores/workflowStore';
import type { ModelOption, ReportType } from '@/types/api';
import { MODEL_LABELS, REPORT_TYPE_LABELS } from '@/types/api';
import { useCallback, useRef, useState } from 'react';

const MODELS: ModelOption[] = ['deepseek-flash', 'deepseek-pro', 'qwen-8b', 'qwen-32b', 'qwen-max'];
const REPORT_TYPES: ReportType[] = ['deep_report', 'flash_news', 'earnings_analysis'];

export function TaskForm() {
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const error = useWorkflowStore((s) => s.error);
  const setForm = useWorkflowStore((s) => s.setForm);
  const startWorkflow = useWorkflowStore((s) => s.startWorkflow);
  const reset = useWorkflowStore((s) => s.reset);

  const [query, setQuery] = useState('');
  const [reportType, setReportType] = useState<ReportType>('deep_report');
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
    setForm({ query, reportType, model, sessionId });
    await startWorkflow();
  };

  const handleReset = () => {
    reset();
    setQuery('');
    setReportType('deep_report');
    setModel('deepseek-flash');
    // sessionId 保持不变
  };

  const canSubmit = !isRunning && query.trim().length > 0 && sessionId.length > 0;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col h-full">
      {/* ── 上半部分：可滚动配置区 ── */}
      <div className="flex-1 overflow-y-auto p-6 pb-0 space-y-5">
        {/* 关联会话 */}
        <div>
          <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
            关联会话
          </label>
          <SessionSelect value={sessionId} onChange={handleSessionChange} disabled={isRunning} />
        </div>

        {/* 报告类型 */}
        <div>
          <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
            报告类型
          </label>
          <div className="flex gap-2">
            {REPORT_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className={`px-4 py-2 rounded-lg text-sm border transition ${
                  reportType === t
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:border-blue-400'
                } disabled:opacity-50`}
                onClick={() => setReportType(t)}
                disabled={isRunning}
              >
                {REPORT_TYPE_LABELS[t]}
              </button>
            ))}
          </div>
        </div>

        {/* AI 模型 */}
        <div>
          <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
            AI 模型
          </label>
          <select
            className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white disabled:opacity-50"
            value={model}
            onChange={(e) => setModel(e.target.value as ModelOption)}
            disabled={isRunning}
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>
                {MODEL_LABELS[m]}
              </option>
            ))}
          </select>
        </div>

        {/* 错误提示 + 重置 */}
        <div className="flex items-center justify-between gap-3">
          {error ? (
            <div className="flex-1 px-3 py-2 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          ) : (
            <div />
          )}
          {!isRunning && (
            <button
              type="button"
              onClick={handleReset}
              className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400 transition shrink-0"
            >
              重置
            </button>
          )}
        </div>
      </div>

      {/* ── 下半部分：固定输入栏 ── */}
      <div className="shrink-0 border-t border-gray-200 dark:border-gray-700 px-6 py-4 flex items-end gap-2">
        <textarea
          className="flex-1 h-17 px-3 py-2 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white disabled:opacity-50 text-sm"
          placeholder="输入研报主题..."
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
    </form>
  );
}
