"""Debug script: check chart server output and diagnose broken image issue."""
import asyncio
import httpx
import base64
import re


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as c:
        try:
            r = await c.post(
                "http://localhost:8003/tools/generate_bar_chart",
                json={
                    "title": "Test Chart",
                    "x_label": "Metrics",
                    "y_label": "Value",
                    "data": {"Values": [10, 20, 30, 40]},
                    "x_ticks": ["A", "B", "C", "D"],
                },
            )
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            print(f"Chart server unreachable: {e}")
            print("→ MCP chart service not running → image_base64 will be empty → broken image")
            return

    b64 = d.get("image_base64", "")
    print(f"Chart server response keys: {list(d.keys())}")
    print(f"image_base64 length: {len(b64)} chars")

    if not b64:
        print("image_base64 is EMPTY — chart generation returned placeholder")
        print(f"Error field: {d.get('error', 'N/A')}")
        return

    # Check for embedded newlines (would break markdown ![]() syntax)
    has_newline = "\n" in b64 or "\r" in b64
    print(f"Contains newline in base64: {has_newline}")

    # Check first 80 chars
    print(f"Base64 start: {b64[:80]}")

    # Check if it's valid base64 that decodes to a valid PNG
    try:
        decoded = base64.b64decode(b64)
        print(f"Decoded PNG size: {len(decoded)} bytes ({len(decoded)/1024:.1f} KB)")
        if decoded[:8] == b"\x89PNG\r\n\x1a\n":
            print("PNG header: VALID")
        else:
            print(f"PNG header: INVALID — first 8 bytes: {decoded[:8].hex()}")
    except Exception as e:
        print(f"Base64 decode failed: {e}")

    # Test the full markdown image syntax that publisher generates
    img_md = f"![Test Chart](data:image/png;base64,{b64})"
    print(f"\nFull markdown image length: {len(img_md)} chars")

    # Check if markdown syntax is valid (no unescaped parens, etc)
    url_part = f"data:image/png;base64,{b64}"
    has_paren = "(" in b64 or ")" in b64
    print(f"Base64 contains parenthesis: {has_paren}")
    has_space = " " in b64
    print(f"Base64 contains space: {has_space}")


if __name__ == "__main__":
    asyncio.run(main())
