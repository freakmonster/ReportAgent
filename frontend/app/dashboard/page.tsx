'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import * as api from '@/lib/api';
import { DashboardCards } from '@/components/DashboardCards';
import { WorkflowTable } from '@/components/WorkflowTable';

interface TemplateItem {
  template: string;
  count: number;
}

interface OverviewRaw {
  total_requests: number;
  success_rate: number;
  total_tokens: number;
  avg_duration_seconds: number;
  by_template: Record<string, { count: number }>;
}

interface RecentItem {
  id: string;
  query: string;
  status: string;
  model: string;
  duration: number;
  created_at: string;
}

const TEMPLATE_LABELS: Record<string, string> = {
  deep_report: '深度研报',
  flash_news: '快讯',
  earnings_analysis: '财报分析',
};

export default function DashboardPage() {
  const [days, setDays] = useState<7 | 30>(7);
  const [overview, setOverview] = useState<OverviewRaw | null>(null);
  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [overviewData, recentData] = await Promise.all([
        api.get('/admin/dashboard/overview', { days: String(days) }),
        api.get('/admin/dashboard/recent', { limit: '20' }),
      ]);

      setOverview(overviewData as OverviewRaw);
      setRecent(recentData as RecentItem[]);
    } catch (err) {
      const message = err instanceof Error ? err.message : '请求失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Convert by_template dict to array
  const templateItems: TemplateItem[] = overview?.by_template
    ? Object.entries(overview.by_template).map(([template, data]) => ({
        template,
        count: data.count,
      }))
    : [];
  const totalByTemplate = templateItems.reduce((sum, t) => sum + t.count, 0);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="h-12 flex items-center px-6 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shrink-0">
        <Link
          href="/"
          className="text-sm font-bold tracking-wide text-gray-800 dark:text-gray-200 hover:text-blue-600 transition"
        >
          智能研报生成系统
        </Link>
        <span className="mx-3 text-gray-300 dark:text-gray-700">/</span>
        <span className="text-sm text-gray-500 dark:text-gray-400">运营面板</span>
      </header>

      {/* Body */}
      <main className="flex-1 max-w-5xl mx-auto w-full p-8 space-y-6">
        {/* Page title & time range toggle */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-800 dark:text-gray-200">
            运营面板
          </h2>
          <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
            <button
              type="button"
              className={`px-3 py-1 text-xs rounded-md font-medium transition ${
                days === 7
                  ? 'bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
              onClick={() => setDays(7)}
              disabled={loading}
            >
              7 天
            </button>
            <button
              type="button"
              className={`px-3 py-1 text-xs rounded-md font-medium transition ${
                days === 30
                  ? 'bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
              onClick={() => setDays(30)}
              disabled={loading}
            >
              30 天
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="px-4 py-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-600 dark:text-red-400">
            数据加载失败：{error}
            <button
              type="button"
              className="ml-3 underline hover:no-underline"
              onClick={fetchData}
            >
              重试
            </button>
          </div>
        )}

        {/* Dashboard cards */}
        <DashboardCards
          loading={loading}
          error={!!error && !overview}
          totalRequests={overview?.total_requests ?? 0}
          successRate={overview?.success_rate ?? 0}
          totalTokens={overview?.total_tokens ?? 0}
          avgDuration={overview?.avg_duration_seconds ?? 0}
        />

        {/* Recent workflows table */}
        <section>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            最近工作流
          </h3>
          <WorkflowTable items={recent} loading={loading} />
        </section>

        {/* By template distribution */}
        {templateItems.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              按模板分布
            </h3>
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="divide-y divide-gray-100 dark:divide-gray-800">
                {templateItems.map((item) => {
                  const percentage =
                    totalByTemplate > 0
                      ? ((item.count / totalByTemplate) * 100).toFixed(1)
                      : '0.0';
                  return (
                    <div
                      key={item.template}
                      className="flex items-center px-4 py-3 bg-white dark:bg-gray-900"
                    >
                      <span className="text-sm text-gray-700 dark:text-gray-300 w-28">
                        {TEMPLATE_LABELS[item.template] ?? item.template}
                      </span>
                      <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 w-16 text-right">
                        {item.count}
                      </span>
                      <div className="flex-1 mx-4">
                        <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-500 rounded-full transition-all duration-500"
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                      </div>
                      <span className="text-xs text-gray-400 dark:text-gray-500 w-12 text-right">
                        {percentage}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
