'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { useWorkflowStore } from '@/stores/workflowStore';
import { TaskForm } from '@/components/TaskForm';
import { NodeProgress } from '@/components/NodeProgress';
import { ReportBubble } from '@/components/ReportBubble';

const NAV_LINKS = [
  { href: '/', label: '工作台' },
  { href: '/history', label: '历史' },
  { href: '/dashboard', label: '运营面板' },
] as const;

export default function Home() {
  const pathname = usePathname();
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const report = useWorkflowStore((s) => s.report);
  const sessionId = useWorkflowStore((s) => s.sessionId);
  const totalElapsed = useWorkflowStore((s) => s.totalElapsed);
  const reportHistory = useWorkflowStore((s) => s.reportHistory);
  const detectedTemplate = useWorkflowStore((s) => s.detectedTemplate);
  const loadSessionHistory = useWorkflowStore((s) => s.loadSessionHistory);

  // --- 自动滚动到右栏底部 ---
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [reportHistory.length, isRunning]);

  // --- 切换会话时加载历史 ---
  const prevSessionRef = useRef(sessionId);
  useEffect(() => {
    if (sessionId && sessionId !== prevSessionRef.current) {
      loadSessionHistory(sessionId);
      prevSessionRef.current = sessionId;
    }
  }, [sessionId, loadSessionHistory]);

  // --- 页面首次加载时加载当前会话历史 ---
  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (sessionId && !initialLoadDone.current) {
      loadSessionHistory(sessionId);
      initialLoadDone.current = true;
    }
  }, [sessionId, loadSessionHistory]);

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-12 flex items-center px-6 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shrink-0">
        <h1 className="text-sm font-bold tracking-wide text-gray-800 dark:text-gray-200">
          智能研报生成系统
        </h1>
        <nav className="ml-6 flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  isActive
                    ? 'font-bold text-gray-800 dark:text-gray-200'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
          {isRunning && (
            <span className="flex items-center gap-1.5 text-blue-500">
              <span className="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
              生成中
            </span>
          )}
          {totalElapsed > 0 && !isRunning && (
            <span>总耗时 {totalElapsed.toFixed(1)}s</span>
          )}
        </div>
      </header>

      {/* Body: 两栏布局 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左栏: 输入区域 */}
        <aside className="w-[380px] shrink-0 border-r border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-950/50 flex flex-col overflow-hidden">
          <TaskForm />
        </aside>

        {/* 右栏: 报告预览 */}
        <main className="flex-1 overflow-y-auto p-6">
          {/* 空闲状态 */}
          {!report && !isRunning && reportHistory.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-600">
              <div className="text-5xl mb-4">📄</div>
              <p className="text-sm">在左侧输入研报主题并点击发送</p>
              <p className="text-xs mt-1">实时查看 Agent 执行进度和生成的研报</p>
            </div>
          )}

          {/* 历史气泡列表 */}
          {reportHistory.length > 0 && (
            <div className="space-y-4">
              {reportHistory.map((entry, i) => (
                <ReportBubble key={entry.workflowId || i} entry={entry} index={i} defaultCollapsed={i < reportHistory.length - 1} />
              ))}
            </div>
          )}

          {/* 非 QA 执行中：显示 Agent 执行进度 */}
          {isRunning && detectedTemplate !== 'qa' && (
            <NodeProgress />
          )}

          {/* 哨兵元素：用于自动滚动到最底部 */}
          <div ref={bottomRef} />
        </main>
      </div>
    </div>
  );
}
