'use client';

import { useState, useRef, useCallback } from 'react';
import { useWorkflowStore } from '@/stores/workflowStore';
import { MODEL_LABELS, REPORT_TYPE_LABELS } from '@/types/api';
import type { ModelOption, ReportType } from '@/types/api';
import { SessionSelect } from '@/components/SessionSelect';

const MODELS: ModelOption[] = ['deepseek-flash', 'deepseek-pro', 'qwen-8b', 'qwen-32b', 'qwen-max'];
const REPORT_TYPES: ReportType[] = ['deep_report', 'flash_news', 'earnings_analysis'];

export function TaskForm() {
  // --- 从 store 读取运行状态（这些仍需 store 驱动） ---
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const error = useWorkflowStore((s) => s.error);
  const setForm = useWorkflowStore((s) => s.setForm);
  const startWorkflow = useWorkflowStore((s) => s.startWorkflow);
  const reset = useWorkflowStore((s) => s.reset);

  // --- 本地 state：避免 IME 组合事件与 store 订阅冲突 ---
  const [query, setQuery] = useState('');
  const [reportType, setReportType] = useState<ReportType>('deep_report');
  const [model, setModel] = useState<ModelOption>('deepseek-flash');
  const [sessionId, setSessionId] = useState('');

  // --- IME 组合输入追踪 ---
  const isComposing = useRef(false);

  const handleTextChange = useCallback((value: string) => {
    if (!isComposing.current) {
      setQuery(value);
    }
  }, []);

  const handleCompositionEnd = useCallback(
    (e: React.CompositionEvent<HTMLTextAreaElement>) => {
      isComposing.current = false;
      // 组合结束后手动更新为最终值
      const value = (e.target as HTMLTextAreaElement).value;
      setQuery(value);
    },
    [],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    // 提交时同步本地 state 到 store
    setForm({ query, reportType, model, sessionId });
    await startWorkflow();
  };

  const handleReset = () => {
    reset();
    setQuery('');
    setReportType('deep_report');
    setModel('deepseek-flash');
    setSessionId('');
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* 研报主题 */}
      <div>
        <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
          研报主题
        </label>
        <textarea
          className="w-full h-32 px-3 py-2 border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white disabled:opacity-50"
          placeholder="输入研报主题，例如：2026年7月AI行业重要动态"
          value={query}
          onChange={(e) => handleTextChange(e.target.value)}
          onCompositionStart={() => { isComposing.current = true; }}
          onCompositionEnd={handleCompositionEnd}
          disabled={isRunning}
        />
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

      {/* 关联会话 */}
      <div>
        <label className="block text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
          关联会话
        </label>
        <SessionSelect value={sessionId} onChange={setSessionId} disabled={isRunning} />
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="px-3 py-2 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {/* 按钮 */}
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={isRunning || !query.trim()}
          className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isRunning ? '生成中...' : '开始生成报告'}
        </button>
        {!isRunning && (
          <button
            type="button"
            onClick={handleReset}
            className="px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
          >
            重置
          </button>
        )}
      </div>
    </form>
  );
}
