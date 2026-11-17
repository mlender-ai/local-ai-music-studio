"""Call the real Codex app-server MCP client; no model turn or sub-agent.

Uses an ephemeral protocol test session only, so no user chat is created.
The installed Codex-generated JSON schema defines these RPC methods.
"""

import asyncio
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


async def main():
    records = []
    log = (ROOT / ".runtime/logs/codex-app-server.log").open("w")
    process = await asyncio.create_subprocess_exec(
        shutil.which("codex"),
        "app-server",
        "--stdio",
        cwd=ROOT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=log,
    )
    counter = 0

    async def rpc(method, params):
        nonlocal counter
        counter += 1
        request_id = counter
        process.stdin.write(
            (
                json.dumps(dict(id=request_id, method=method, params=params)) + "\n"
            ).encode()
        )
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), 120)
            if not line:
                raise RuntimeError("Codex app-server closed its output")
            message = json.loads(line)
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]
            if "id" in message and "method" in message:
                # Never consent to unexpected access/approval requests in a test.
                response = dict(
                    id=message["id"],
                    error=dict(code=-32601, message="Unsupported test-client request"),
                )
                process.stdin.write((json.dumps(response) + "\n").encode())
                await process.stdin.drain()

    try:
        initialized = await rpc(
            "initialize",
            dict(
                clientInfo=dict(name="local_music_qa", version="0.1.0"),
                capabilities=dict(experimentalApi=True),
            ),
        )
        process.stdin.write(b'{"method":"initialized"}\n')
        await process.stdin.drain()
        records.append(dict(method="initialize", result=initialized))
        session = await rpc("thread/start", dict(cwd=str(ROOT), ephemeral=True))
        thread_id = session["thread"]["id"]
        tools = await rpc(
            "mcpServerStatus/list",
            dict(
                threadId=thread_id, serverName="local_music", detail="toolsAndAuthOnly"
            ),
        )
        records.append(dict(method="mcpServerStatus/list", result=tools))

        async def call(name, args):
            result = await rpc(
                "mcpServer/tool/call",
                dict(
                    threadId=thread_id, server="local_music", tool=name, arguments=args
                ),
            )
            if result.get("isError"):
                raise RuntimeError(result)
            records.append(
                dict(
                    method="mcpServer/tool/call",
                    tool=name,
                    arguments=args,
                    result=result,
                )
            )
            print("CODEX MCP", name, "SUCCESS", flush=True)
            return result.get("structuredContent") or json.loads(
                next(c["text"] for c in result["content"] if c["type"] == "text")
            )

        # Replay the successful SDK generation to verify cross-client idempotency.
        replay = await call(
            "music.generate",
            dict(
                prompt="우주 앰비언트, 드럼 없음, 보컬 없는 15초 음악.",
                duration=15,
                seed=45,
                request_key="mcp-smoke-v1",
            ),
        )
        status = await call("music.get_status", dict(job_id=replay["id"]))
        assert status["state"] == "succeeded"
        await call("music.list_versions", {})
        source = json.loads((ROOT / "docs/generation-results.json").read_text())[0][
            "result"
        ]["id"]
        filtered = await call(
            "music.apply_effect",
            dict(
                version_id=source,
                effect=dict(type="eq", mode="high_shelf", frequency=5000, gain_db=-2),
            ),
        )
        await call(
            "music.render",
            dict(
                version_id=filtered["version"]["id"],
                effects=[
                    dict(type="reverb", wet=0.2, decay=2.5, pre_delay_ms=20),
                    dict(type="limiter", ceiling_db=-1),
                ],
            ),
        )
        produced = await call(
            "music.produce",
            dict(version_id=source, instruction="조금 더 몽환적으로 만들어줘."),
        )
        assert produced["applied"]
        modified = produced["version"]["id"]
        await call("music.compare", dict(original_id=source, modified_id=modified))
        await call("music.export", dict(version_id=modified))
        await call("music.restore", dict(version_id=source))
        (ROOT / "docs/codex-mcp-calls.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2)
        )
        print("Real Codex app-server tool calls verified.", flush=True)
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        log.close()


if __name__ == "__main__":
    asyncio.run(main())
