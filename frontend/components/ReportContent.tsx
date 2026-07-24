'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';

interface Props {
  content: string;
}

export function ReportContent({ content }: Props) {
  if (!content) return null;

  const components: Components = {
    img: ({ src, alt, ...props }) => (
      <div className="my-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt ?? '图表'}
          className="max-w-full h-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm"
          loading="lazy"
          {...props}
        />
        {alt && alt !== '图表' && (
          <p className="text-center text-xs text-gray-400 dark:text-gray-500 mt-1">
            {alt}
          </p>
        )}
      </div>
    ),
  };

  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}