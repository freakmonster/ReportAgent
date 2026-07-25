'use client';

import type { Components } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

interface Props {
  content: string;
  citations?: Record<string, string>;
}

export function ReportContent({ content, citations }: Props) {
  if (!content) return null;

  // 预处理：将正文中的 [N] 引用标注转为右上角小字，hover 显示引用 URL
  const citationHeader = '## 引用来源';
  const idx = content.indexOf(citationHeader);
  const body = idx !== -1 ? content.slice(0, idx) : content;
  const citationSection = idx !== -1 ? content.slice(idx) : '';
  const processed =
    body.replace(
      /\[(\d+)\]/g,
      (_, n) => {
        const url = citations?.[n];
        return `<sup class="text-[0.70em] align-super text-blue-400${url ? ' cursor-help' : ''}"${url ? ` title="${url}"` : ''}>[${n}]</sup>`;
      },
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
    <div className="prose prose-sm max-w-none
  prose-headings:text-slate-50   // 标题 h1-h6
  prose-strong:text-slate-100     // 加粗
  prose-a:text-blue-300           // 链接
  prose-code:text-slate-200       // 行内代码
  prose-blockquote:text-slate-100 // 引用块
  prose-p:text-slate-200          // 段落
  prose-li:text-slate-200         // 列表项
">
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