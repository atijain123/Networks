from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import serve
from .service import FlowScopeService


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowScope application-aware SDN prototype")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("demo", help="Run an NSGA-II decision and print the result")
    serve_parser = subcommands.add_parser("serve", help="Serve the API and lightweight dashboard")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    service = FlowScopeService(root / "results" / "routing-decisions.jsonl")
    if args.command == "demo":
        print(json.dumps(service.simulate(seed=20261013), indent=2))
        return
    server = serve(service, root, port=args.port)
    print(f"FlowScope running at http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
