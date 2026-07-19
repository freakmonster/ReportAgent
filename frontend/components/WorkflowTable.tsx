'use client';

interface WorkflowItem {
  id: string;
  query: string;
  status: string;
  model: string;
  duration: number;
  created_at: string;
}

interface WorkflowTableProps {
  items: WorkflowItem[];
  loading: boolean;
}

const STATUS_CONFIG: Record<string, { label: string; badgeClass: string }> = {
  completed: {
    label: '已完成',
    badgeClass:
      'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800',
  },
  failed: {
    label: '失败',
    badgeClass:
      'bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800',
  },
  running: {
    label: '运行中',
    badgeClass:
      'bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
  },
};

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    badgeClass:
      'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700',
  };

  return (
    <span
      className={`inline-block px-2 py-0.5 text-xs rounded-full border ${config.badgeClass}`}
    >
      {config.label}
    </span>
  );
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleString('zh-CN');
  } catch {
    return dateStr;
  }
}

function truncate(text: string, max = 40): string {
  if (!text) return '—';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      <td className="px-4 py-3">
        <div className="h-4 w-40 bg-gray-200 dark:bg-gray-700 rounded" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-12 bg-gray-200 dark:bg-gray-700 rounded" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-16 bg-gray-200 dark:bg-gray-700 rounded" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-12 bg-gray-200 dark:bg-gray-700 rounded" />
      </td>
      <td className="px-4 py-3">
        <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
      </td>
    </tr>
  );
}

export function WorkflowTable({ items, loading }: WorkflowTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800/50 text-left text-gray-500 dark:text-gray-400">
            <th className="px-4 py-3 font-medium">查询主题</th>
            <th className="px-4 py-3 font-medium w-24">状态</th>
            <th className="px-4 py-3 font-medium w-32">模型</th>
            <th className="px-4 py-3 font-medium w-20">耗时</th>
            <th className="px-4 py-3 font-medium w-40">时间</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {loading && (
            <>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </>
          )}

          {!loading && items.length === 0 && (
            <tr>
              <td
                colSpan={5}
                className="px-4 py-12 text-center text-gray-400 dark:text-gray-600"
              >
                暂无数据
              </td>
            </tr>
          )}

          {!loading &&
            items.map((item) => (
              <tr
                key={item.id}
                className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition"
              >
                <td className="px-4 py-3 text-gray-800 dark:text-gray-200">
                  {truncate(item.query, 40)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={item.status} />
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {item.model || '—'}
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                  {item.duration.toFixed(1)}s
                </td>
                <td className="px-4 py-3 text-xs text-gray-400 dark:text-gray-500">
                  {formatDate(item.created_at)}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
