'use client';

import { useWorkflowStore } from '@/stores/workflowStore';
import { NODE_ORDER_BY_TEMPLATE } from '@/types/api';
import { NodeCard } from './NodeCard';

export function NodeProgress() {
  const nodes = useWorkflowStore(s => s.nodes);
  const isRunning = useWorkflowStore(s => s.isRunning);
  const reportType = useWorkflowStore(s => s.reportType);

  const nodeOrder = NODE_ORDER_BY_TEMPLATE[reportType] || NODE_ORDER_BY_TEMPLATE.deep_report;

  // 找到第一个 running 或最后一个 completed 之后的节点作为 current
  let currentIdx = -1;
  for (let i = 0; i < nodeOrder.length; i++) {
    const s = nodes[nodeOrder[i]]?.status;
    if (s === 'running') { currentIdx = i; break; }
  }
  if (currentIdx === -1) {
    for (let i = nodeOrder.length - 1; i >= 0; i--) {
      if (nodes[nodeOrder[i]]?.status === 'completed') { currentIdx = i + 1; break; }
    }
  }

  return (
    <div className="space-y-1">
      <h3 className="text-sm font-semibold mb-3 text-gray-600 dark:text-gray-400 uppercase tracking-wide">
        Agent 执行进度
      </h3>
      <div className="space-y-0.5">
        {nodeOrder.map((name, idx) => (
          <NodeCard
            key={name}
            nodeName={name}
            status={nodes[name]?.status || 'idle'}
            durationMs={nodes[name]?.durationMs || 0}
            isCurrent={idx === currentIdx && isRunning}
          />
        ))}
      </div>
      {isRunning && (
        <p className="text-xs text-blue-500 mt-2 animate-pulse">执行中...</p>
      )}
    </div>
  );
}
