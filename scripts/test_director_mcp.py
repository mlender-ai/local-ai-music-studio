"""Real STDIO test of external Music Plan delivery and generation retry."""

import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    rows = json.loads((ROOT / "outputs/producer/results.json").read_text())
    b = next(r["job"] for r in rows if r["genre"] == "soul" and r["condition"] == "B")
    request = b["request"]
    async with stdio_client(
        StdioServerParameters(
            command=sys.executable, args=["-m", "app.mcp_server"], cwd=str(ROOT)
        )
    ) as streams:
        async with ClientSession(*streams) as s:
            await s.initialize()

            async def call(name, args):
                r = await s.call_tool(name, args)
                assert not r.isError, r
                return r.structuredContent or json.loads(
                    next(c.text for c in r.content if c.type == "text")
                )

            d = await call(
                "music.director_plan",
                dict(
                    prompt=request["original_prompt"],
                    music_plan=request["music_plan"],
                    instrumental=True,
                ),
            )
            assert (
                d["caption"] == request["caption"]
                and d["music_plan"]["source"] == "codex"
            )
            result = await call(
                "music.generate",
                dict(
                    prompt=request["original_prompt"],
                    music_plan=request["music_plan"],
                    instrumental=True,
                    seed=42,
                    request_key="producer-v1-soul-B",
                ),
            )
            assert result["id"] == b["id"] and result["state"] == "succeeded"
            print(
                "Structured Codex Music Plan reached actual generated B unchanged; retry reused job."
            )


if __name__ == "__main__":
    asyncio.run(main())
