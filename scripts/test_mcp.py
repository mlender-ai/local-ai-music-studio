"""Real STDIO MCP client smoke test, including a new local model generation."""

import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def payload(result):
    if result.isError:
        raise RuntimeError(str(result))
    if result.structuredContent:
        return result.structuredContent
    return json.loads(next(c.text for c in result.content if c.type == "text"))


async def main():
    records = []
    async with stdio_client(
        StdioServerParameters(
            command=sys.executable, args=["-m", "app.mcp_server"], cwd=str(ROOT)
        )
    ) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            listed = await session.list_tools()
            print("Tools:", [t.name for t in listed.tools], flush=True)

            async def call(name, args):
                data = payload(await session.call_tool(name, args))
                records.append(dict(tool=name, arguments=args, result=data))
                print(name, "OK", flush=True)
                return data

            result = await call(
                "music.generate",
                dict(
                    prompt="우주 앰비언트, 드럼 없음, 보컬 없는 15초 음악.",
                    duration=15,
                    seed=45,
                    request_key="mcp-smoke-v1",
                ),
            )
            while result["state"] in ("queued", "running"):
                await asyncio.sleep(3)
                result = payload(
                    await session.call_tool(
                        "music.get_status", {"job_id": result["id"]}
                    )
                )
            records.append(dict(tool="music.get_status", result=result))
            assert result["state"] == "succeeded", result["error"]
            source = result["result"]["id"]
            modified = await call(
                "music.apply_effect",
                dict(
                    version_id=source,
                    effect=dict(
                        type="eq", mode="high_shelf", frequency=5000, gain_db=-3
                    ),
                ),
            )
            rendered = await call(
                "music.render",
                dict(
                    version_id=modified["version"]["id"],
                    effects=[
                        dict(type="reverb", wet=0.15, decay=2),
                        dict(type="limiter", ceiling_db=-1),
                    ],
                ),
            )
            comp = await call(
                "music.compare",
                dict(original_id=source, modified_id=rendered["version"]["id"]),
            )
            assert comp["same_format"] and comp["changed_samples"] > 0
            await call("music.export", dict(version_id=rendered["version"]["id"]))
            await call("music.restore", dict(version_id=source))
            await call("music.list_versions", {})
    (ROOT / "docs/mcp-smoke.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2)
    )
    print("STDIO MCP integration passed.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
