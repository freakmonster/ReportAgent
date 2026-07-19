'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useWorkflowStore } from '@/stores/workflowStore';
import { TaskForm } from '@/components/TaskForm';
import { NodeProgress } from '@/components/NodeProgress';
import { ReportContent } from '@/components/ReportContent';
import { CitationList } from '@/components/CitationList';
import { OutputToolbar } from '@/components/OutputToolbar';

const NAV_LINKS = [
  { href: '/', label: '工作台' },
  { href: '/history', label: '历史' },
  { href: '/dashboard', label: '运营面板' },
] as const;

export default function Home() {
  const pathname = usePathname();
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const report = useWorkflowStore((s) => s.report);
  const citations = useWorkflowStore((s) => s.citations);
  const workflowId = useWorkflowStore((s) => s.workflowId);
  const totalElapsed = useWorkflowStore((s) => s.totalElapsed);

  return (
    <div className="min-h-screen flex flex-col">
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

      {/* Body: 三栏布局 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左栏: 输入区域 */}
        <aside className="w-[380px] shrink-0 border-r border-gray-200 dark:border-gray-800 p-6 overflow-y-auto bg-gray-50/50 dark:bg-gray-950/50">
          <TaskForm />
        </aside>

        {/* 中栏: 节点进度 */}
        <aside className="w-[260px] shrink-0 border-r border-gray-200 dark:border-gray-800 p-4 overflow-y-auto">
          <NodeProgress />
        </aside>

        {/* 右栏: 报告预览 */}
        <main className="flex-1 overflow-y-auto p-6">
          {!report && !isRunning && (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-600">
              <div className="text-5xl mb-4">📄</div>
              <p className="text-sm">输入研报主题并点击&ldquo;开始生成报告&rdquo;</p>
              <p className="text-xs mt-1">实时查看 Agent 执行进度和生成的研报</p>
            </div>
          )}

          {/* 生成中骨架屏 */}
          {isRunning && !report && (
            <div className="space-y-4 animate-pulse">
              <div className="h-6 bg-gray-200 dark:bg-gray-800 rounded w-1/3" />
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-full" />
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-5/6" />
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-4/6" />
              <div className="h-6 bg-gray-200 dark:bg-gray-800 rounded w-1/4 mt-6" />
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-full" />
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-3/4" />
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-5/6" />
            </div>
          )}

          {/* 报告内容 */}
          {report && !isRunning && (
            <div>
              <ReportContent content={report} />
              <CitationList citations={citations} />
              <OutputToolbar report={report} workflowId={workflowId} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
