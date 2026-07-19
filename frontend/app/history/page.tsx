'use client';

import Link from 'next/link';
import { useReportStore } from '@/stores/reportStore';
import { REPORT_TYPE_LABELS } from '@/types/api';
import type { ReportType } from '@/types/api';

function typeLabel(reportType?: string): string {
  if (!reportType) return '—';
  return REPORT_TYPE_LABELS[reportType as ReportType] ?? reportType;
}

function truncate(text?: string, max = 50): string {
  if (!text) return '—';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

export default function HistoryPage() {
  const reports = useReportStore((s) => s.reports);

  const entries = Object.values(reports).sort(
    (a, b) => b.createdAt - a.createdAt,
  );

  const hasEntries = entries.length > 0;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="h-12 flex items-center px-6 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shrink-0">
        <Link
          href="/"
          className="text-sm font-bold tracking-wide text-gray-800 dark:text-gray-200 hover:text-blue-600 transition"
        >
          智能研报生成系统
        </Link>
        <span className="mx-3 text-gray-300 dark:text-gray-700">/</span>
        <span className="text-sm text-gray-500 dark:text-gray-400">历史报告</span>
      </header>

      {/* Body */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-8">
        {!hasEntries && (
          <div className="flex flex-col items-center justify-center h-64 text-gray-400 dark:text-gray-600">
            <div className="text-4xl mb-3">📭</div>
            <p className="text-sm">暂无历史报告</p>
            <p className="text-xs mt-1">生成研报后将自动保存在此处</p>
          </div>
        )}

        {hasEntries && (
          <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-800/50 text-left text-gray-500 dark:text-gray-400">
                  <th className="px-4 py-3 font-medium">查询主题</th>
                  <th className="px-4 py-3 font-medium w-28">报告类型</th>
                  <th className="px-4 py-3 font-medium w-40">生成时间</th>
                  <th className="px-4 py-3 font-medium w-20">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition"
                  >
                    <td className="px-4 py-3 text-gray-800 dark:text-gray-200">
                      {truncate(entry.query, 60)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-block px-2 py-0.5 text-xs rounded-full bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                        {typeLabel(entry.reportType)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">
                      {new Date(entry.createdAt).toLocaleString('zh-CN')}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/report/${entry.id}`}
                        className="text-blue-500 hover:underline text-xs"
                      >
                        查看
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
