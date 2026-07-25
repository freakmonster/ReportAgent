'use client';

import { NodeProgress } from '@/components/NodeProgress';
import { ReportBubble } from '@/components/ReportBubble';
import { TaskForm } from '@/components/TaskForm';
import { useWorkflowStore } from '@/stores/workflowStore';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useRef } from 'react';

/** 品牌首屏空状态 */
function BrandEmptyState() {
  const slogan = 'AI 驱动的金融研报生成';

  // 稳定化粒子参数
  const particles = useMemo(() =>
    [...Array(12)].map(() => ({
      size: 2 + Math.random() * 3,
      left: Math.random() * 100,
      delay: Math.random() * 8,
      duration: 6 + Math.random() * 10,
    })),
  []);

  const featureCards = [
    {
      icon: (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
        </svg>
      ),
      title: '深度研报',
      desc: '多 Agent 协同，深度分析产业链与公司基本面，生成结构化长篇研报',
      color: 'from-blue-500/20 to-cyan-500/10 border-blue-400/20',
      iconColor: 'text-blue-400',
    },
    {
      icon: (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      ),
      title: '市场快讯',
      desc: '实时抓取市场热点，秒级生成结构化快讯，把握瞬息万变的行情',
      color: 'from-amber-500/20 to-orange-500/10 border-amber-400/20',
      iconColor: 'text-amber-400',
    },
    {
      icon: (
        <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="20" x2="18" y2="10" />
          <line x1="12" y1="20" x2="12" y2="4" />
          <line x1="6" y1="20" x2="6" y2="14" />
        </svg>
      ),
      title: '财报分析',
      desc: '自动解读财报数据，提炼核心财务指标与趋势洞察',
      color: 'from-emerald-500/20 to-teal-500/10 border-emerald-400/20',
      iconColor: 'text-emerald-400',
    },
  ] as const;

  return (
    <div className="flex flex-col items-center justify-center h-full relative overflow-hidden">
      {/* 粒子背景 */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {particles.map((p, i) => (
            <div
              key={i}
              className="absolute rounded-full bg-blue-400/20"
              style={{
                width: p.size,
                height: p.size,
                left: `${p.left}%`,
                bottom: '-10px',
                animation: `floatUp ${p.duration}s ${p.delay}s linear infinite`,
              }}
            />
          ))}
        {/* 静态光晕 */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[300px] bg-blue-500/5 rounded-full blur-3xl" />
        <div className="absolute top-2/3 left-1/3 w-[300px] h-[200px] bg-cyan-500/4 rounded-full blur-3xl" />
      </div>

      {/* 主内容 */}
      <div className="relative z-10 flex flex-col items-center gap-8 max-w-lg">
        {/* Slogan — 逐字淡入 */}
        <div className="text-center">
          <h2 className="text-2xl font-bold tracking-tight text-slate-200 mb-2">
            {slogan.split('').map((char, i) => (
              <span
                key={i}
                className="animate-char"
                style={{ animationDelay: `${0.3 + i * 0.06}s` }}
              >
                {char === ' ' ? '\u00A0' : char}
              </span>
            ))}
          </h2>
          <p className="text-sm text-slate-400 mt-1">专业、高效、智能</p>
        </div>

        {/* 功能卡片 */}
        <div className="flex gap-4 w-full">
          {featureCards.map((card) => (
            <div
              key={card.title}
              className={`flex-1 p-4 rounded-2xl bg-gradient-to-b ${card.color} border backdrop-blur-sm
                transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:shadow-blue-500/5`}
            >
              <div className={`mb-2 ${card.iconColor}`}>{card.icon}</div>
              <h3 className="text-sm font-semibold text-slate-200 mb-1">{card.title}</h3>
              <p className="text-[11px] text-slate-400 leading-relaxed">{card.desc}</p>
            </div>
          ))}
        </div>

        {/* 底部引导 */}
        <p className="text-xs text-slate-500 flex items-center gap-1">
          开始你的第一次研究
          <span className="inline-block animate-pulse">&rarr;</span>
        </p>
      </div>
    </div>
  );
}

const NAV_LINKS = [
  { href: '/', label: '工作台' },
  { href: '/history', label: '历史' },
  { href: '/dashboard', label: '运营面板' },
] as const;

export default function Home() {
  const pathname = usePathname();
  const isRunning = useWorkflowStore((s) => s.isRunning);
  const report = useWorkflowStore((s) => s.report);
  const sessionId = useWorkflowStore((s) => s.sessionId);
  const totalElapsed = useWorkflowStore((s) => s.totalElapsed);
  const reportHistory = useWorkflowStore((s) => s.reportHistory);
  const detectedTemplate = useWorkflowStore((s) => s.detectedTemplate);
  const loadSessionHistory = useWorkflowStore((s) => s.loadSessionHistory);

  // --- 自动滚动到右栏底部 ---
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [reportHistory.length, isRunning]);

  // --- 切换会话时加载历史 ---
  const prevSessionRef = useRef(sessionId);
  useEffect(() => {
    if (sessionId && sessionId !== prevSessionRef.current) {
      loadSessionHistory(sessionId);
      prevSessionRef.current = sessionId;
    }
  }, [sessionId, loadSessionHistory]);

  // --- 页面首次加载时加载当前会话历史 ---
  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (sessionId && !initialLoadDone.current) {
      loadSessionHistory(sessionId);
      initialLoadDone.current = true;
    }
  }, [sessionId, loadSessionHistory]);

  return (
    <div className="h-screen flex flex-col">
      {/* Header — 品牌质感升级 */}
      <header className="h-12 flex items-center px-6 shrink-0 bg-gradient-to-r from-slate-700 via-blue-900 to-slate-700 border-b border-slate-600/50 relative overflow-hidden">
        {/* 微弱网格纹理 */}
        <div className="absolute inset-0 bg-grid-pattern pointer-events-none" />

        {/* Logo 区 */}
        <div className="relative z-10 flex items-center gap-2.5">
          {/* 品牌图标 */}
          <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="url(#icon-grad)" />
            <path d="M2 17L12 22L22 17" stroke="url(#icon-grad)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 12L12 17L22 12" stroke="url(#icon-grad)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <defs>
              <linearGradient id="icon-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                <stop stopColor="#60a5fa" />
                <stop offset="1" stopColor="#22d3ee" />
              </linearGradient>
            </defs>
          </svg>
          <h1 className="text-sm font-bold tracking-tight">
            <span className="text-gradient-brand">智能研报</span>
            <span className="text-gold-glow ml-1">生成系统</span>
          </h1>
        </div>

        {/* 导航 tab — 胶囊形状 */}
        <nav className="ml-6 flex items-center gap-1 relative z-10">
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`text-xs px-3 py-1 rounded-full transition-all duration-300 ease-out ${
                  isActive
                    ? 'bg-blue-500/15 text-blue-300 border border-blue-400/30 shadow-[0_0_10px_rgba(59,130,246,0.25)]'
                    : 'text-slate-300 hover:text-slate-100 hover:bg-slate-600/50'
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>

        {/* 右侧状态指示器 */}
        <div className="ml-auto flex items-center gap-4 text-xs text-slate-400 relative z-10">
          {isRunning && (
            <span className="relative flex items-center gap-2 text-blue-300 overflow-hidden rounded-full px-2.5 py-1 bg-blue-500/10 border border-blue-500/20">
              {/* 流光条动画 */}
              <span className="pointer-events-none absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-blue-400/25 to-transparent animate-scan-bar" />
              <span className="relative inline-block w-2 h-2 bg-blue-400 rounded-full shrink-0" />
              <span className="relative">生成中</span>
            </span>
          )}
          {totalElapsed > 0 && !isRunning && (
            <span>总耗时 {totalElapsed.toFixed(1)}s</span>
          )}
        </div>
      </header>

      {/* Body: 两栏布局 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左栏: 输入区域 */}
        <aside className="w-[380px] shrink-0 border-r border-slate-600/40 bg-slate-800/65 backdrop-blur-xl flex flex-col overflow-hidden">
          <TaskForm />
        </aside>

        {/* 右栏: 报告预览 */}
        <main className="flex-1 overflow-y-auto p-6 bg-slate-800/30 custom-scrollbar">
          {/* 品牌首屏空状态 */}
          {!report && !isRunning && reportHistory.length === 0 && (
            <BrandEmptyState />
          )}

          {/* 历史气泡列表 */}
          {reportHistory.length > 0 && (
            <div className="space-y-4">
              {reportHistory.map((entry, i) => (
                <ReportBubble key={entry.workflowId || i} entry={entry} index={i} defaultCollapsed={i < reportHistory.length - 1} />
              ))}
            </div>
          )}

          {/* 非 QA 执行中：显示 Agent 执行进度 */}
          {isRunning && detectedTemplate !== 'qa' && (
            <div className="mt-6">
              <NodeProgress />
            </div>
          )}

          {/* 哨兵元素：用于自动滚动到最底部 */}
          <div ref={bottomRef} />
        </main>
      </div>
    </div>
  );
}
