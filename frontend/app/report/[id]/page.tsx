'use client';

import { useParams } from 'next/navigation';
import { useReportStore } from '@/stores/reportStore';
import { ReportContent } from '@/components/ReportContent';
import { CitationList } from '@/components/CitationList';
import { OutputToolbar } from '@/components/OutputToolbar';
import Link from 'next/link';

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const report = useReportStore((s) => s.getReport(id));

  if (!report) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-gray-400 dark:text-gray-600">
        <p className="text-lg mb-2">报告未找到</p>
        <p className="text-sm mb-6">该报告可能已被清除或链接无效</p>
        <Link
          href="/"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition"
        >
          返回首页
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="h-12 flex items-center px-6 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shrink-0">
        <Link href="/" className="text-sm font-bold tracking-wide text-gray-800 dark:text-gray-200 hover:text-blue-600 transition">
          智能研报生成系统
        </Link>
        <span className="mx-3 text-gray-300 dark:text-gray-700">/</span>
        <span className="text-sm text-gray-500 dark:text-gray-400 truncate max-w-md">
          {id}
        </span>
        <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
          {new Date(report.createdAt).toLocaleString('zh-CN')}
        </span>
      </header>

      {/* Body */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-8">
        <ReportContent content={report.report} />
        <CitationList citations={report.citations} />
        <OutputToolbar report={report.report} workflowId={report.id} />

        <div className="mt-8 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Link
            href="/"
            className="text-sm text-blue-500 hover:underline"
          >
            ← 返回工作台
          </Link>
        </div>
      </main>
    </div>
  );
}
