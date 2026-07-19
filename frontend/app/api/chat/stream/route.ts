/** Next.js API Route — 用 Node.js 原生 HTTP 透传后端 SSE 流（避免 fetch 缓冲） */
import type { IncomingMessage } from 'http';
import { request as httpRequest } from 'http';

export async function POST(req: Request) {
  const body = await req.json();
  console.log('[API] SSE proxy | query=', body.query?.slice(0, 30), '| model=', body.model);

  const encoded = Buffer.from(JSON.stringify(body));

  const stream = new ReadableStream({
    start(controller) {
      const backendReq = httpRequest(
        {
          hostname: 'localhost',
          port: 8010,
          path: '/chat/stream',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': String(encoded.length),
          },
        },
        (res: IncomingMessage) => {
          console.log('[API] Backend connected | status=', res.statusCode);
          if (res.statusCode !== 200) {
            controller.error(new Error(`Backend returned ${res.statusCode}`));
            return;
          }
          res.on('data', (chunk: Buffer) => {
            console.log('[API] chunk | size=', chunk.length);
            controller.enqueue(new Uint8Array(chunk));
          });
          res.on('end', () => {
            console.log('[API] stream ended');
            controller.close();
          });
          res.on('error', (err: Error) => {
            console.error('[API] stream error:', err.message);
            controller.error(err);
          });
        },
      );

      backendReq.on('error', (err: Error) => {
        console.error('[API] request error:', err.message);
        controller.error(err);
      });

      backendReq.write(encoded);
      backendReq.end();
    },
    cancel() {
      console.log('[API] stream cancelled by client');
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
