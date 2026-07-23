'use client';

import type { ModelOption, NodeStatus, ReportType } from '@/types/api';
import { NODE_ORDER_BY_TEMPLATE } from '@/types/api';
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

  // --- 历史记录 ---
  reportHistory: ReportEntry[];

  // --- 动作 ---
  setForm: (partial: Partial<Pick<WorkflowState, 'query' | 'reportType' | 'model' | 'sessionId'>>) => void;
  startWorkflow: () => Promise<void>;
  updateNode: (nodeName: string, status: NodeStatus, durationMs: number) => void;
  setRunning: (running: boolean) => void;
  reset: () => void;
  loadSessionHistory: (sessionId: string) => Promise<void>;
}

export interface ReportEntry {
  query: string;
  reportType: ReportType;
  report: string;
  citations: string[];
  elapsed: number;
  workflowId: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** 解析一条完整的 SSE 事件块（以 \n\n 分隔）。
 *  后端 sse-starlette 使用 dict 格式 yield，产生标准 SSE 格式：
 *    event: progress
 *    data: {"status":"completed","node":"intent_classifier"}
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

  if (eventType && dataStr) return { event: eventType, data: dataStr };
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

      const { query, reportType, reportHistory } = get();

      set({
        report,
        citations,
        totalElapsed: elapsed,
        workflowId,
        isRunning: false,
        reportHistory: [...reportHistory, { query, reportType, report, citations, elapsed, workflowId }],
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
  reportHistory: [],

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

    // 根据报告模板动态初始化节点列表（首个节点置为 running）
    const templateNodes = NODE_ORDER_BY_TEMPLATE[reportType] || NODE_ORDER_BY_TEMPLATE.deep_report;
    const initNodes: Record<string, NodeState> = {};
    templateNodes.forEach((name, idx) => {
      initNodes[name] = { status: idx === 0 ? 'running' : 'idle', durationMs: 0 };
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
      console.log('[SSE] 正在连接后端:', `${backendBase}/chat/stream`);
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
            let remainingParts = buffer.split('\r\n\r\n');
            if (remainingParts.length === 1) remainingParts = buffer.split('\n\n');
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

        // 按 SSE 事件边界分割（sse-starlette v3 默认 \r\n 分隔符）
        // 优先 \r\n\r\n，回退到 \n\n 兼容旧格式
        let parts = buffer.split('\r\n\r\n');
        if (parts.length === 1) parts = buffer.split('\n\n');
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
      console.error('[SSE] 连接失败 (type=' + (err instanceof TypeError ? 'NETWORK' : 'HTTP') + '):', err);
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
      reportHistory: [],
    }),

  // --- 从后端加载当前会话的历史 ---
  loadSessionHistory: async (sessionId: string) => {
    if (!sessionId) return;
    try {
      const backendBase = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8010';
      const res = await fetch(`${backendBase}/session/${sessionId}/reports?user_id=anonymous`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json() as { session_id: string; reports: Array<{ workflow_id: string; query: string; template_name: string; report: string; citations: string[]; elapsed_seconds: number; created_at: string }> };
      const history: ReportEntry[] = (data.reports || []).map((r) => ({
        query: r.query || '',
        reportType: r.template_name as ReportType,
        report: r.report || '',
        citations: r.citations || [],
        elapsed: r.elapsed_seconds || 0,
        workflowId: r.workflow_id,
      }));
      set({ reportHistory: history, report: '', citations: [] });
    } catch (err) {
      console.warn('[loadSessionHistory] 加载失败:', err);
    }
  },
}));
