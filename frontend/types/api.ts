// ============================================================
// API Types — 与后端 ChatRequest / SSE Event 严格对齐
// ============================================================

// --- 报告类型 ---
export type ReportType = 'deep_report' | 'flash_news' | 'earnings_analysis';

// --- 模型选项 ---
export type ModelOption =
  | 'deepseek-flash'
  | 'deepseek-pro'
  | 'qwen-8b'
  | 'qwen-32b'
  | 'qwen-max';

// --- 请求体 ---
export interface ChatRequest {
  query: string;
  report_type: ReportType;
  model: ModelOption;
  user_id: string;
  session_id?: string;
  reconnect_token?: string | null;
}

// --- 节点状态 ---
export type NodeStatus = 'idle' | 'running' | 'completed' | 'error';

// --- 工作流节点定义顺序 ---
export const NODE_ORDER: string[] = [
  'intent_classifier',
  'research_planner',
  'data_collector',
  'data_processor',
  'data_analyst',
  'writer',
  'editor',
  'reviewer',
  'publisher',
];

// --- 节点名称 → 中文映射 ---
export const NODE_LABELS: Record<string, string> = {
  intent_classifier: '意图识别',
  research_planner: '研究规划',
  data_collector: '数据采集',
  data_processor: '数据处理',
  data_analyst: '数据分析',
  writer: '报告撰写',
  editor: '编辑润色',
  reviewer: '质量审核',
  publisher: '发布输出',
};

// --- 模型选项 → 显示名称 ---
export const MODEL_LABELS: Record<ModelOption, string> = {
  'deepseek-flash': 'DeepSeek Flash',
  'deepseek-pro': 'DeepSeek Pro',
  'qwen-8b': 'Qwen-Light (8B)',
  'qwen-32b': 'Qwen-Medium (32B)',
  'qwen-max': 'Qwen-Max',
};

// --- 报告类型 → 显示名称 ---
export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  deep_report: '深度研报',
  flash_news: '快讯',
  earnings_analysis: '财报分析',
};

// --- SSE 进度事件 ---
export interface SSEProgressEvent {
  node: string;
  status: 'ok' | 'error';
  duration_ms: number;
}

// --- SSE 完成事件 ---
export interface SSECompleteEvent {
  report: string;
  citations?: string[];
  elapsed: number;
  workflow_id: string;
  template?: ReportType;
}
