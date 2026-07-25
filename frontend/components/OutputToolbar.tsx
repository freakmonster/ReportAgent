'use client';

import { useState } from 'react';

interface Props {
  report: string;
  workflowId: string | null;
  query: string;
}

export function OutputToolbar({ report, workflowId, query }: Props) {
  const [copied, setCopied] = useState(false);

  const handleExportMd = () => {
    const blob = new Blob([report], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const filename = query ? `${query}.md` : workflowId ? `${workflowId}.md` : 'report.md';
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = report;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex gap-2 mt-4 items-center">
      <button
        onClick={handleExportMd}
        className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition"
      >
        📥 导出 Markdown
      </button>
      <button
        onClick={handleCopy}
        className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition"
      >
        📋 复制
      </button>
      {copied && (
        <span className="text-xs text-green-600 dark:text-green-400 animate-pulse">
          复制成功
        </span>
      )}
    </div>
  );
}
