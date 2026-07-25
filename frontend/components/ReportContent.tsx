'use client';

import type { Components } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

interface Props {
  content: string;
}

export function ReportContent({ content }: Props) {
  if (!content) return null;

  // 预处理：将正文中的 [N] 引用标注转为右上角小字，但引用来源列表保持不变
  const citationHeader = '## 引用来源';
  const idx = content.indexOf(citationHeader);
  const body = idx !== -1 ? content.slice(0, idx) : content;
  const citationSection = idx !== -1 ? content.slice(idx) : '';
  const processed =
    body.replace(
      /\[(\d+)\]/g,
      '<sup class="text-[0.70em] align-super text-blue-500 dark:text-blue-400">[$1]</sup>',
    ) + citationSection;

  const components: Components = {
    img: ({ src, alt, ...props }) => (
      <div className="my-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt ?? '图表'}
          className="max-w-[400px] w-full h-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm mx-auto block"
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
        rehypePlugins={[rehypeHighlight, rehypeRaw]}
        components={components}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}