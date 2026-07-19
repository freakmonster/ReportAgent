const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8010';

async function request(method: string, path: string, body?: unknown, params?: Record<string, string>): Promise<unknown> {
  let url = `${BASE_URL}${path}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export async function get(path: string, params?: Record<string, string>): Promise<unknown> {
  return request('GET', path, undefined, params);
}

export async function post(path: string, body?: unknown): Promise<unknown> {
  return request('POST', path, body);
}

export async function del(path: string): Promise<unknown> {
  return request('DELETE', path);
}
