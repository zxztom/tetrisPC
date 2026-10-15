import argparse
import json
import sys
from pathlib import Path

from .server import serve
from .solver import solve


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="连续 PC 项目的本地求解实验室")
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve", help="打开图形界面")
    server.add_argument("--port", type=int, default=8787)
    server.add_argument("--open", action="store_true")
    solver = sub.add_parser("solve", help="离线求解并保存回放")
    solver.add_argument("--queue", default="JLOSTZIJLO")
    solver.add_argument("--hold", default="")
    solver.add_argument("--no-hold", action="store_true")
    solver.add_argument("--mode", choices=("hard", "soft"), default="hard")
    solver.add_argument("--request", type=Path, help="读取 JSON 棋盘和块序")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.port, args.open)
    else:
        request = json.loads(args.request.read_text(encoding="utf-8-sig")) if args.request else {
            "queue": args.queue, "hold": args.hold,
            "allow_hold": not args.no_hold, "mode": args.mode}
        result = solve(request, lambda _, message: print(message, flush=True))
        print(json.dumps({key: result[key] for key in
                          ("status", "message", "candidate_count", "checked_candidates",
                           "elapsed_seconds", "output_directory")}, ensure_ascii=False, indent=2))
        if result["steps"]:
            print("放置顺序:", result["placed_sequence"])
            print("累计消行:", result["total_cleared_lines"])
        return 0 if result["status"] == "solved" else 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, TimeoutError, InterruptedError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
