"""Small CLI for the same operations exposed through MCP."""

import argparse
import json
import time
from engine import jobs, service, store
from engine.schema import Generate


def main():
    parser = argparse.ArgumentParser(description="Local AI Music Studio")
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("prompt")
    gen.add_argument("--duration", type=float, default=30)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--wait", action="store_true")
    gen.add_argument("--request-key")
    mode = gen.add_mutually_exclusive_group()
    mode.add_argument("--vocal", action="store_true")
    mode.add_argument("--instrumental", action="store_true")
    gen.add_argument("--intent", help="Path to editable Music Intent JSON")
    gen.add_argument("--music-plan", help="Path to validated Music Plan JSON")
    gen.add_argument(
        "--inference-profile",
        choices=["turbo_4bit", "turbo_8bit"],
        default="turbo_4bit",
    )
    gen.add_argument("--lyrics", default="")
    status = commands.add_parser("status")
    status.add_argument("job_id", nargs="?")
    commands.add_parser("list")
    prod = commands.add_parser("produce")
    prod.add_argument("version_id")
    prod.add_argument("instruction")
    render = commands.add_parser("render")
    render.add_argument("version_id")
    render.add_argument("effects_json", help="JSON array of effects")
    compare = commands.add_parser("compare")
    compare.add_argument("original_id")
    compare.add_argument("modified_id")
    export = commands.add_parser("export")
    export.add_argument("version_id")
    export.add_argument("--filename")
    restore = commands.add_parser("restore")
    restore.add_argument("version_id")
    imp = commands.add_parser("import")
    imp.add_argument("path")
    player = commands.add_parser("player")
    player.add_argument("--port", type=int, default=8795)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            result = jobs.submit(
                Generate(
                    prompt=args.prompt,
                    duration=args.duration,
                    seed=args.seed,
                    instrumental=False
                    if args.vocal
                    else True
                    if args.instrumental
                    else None,
                    intent=json.loads(
                        __import__("pathlib").Path(args.intent).read_text()
                    )
                    if args.intent
                    else None,
                    music_plan=json.loads(
                        __import__("pathlib").Path(args.music_plan).read_text()
                    )
                    if args.music_plan
                    else None,
                    inference_profile=args.inference_profile,
                    lyrics=args.lyrics,
                ),
                args.request_key,
            )
            if args.wait:
                print(
                    json.dumps(dict(job_id=result["id"], state=result["state"])),
                    flush=True,
                )
                while result["state"] in ("queued", "running"):
                    time.sleep(2)
                    result = jobs.status(result["id"])
                if result["state"] == "failed":
                    raise RuntimeError(result["error"])
        elif args.command == "status":
            result = jobs.status(args.job_id)
        elif args.command == "list":
            result = store.list_versions()
        elif args.command == "produce":
            result = service.produce(args.version_id, args.instruction)
        elif args.command == "render":
            result = service.render(args.version_id, json.loads(args.effects_json))
        elif args.command == "compare":
            result = service.compare_versions(args.original_id, args.modified_id)
        elif args.command == "export":
            result = service.export(args.version_id, args.filename)
        elif args.command == "restore":
            result = store.restore(args.version_id)
        elif args.command == "import":
            result = service.import_audio(args.path)
        elif args.command == "player":
            import uvicorn

            uvicorn.run("app.player.server:app", host="127.0.0.1", port=args.port)
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, json.dumps(dict(error=str(exc)), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
