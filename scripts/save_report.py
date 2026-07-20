"""Save report from SSE endpoint to file."""

import json

import requests

r = requests.post(
    "http://localhost:8000/chat/stream",
    json={"query": "新能源汽车", "report_type": "deep_report"},
    stream=True,
)

for line in r.iter_lines():
    if not line:
        continue
    text = line.decode()
    if "complete" in text and "report" in text:
        # text is: data: {json-string}
        event = json.loads(text[5:])  # strip "data: "
        data = event["data"]  # already a dict
        report = data["report"]
        with open("report_output2.md", "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to report_output.md ({len(report)} chars)")
        break
