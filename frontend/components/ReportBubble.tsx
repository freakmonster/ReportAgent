'use client';

import { OutputToolbar } from '@/components/OutputToolbar';
import { ReportContent } from '@/components/ReportContent';
import type { ReportEntry } from '@/stores/workflowStore';
import { REPORT_TYPE_LABELS } from '@/types/api';
import { useState } from 'react';

interface Props {
  entry: ReportEntry;
  index: number;
  defaultCollapsed?: boolean;
}

function getReportLabel(reportType: string): string {
  if (reportType === 'qa') return '问答';
  if (reportType === 'auto' || !reportType) return '自动识别';
  return (REPORT_TYPE_LABELS as Record<string, string>)[reportType] || reportType;
}

export function ReportBubble({ entry, index, defaultCollapsed = true }: Props) {
  const isQA = entry.type === 'qa';
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm">
      {/* 顶部信息栏 */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        <span className="text-xs font-bold text-gray-400 dark:text-gray-500">
          #{index + 1}
        </span>
        {isQA ? (
          <span className="text-xs px-2 py-0.5 rounded bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300">
            问答
          </span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">
            {getReportLabel(entry.reportType)}
          </span>
        )}
        <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
          耗时 {entry.elapsed.toFixed(1)}s
        </span>
      </div>

      {/* 查询引用 */}
      <div className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 italic border-b border-gray-100 dark:border-gray-800">
        &ldquo;{entry.query}&rdquo;
      </div>

      {/* 内容区  可折叠 */}
      <div className="px-4 py-3">
        <div className="relative">
          {/* 内容 */}
          <div className={collapsed ? 'max-h-28 overflow-hidden' : ''}>
            <ReportContent content={entry.report} />
          </div>

          {/* 折叠时：渐变遮罩 + 展开按钮 */}
          {collapsed && (
            <div className="absolute bottom-0 left-0 right-0">
              {/* 渐变遮罩 */}
              <div className="h-12 bg-gradient-to-t from-white dark:from-gray-900 to-transparent" />
              {/* 展开按钮 */}
              <div className="flex justify-center bg-white dark:bg-gray-900 pb-1">
                <button
                  type="button"
                  onClick={() => setCollapsed(false)}
                  className="text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 transition"
                >
                   展开
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 展开后：收起按钮 */}
        {!collapsed && (
          <div className="flex justify-center pt-3">
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              className="text-xs text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 transition"
            >
               收起
            </button>
          </div>
        )}
      </div>

      {/* 图表渲染（仅展开且有图表数据时显示） */}
      {!collapsed && entry.charts && entry.charts.length > 0 && (
        <div className="px-4 pb-3">
          <div className="border-t border-gray-100 dark:border-gray-800 pt-3">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              数据图表
            </h3>
            <div className="space-y-4">
              {entry.charts.map((chart, i) => (
                <div key={i}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/png;base64,${chart.image_base64}`}
                    alt={chart.title || `图表 ${i + 1}`}
                    className="max-w-full h-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm"
                    loading="lazy"
                  />
                  {chart.title && (
                    <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-1">
                      {chart.title}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 操作栏 */}
      <div className="px-4 pb-3">
        <OutputToolbar report={entry.report} workflowId={entry.workflowId} />
      </div>
    </div>
  );
}