'use client';

interface Props {
  citations: string[];
}

export function CitationList({ citations }: Props) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-8 pt-4 border-t border-gray-200 dark:border-gray-700">
      <h3 className="text-sm font-semibold mb-2 text-gray-600 dark:text-gray-400">
        📎 引用来源 ({citations.length})
      </h3>
      <ol className="text-xs text-gray-500 dark:text-gray-400 space-y-1 list-decimal list-inside break-all">
        {citations.map((c, i) => (
          <li key={i}>
            {c.startsWith('http') ? (
              <a href={c} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                {c}
              </a>
            ) : (
              c.replace(/^-\s*/, '')
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
