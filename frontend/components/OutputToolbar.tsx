'use client';

interface Props {
  report: string;
  workflowId: string | null;
}

export function OutputToolbar({ report, workflowId }: Props) {
  const handleExportMd = () => {
    const blob = new Blob([report], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = workflowId ? `${workflowId}.md` : 'report.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report);
    } catch {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = report;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
  };

  return (
    <div className="flex gap-2 mt-4">
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
    </div>
  );
}
