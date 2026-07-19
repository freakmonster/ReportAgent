'use client';

export default function ReviewPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-12 flex items-center px-6 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shrink-0">
        <h1 className="text-sm font-bold tracking-wide text-gray-800 dark:text-gray-200">
          智能研报生成系统
        </h1>
        <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
          审核台
        </span>
      </header>

      <main className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-gray-400 dark:text-gray-600">
          <span className="text-6xl" role="img" aria-label="review">
            📋
          </span>
          <h2 className="text-lg font-semibold text-gray-500 dark:text-gray-400">
            审核台功能开发中
          </h2>
          <p className="text-sm text-gray-400 dark:text-gray-500">
            该页面将用于人工审核和确认待发布的研报
          </p>
        </div>
      </main>
    </div>
  );
}
