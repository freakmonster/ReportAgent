'use client';

import { SessionSelect } from '@/components/SessionSelect';
import { useWorkflowStore } from '@/stores/workflowStore';
import type { ModelOption, ReportType } from '@/types/api';
import { MODEL_LABELS } from '@/types/api';
import { useCallback, useRef, useState } from 'react';

const MODELS: ModelOption[] = ['deepseek-flash', 'deepseek-pro', 'qwen-8b', 'qwen-32b', 'qwen-max'];

const MODEL_COLORS: Record<ModelOption, { ring: string; bg: string; text: string }> = {
  'deepseek-flash': { ring: 'ring-blue-400/50', bg: 'bg-blue-500/15', text: 'text-blue-300' },
  'deepseek-pro':   { ring: 'ring-purple-400/50', bg: 'bg-purple-500/15', text: 'text-purple-300' },
  'qwen-8b':        { ring: 'ring-cyan-400/50', bg: 'bg-cyan-500/15', text: 'text-cyan-300' },
  'qwen-32b':       { ring: 'ring-emerald-400/50', bg: 'bg-emerald-500/15', text: 'text-emerald-300' },
  'qwen-max':       { ring: 'ring-amber-400/50', bg: 'bg-amber-500/15', text: 'text-amber-300' },
};

export function TaskForm() {
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const error = useWorkflowStore((s) => s.error);
  const setForm = useWorkflowStore((s) => s.setForm);
  const startWorkflow = useWorkflowStore((s) => s.startWorkflow);

  const [query, setQuery] = useState('');
  const [model, setModel] = useState<ModelOption>('deepseek-flash');
  const [sessionId, setSessionId] = useState('');
  const [hintOpen, setHintOpen] = useState(false);

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
          <label className="block text-xs font-semibold mb-2 text-slate-300 uppercase tracking-wider">
            会话列表
          </label>
          <SessionSelect value={sessionId} onChange={handleSessionChange} disabled={isRunning} />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="px-3 py-2 bg-red-900/40 border border-red-700/40 rounded-xl text-sm text-red-300">
            {error}
          </div>
        )}
      </div>

      {/* ── 下半部分：固定输入栏 ── */}
      <div className="shrink-0 border-t border-slate-600/40 px-5 py-4 space-y-3">
        {/* 模型选择 — 彩色标签按钮 */}
        <div>
          <div className="flex flex-wrap gap-1.5">
            {MODELS.map((m) => {
              const isSelected = model === m;
              const c = MODEL_COLORS[m];
              return (
                <button
                  key={m}
                  type="button"
                  disabled={isRunning}
                  onClick={() => setModel(m)}
                  className={`text-[11px] px-2.5 py-1 rounded-full font-medium transition-all duration-300 ease-out
                    border border-transparent
                    ${isSelected
                      ? `${c.bg} ${c.text} ${c.ring} ring-1 tag-glow-selected`
                      : 'text-slate-400 bg-slate-700/40 hover:text-slate-200 hover:bg-slate-700'
                    }
                    ${isRunning ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  {MODEL_LABELS[m]}
                </button>
              );
            })}
          </div>
        </div>

        {/* textarea + 发送按钮 */}
        <div className="flex items-end gap-2">
          <textarea
            className="flex-1 h-17 px-4 py-2.5 border border-slate-600/60 rounded-2xl resize-none
              bg-slate-700/60 text-slate-200 placeholder-slate-400 text-sm
              focus:outline-none focus:border-blue-500/50 focus:ring-0
              input-glow disabled:opacity-40 transition-all duration-300"
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
            className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-blue-500 to-cyan-400
              text-white flex items-center justify-center
              hover:scale-110 active:scale-95 transition-all duration-300 ease-out
              disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100
              shadow-lg shadow-blue-500/25"
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

        {/* 输入提示 — 可折叠小卡片 */}
        <div className={`border border-slate-600/30 rounded-xl overflow-hidden transition-all duration-300 ${hintOpen ? 'bg-slate-700/40' : 'bg-slate-700/20'}`}>
          <button
            type="button"
            onClick={() => setHintOpen(!hintOpen)}
            className="w-full flex items-center justify-between px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            <span>不知道怎么问？</span>
            <svg
              className={`w-3 h-3 transition-transform duration-300 ${hintOpen ? 'rotate-180' : ''}`}
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          {hintOpen && (
            <div className="px-3 pb-2.5 text-[11px] text-slate-400 leading-relaxed space-y-0.5 border-t border-slate-600/20 pt-2">
              <p><span className="text-slate-400">一般提问：</span>"最近黄金为什么涨"、"什么是深度学习"</p>
              <p><span className="text-blue-400">深度研报：</span>"分析腾讯的未来增长点"、"新能源汽车产业链分析"</p>
              <p><span className="text-amber-400">市场快讯：</span>"今日AI行业快讯"</p>
              <p><span className="text-emerald-400">财报分析：</span>"分析腾讯Q4财报"</p>
            </div>
          )}
        </div>
      </div>
    </form>
  );
}
