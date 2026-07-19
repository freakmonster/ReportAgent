'use client';

import type { ModelOption, NodeStatus, ReportType } from '@/types/api';
import { create } from 'zustand';
import { useReportStore } from './reportStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NodeState {
  status: NodeStatus;
  durationMs: number;
}

interface WorkflowState {
  // --- 表单 ---
  query: string;
  reportType: ReportType;
  model: ModelOption;
  sessionId: string;
  error: string | null;

  // --- 运行状态 ---
  isRunning: boolean;
  workflowId: string | null;

  // --- 节点进度 ---
  nodes: Record<string, NodeState>;

  // --- 结果 ---
  report: string;
  citations: string[];
  totalElapsed: number;

  // --- 动作 ---
  setForm: (partial: Partial<Pick<WorkflowState, 'query' | 'reportType' | 'model' | 'sessionId'>>) => void;
  startWorkflow: () => Promise<void>;
  updateNode: (nodeName: string, status: NodeStatus, durationMs: number) => void;
  setRunning: (running: boolean) => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** 解析一条完整的 SSE 事件块（以 \n\n 分隔）
 *  后端 sse_starlette 的 EventSourceResponse 将事件包装为：
 *    data: {"event":"progress","node":"xxx","data":{...},"timestamp":"..."}
 *  同时兼容标准 SSE 格式：
 *    event: progress
 *    data: {...}
 */
function parseSSEBlock(block: string): { event: string; data: string } | null {
  const lines = block.split('\n');
  let eventType = '';
  let dataStr = '';

  for (const line of lines) {
    if (line.startsWith('event: ')) {
      eventType = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      dataStr = line.slice(6).trim();
    }
  }

  // 标准格式：event + data 同时存在
  if (eventType && dataStr) return { event: eventType, data: dataStr };

  // 只有 data 行时，尝试从 JSON 中提取 event 字段（后端 sse_starlette 格式）
  if (!eventType && dataStr) {
    try {
      const parsed = JSON.parse(dataStr);
      if (parsed.event) {
        // 后端格式：{ event, data, node, timestamp }
        // progress: { event:"progress", node:"data_collector", data:{status:"completed"} }
        // complete:  { event:"complete",  node:"done",         data:{workflow_id,report,...} }
        // error:     { event:"error",     node:"error",        data:{message:"..."} }
        const payload: Record<string, unknown> = { ...(parsed.data ?? {}) };
        // 把外层的 node 字段合并进 payload（progress 事件需要 payload.node）
        if (parsed.node) payload.node = parsed.node;
        return { event: parsed.event, data: JSON.stringify(payload) };
      }
    } catch {
      // 非 JSON data，忽略
    }
  }

  return null;
}

/** 处理单个已解析的 SSE 事件块，更新 store 状态 */
function processSSEPart(
  part: string,
  get: () => WorkflowState,
  set: (partial: Partial<WorkflowState> | ((state: WorkflowState) => Partial<WorkflowState>)) => void,
): void {
  const parsed = parseSSEBlock(part);
  if (!parsed) { console.log('[SSE] parse failed | part=', part.slice(0, 80)); return; }

  console.log('[SSE] parsed event | type=', parsed.event);

  try {
    const payload = JSON.parse(parsed.data);

    if (parsed.event === 'progress') {
      const nodeName: string = payload.node || '';
      console.log('[SSE] progress | node=', nodeName, '| payload=', payload);
      const status: NodeStatus = payload.status === 'completed' ? 'completed'
        : payload.status === 'error' ? 'error'
        : 'completed';
      const durationMs: number = typeof payload.duration_ms === 'number' ? payload.duration_ms : 0;
      get().updateNode(nodeName, status, durationMs);

      // 标记下一个节点为 running（如果还没完成）
      const allNodeNames = Object.keys(get().nodes);
      const currentIdx = allNodeNames.indexOf(nodeName);
      if (currentIdx >= 0 && currentIdx < allNodeNames.length - 1) {
        const nextName = allNodeNames[currentIdx + 1];
        const nextState = get().nodes[nextName];
        if (nextState && nextState.status === 'idle') {
          get().updateNode(nextName, 'running', 0);
        }
      }
    } else if (parsed.event === 'complete') {
      console.log('[SSE] complete | payload keys=', Object.keys(payload));
      const workflowId: string = payload.workflow_id || '';
      const report: string = payload.report || '';
      const citations: string[] = Array.isArray(payload.citations) ? payload.citations : [];
      const elapsed: number = typeof payload.elapsed_seconds === 'number' ? payload.elapsed_seconds : 0;

      set({
        report,
        citations,
        totalElapsed: elapsed,
        workflowId,
        isRunning: false,
      });

      if (workflowId) {
        useReportStore.getState().saveReport(workflowId, report, citations, get().query, get().reportType);
      }
    }
  } catch {
    console.warn('[SSE] 无法解析事件数据:', parsed.data.slice(0, 100));
  }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  // --- 初始值 ---
  query: '',
  reportType: 'deep_report',
  model: 'deepseek-flash',
  sessionId: '',
  error: null,

  isRunning: false,
  workflowId: null,

  nodes: {},

  report: '',
  citations: [],
  totalElapsed: 0,

  // --- 表单更新 ---
  setForm: (partial) => set(partial),

  // --- 发起工作流 + SSE 监听 ---
  startWorkflow: async () => {
    const { query, reportType, model, sessionId } = get();
    if (!query.trim()) {
      set({ error: '请输入研报主题' });
      return;
    }

    // 重置状态
    set({
      isRunning: true,
      error: null,
      nodes: {},
      report: '',
      citations: [],
      totalElapsed: 0,
      workflowId: null,
    });

    // 标记已有节点为 idle（避免 NodeProgress 初始空白）
    const initNodes: Record<string, NodeState> = {};
    ['intent_classifier', 'research_planner', 'data_collector', 'data_processor', 'data_analyst', 'writer', 'editor', 'reviewer', 'publisher'].forEach((name) => {
      initNodes[name] = { status: 'idle', durationMs: 0 };
    });
    set({ nodes: initNodes });

    try {
      const body: Record<string, unknown> = {
        query,
        report_type: reportType,
        model,
        user_id: 'anonymous',
      };
      if (sessionId) body.session_id = sessionId;

      // 直连后端，绕过 Next.js 代理缓冲（Next.js 会缓冲所有 SSE 流）
      const backendBase = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8010';
      const response = await fetch(`${backendBase}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      console.log('[SSE] fetch response | ok=', response.ok, '| status=', response.status);

      if (!response.ok) {
        const errText = await response.text().catch(() => '');
        throw new Error(`HTTP ${response.status}: ${errText || response.statusText}`);
      }

      const reader = response.body?.getReader();
      console.log('[SSE] reader ready | hasReader=', !!reader);
      if (!reader) {
        throw new Error('Response body is not readable');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('[SSE] stream done | buffer_remaining=', buffer.length, 'bytes');
          // 处理剩余 buffer 中可能存在的完整 SSE 块
          if (buffer.trim()) {
            const remainingParts = buffer.split('\n\n');
            for (const part of remainingParts) {
              const trimmed = part.trim();
              if (!trimmed) continue;
              processSSEPart(trimmed, get, set);
            }
          }
          break;
        }

        // 原始数据块日志
        const chunk = decoder.decode(value, { stream: true });
        console.log('[SSE] raw chunk | size=', value?.length, '| preview=', chunk.slice(0, 100).replace(/\n/g, '\\n'));
        buffer += chunk;

        // 按 \n\n 分割 SSE 事件块
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const trimmed = part.trim();
          if (!trimmed) continue;
          processSSEPart(trimmed, get, set);
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      set({
        error: msg,
        isRunning: false,
      });
      console.error('[SSE] 连接失败:', err);
    }
  },

  // --- 更新节点状态 ---
  updateNode: (nodeName, status, durationMs) =>
    set((state) => ({
      nodes: {
        ...state.nodes,
        [nodeName]: { status, durationMs },
      },
    })),

  setRunning: (running) => set({ isRunning: running }),

  // --- 重置 ---
  reset: () =>
    set({
      nodes: {},
      isRunning: false,
      error: null,
      query: '',
      reportType: 'deep_report',
      model: 'deepseek-flash',
      sessionId: '',
      workflowId: null,
      report: '',
      citations: [],
      totalElapsed: 0,
    }),
}));
