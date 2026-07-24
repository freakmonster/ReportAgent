'use client';

import { useWorkflowStore } from '@/stores/workflowStore';
import { NODE_LABELS, NODE_ORDER_BY_TEMPLATE } from '@/types/api';

export function NodeProgress() {
  const nodes = useWorkflowStore(s => s.nodes);
  const reportType = useWorkflowStore(s => s.reportType);

  const nodeOrder = NODE_ORDER_BY_TEMPLATE[reportType] || NODE_ORDER_BY_TEMPLATE.deep_report;

  const runningNode = nodeOrder.find(n => nodes[n]?.status === 'running');
  const completedNodes = nodeOrder.filter(n => nodes[n]?.status === 'completed');

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm p-4">
      <h3 className="text-sm font-semibold mb-3 text-gray-600 dark:text-gray-400 uppercase tracking-wide">
        Agent 执行进度
      </h3>

      {/* 当前节点：大字 + 脉冲动画 */}
      {runningNode ? (
        <p className="text-lg font-semibold text-blue-600 dark:text-blue-400 animate-pulse mb-2">
          {NODE_LABELS[runningNode] || runningNode}中...
        </p>
      ) : (
        <p className="text-lg font-semibold text-gray-400 dark:text-gray-500 mb-2">
          执行中...
        </p>
      )}

      {/* 已完成节点面包屑 */}
      {completedNodes.length > 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          {completedNodes.map(n => (
            <span key={n} className="inline-flex items-center gap-0.5">
              <span>✅ {NODE_LABELS[n] || n}</span>
              <span className="mx-1 opacity-40">→</span>
            </span>
          ))}
          {runningNode && (
            <span className="inline-flex items-center gap-0.5 text-blue-500">
              <span>⏳ {NODE_LABELS[runningNode] || runningNode}中...</span>
            </span>
          )}
        </p>
      )}
    </div>
  );
}
