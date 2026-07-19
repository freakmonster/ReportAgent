'use client';

import { NODE_LABELS } from '@/types/api';
import type { NodeStatus } from '@/types/api';

interface Props {
  nodeName: string;
  status: NodeStatus;
  durationMs: number;
  isCurrent: boolean;
}

const STATUS_ICON: Record<NodeStatus, string> = {
  idle: '⬜',
  running: '⏳',
  completed: '✅',
  error: '❌',
};

export function NodeCard({ nodeName, status, durationMs, isCurrent }: Props) {
  const label = NODE_LABELS[nodeName] || nodeName;
  const seconds = durationMs > 0 ? (durationMs / 1000).toFixed(1) + 's' : '';

  return (
    <div
      className={
        'flex items-center gap-3 px-3 py-2 rounded-lg text-sm ' +
        (isCurrent
          ? 'bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 animate-pulse'
          : status === 'completed'
          ? 'text-green-700 dark:text-green-400'
          : status === 'error'
          ? 'text-red-600 dark:text-red-400'
          : 'text-gray-400 dark:text-gray-600')
      }
    >
      <span className="text-base w-6 text-center">{STATUS_ICON[status]}</span>
      <span className="flex-1">{label}</span>
      {seconds && <span className="text-xs tabular-nums opacity-70">{seconds}</span>}
    </div>
  );
}
