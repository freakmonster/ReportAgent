'use client';

import type { ReportEntry } from '@/stores/workflowStore';
import { REPORT_TYPE_LABELS } from '@/types/api';
import { ReportContent } from '@/components/ReportContent';
import { CitationList } from '@/components/CitationList';
import { OutputToolbar } from '@/components/OutputToolbar';

interface Props {
  entry: ReportEntry;
  index: number;
}

export function ReportBubble({ entry, index }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm">
      {/* 顶部信息栏 */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        <span className="text-xs font-bold text-gray-400 dark:text-gray-500">
          #{index + 1}
        </span>
        <span className="text-xs px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">
          {REPORT_TYPE_LABELS[entry.reportType]}
        </span>
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
          耗时 {entry.elapsed.toFixed(1)}s
        </span>
      </div>

      {/* 查询引用 */}
      <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 italic border-b border-gray-100 dark:border-gray-800">
        &ldquo;{entry.query}&rdquo;
      </div>

      {/* 报告内容 */}
      <div className="px-4 py-3">
        <ReportContent content={entry.report} />
      </div>

      {/* 引用来源 + 操作栏 */}
      <div className="px-4 pb-3">
        <CitationList citations={entry.citations} />
        <OutputToolbar report={entry.report} workflowId={entry.workflowId} />
      </div>
    </div>
  );
}
