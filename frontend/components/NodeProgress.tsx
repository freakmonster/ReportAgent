'use client';

import { NODE_ORDER } from '@/types/api';
import { useWorkflowStore } from '@/stores/workflowStore';
import { NodeCard } from './NodeCard';

export function NodeProgress() {
  const nodes = useWorkflowStore(s => s.nodes);
  const isRunning = useWorkflowStore(s => s.isRunning);

  // 找到第一个 running 或最后一个 completed 之后的节点作为 current
  let currentIdx = -1;
  for (let i = 0; i < NODE_ORDER.length; i++) {
    const s = nodes[NODE_ORDER[i]]?.status;
    if (s === 'running') { currentIdx = i; break; }
  }
  if (currentIdx === -1) {
    for (let i = NODE_ORDER.length - 1; i >= 0; i--) {
      if (nodes[NODE_ORDER[i]]?.status === 'completed') { currentIdx = i + 1; break; }
    }
  }

  return (
    <div className="space-y-1">
      <h3 className="text-sm font-semibold mb-3 text-gray-600 dark:text-gray-400 uppercase tracking-wide">
        Agent 执行进度
      </h3>
      <div className="space-y-0.5">
        {NODE_ORDER.map((name, idx) => (
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
