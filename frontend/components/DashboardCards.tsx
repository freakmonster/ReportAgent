'use client';

interface DashboardCardsProps {
  totalRequests: number;
  successRate: number;
  totalTokens: number;
  avgDuration: number;
  loading: boolean;
  error: boolean;
}

function formatTokens(totalTokens: number): string {
  if (totalTokens >= 1_000_000) {
    return (totalTokens / 1_000_000).toFixed(1) + 'M';
  }
  return (totalTokens / 1_000).toFixed(1) + 'K';
}

function successRateColor(rate: number): string {
  const pct = rate * 100;
  if (pct > 90) return 'text-green-500 dark:text-green-400';
  if (pct > 70) return 'text-yellow-500 dark:text-yellow-400';
  return 'text-red-500 dark:text-red-400';
}

function SkeletonCard() {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-4 bg-white dark:bg-gray-900 animate-pulse">
      <div className="h-4 w-16 bg-gray-200 dark:bg-gray-700 rounded mb-3" />
      <div className="h-8 w-24 bg-gray-200 dark:bg-gray-700 rounded" />
    </div>
  );
}

function ErrorCard({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 p-4 bg-white dark:bg-gray-900">
      <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className="text-2xl font-bold text-gray-400 dark:text-gray-600">—</div>
    </div>
  );
}

export function DashboardCards({ totalRequests, successRate, totalTokens, avgDuration, loading, error }: DashboardCardsProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ErrorCard label="请求总量" />
        <ErrorCard label="成功率" />
        <ErrorCard label="Token 消耗" />
        <ErrorCard label="平均耗时" />
      </div>
    );
  }

  const cards = [
    {
      label: '请求总量',
      value: totalRequests.toLocaleString(),
      color: 'text-gray-800 dark:text-gray-100',
    },
    {
      label: '成功率',
      value: (successRate * 100).toFixed(1) + '%',
      color: successRateColor(successRate),
    },
    {
      label: 'Token 消耗',
      value: formatTokens(totalTokens),
      color: 'text-gray-800 dark:text-gray-100',
    },
    {
      label: '平均耗时',
      value: avgDuration.toFixed(1) + 's',
      color: 'text-gray-800 dark:text-gray-100',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-lg border border-gray-200 dark:border-gray-800 p-4 bg-white dark:bg-gray-900"
        >
          <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">{card.label}</div>
          <div className={`text-2xl font-bold ${card.color}`}>{card.value}</div>
        </div>
      ))}
    </div>
  );
}
