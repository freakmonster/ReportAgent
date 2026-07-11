"""Quick integration test for Tavily search server."""
import asyncio
import httpx


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(90)) as c:
        # 1. Health check
        r = await c.get("http://127.0.0.1:8001/health")
        print("=== HEALTH ===")
        print(r.json())

        # 2. Web search
        print()
        print("=== WEB SEARCH: 2026年Q2 中国新能源汽车 市场规模 ===")
        payload = {
            "query": "2026年Q2 中国新能源汽车 市场规模",
            "search_depth": "basic",
            "max_results": 5,
        }
        r = await c.post("http://127.0.0.1:8001/tools/web_search", json=payload)
        print(f"Status: {r.status_code}")
        data = r.json()
        if r.status_code != 200:
            print(f"Error: {data}")
            return
        print(f"Response time: {data.get('response_time', 'N/A')}s")
        print(f"Answer: {data.get('answer', 'N/A')}")
        print()
        for i, item in enumerate(data.get("results", []), 1):
            print(f"  [{i}] {item['title']}")
            print(f"      URL: {item['url']}")
            content = item.get("content", "")[:200].replace("\n", " ")
            print(f"      {content}...")
            if item.get("raw_content"):
                raw = item["raw_content"][:200].replace("\n", " ")
                print(f"      [raw] {raw}...")
            print()

        # 3. News search
        print("=== NEWS SEARCH: 新能源汽车 电池技术 突破 ===")
        r = await c.post("http://127.0.0.1:8001/tools/news_search", json={
            "query": "新能源汽车 电池技术 突破",
            "days": 30,
            "max_results": 3,
        })
        print(f"Status: {r.status_code}")
        data = r.json()
        if r.status_code == 200:
            print(f"Response time: {data.get('response_time', 'N/A')}s")
            for i, item in enumerate(data.get("results", []), 1):
                print(f"  [{i}] {item['title']}")
                print(f"      URL: {item['url']}")
                print(f"      {item.get('content', '')[:120]}...")
        else:
            print(f"Error: {data}")


asyncio.run(main())
