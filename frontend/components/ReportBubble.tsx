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

/** Parse "## 引用来源" section, build N -> URL map */
function parseCitations(content: string): Record<string, string> {
  const map: Record<string, string> = {};
  const header = '## 引用来源';
  const idx = content.indexOf(header);
  if (idx === -1) return map;

  const section = content.slice(idx + header.length);
  const lines = section.split('\n');
  for (const line of lines) {
    const m = line.match(/\[(\d+)\]\s*(?:\[.*?\]\((.+?)\)|(https?:\/\/\S+))/);
    if (m) {
      map[m[1]] = m[2] || m[3];
    }
  }
  return map;
}

/** Gradient bar color by report type */
function getGradientBar(reportType: string): string {
  switch (reportType) {
    case 'flash_news':
      return 'bg-gradient-to-r from-amber-500 to-orange-400';
    case 'earnings_analysis':
    case 'qa':
      return 'bg-gradient-to-r from-emerald-500 to-teal-400';
    case 'deep_report':
    default:
      return 'bg-gradient-to-r from-blue-500 to-cyan-400';
  }
}

function getReportLabel(reportType: string): string {
  if (reportType === 'qa') return '问答';
  if (reportType === 'auto' || !reportType) return '自动识别';
  return (REPORT_TYPE_LABELS as Record<string, string>)[reportType] || reportType;
}

export function ReportBubble({ entry, index, defaultCollapsed = true }: Props) {
  const isQA = entry.type === 'qa';
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [reveal, setReveal] = useState(false);

  const citations = parseCitations(entry.report);
  const gradientBar = getGradientBar(entry.reportType);

  const handleExpand = () => {
    setCollapsed(false);
    setReveal(true);
  };

  const handleCollapse = () => {
    setCollapsed(true);
    setReveal(false);
  };

  const charts = entry.charts ?? [];

  return (
    <div className="rounded-2xl bg-slate-800/65 border border-slate-600/30 shadow-lg shadow-blue-500/5 overflow-hidden transition-all duration-300">
      {/* Color gradient top bar */}
      <div className={`h-0.5 ${gradientBar}`} />

      {/* Info bar */}
      <div className="flex items-center gap-3 px-5 py-3">
        <span className="text-xs font-bold text-slate-400">
          #{index + 1}
        </span>
        {isQA ? (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/20">
            问答
          </span>
        ) : (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/20">
            {getReportLabel(entry.reportType)}
          </span>
        )}
        <span className="text-xs text-slate-400 ml-auto">
          耗时 {entry.elapsed.toFixed(1)}s
        </span>
      </div>

      {/* Query */}
      <div className="px-5 pb-3 text-sm text-slate-200 italic">
        &ldquo;{entry.query}&rdquo;
      </div>

      {/* Content area - collapsible */}
      <div className="px-5 pb-3 relative">
        {/* Blue light reveal on expand */}
        {reveal && (
          <div className="animate-blue-reveal absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-400/80 to-transparent pointer-events-none" />
        )}
        <div className="relative">
          <div className={collapsed ? 'max-h-28 overflow-hidden' : ''}>
            <ReportContent content={entry.report} citations={citations} />
          </div>

          {/* Collapsed: gradient mask + expand button */}
          {collapsed && (
            <div className="absolute bottom-0 left-0 right-0">
              <div className="h-12 bg-gradient-to-t from-slate-700/60 to-transparent" />
              <div className="flex justify-center bg-slate-700/80 pb-1">
                <button
                  type="button"
                  onClick={handleExpand}
                  className="text-xs text-blue-400 hover:text-blue-300 transition"
                >
                  ︾ 展开
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Expanded: collapse button */}
        {!collapsed && (
          <div className="flex justify-center pt-3">
            <button
              type="button"
              onClick={handleCollapse}
              className="text-xs text-blue-400 hover:text-blue-300 transition"
            >
              ︽ 收起
            </button>
          </div>
        )}
      </div>

      {/* Charts (only when expanded and charts exist) */}
      {!collapsed && charts.length > 0 && (
        <div className="px-5 pb-4">
          <div className="border-t border-slate-600/30 pt-4">
            <h3 className="text-sm font-semibold text-slate-200 mb-3 text-center">
              数据图表
            </h3>
            <div className="space-y-4">
              {charts.map((chart, i) => (
                <div key={i}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/png;base64,${chart.image_base64}`}
                    alt={chart.title || `图表 ${i + 1}`}
                    className="max-w-[400px] w-full h-auto rounded-xl border border-slate-600/40 shadow-md mx-auto block bg-slate-50"
                    loading="lazy"
                  />
                  {chart.title && (
                    <p className="text-center text-xs text-slate-400 mt-1.5">
                      {chart.title}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Action bar */}
      <div className="px-5 pb-4">
        <OutputToolbar report={entry.report} workflowId={entry.workflowId} query={entry.query} />
      </div>
    </div>
  );
}
