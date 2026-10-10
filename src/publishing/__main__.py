"""CLI for the personal-brand site.

    python -m src.publishing publish [--json PATH] [--title ...] [--tags A,B] [--featured]
    python -m src.publishing build
    python -m src.publishing serve [--port 8000]
    python -m src.publishing check
    python -m src.publishing research --topic "..."   # run the agent, then publish
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import subprocess
import sys
from pathlib import Path

from .builder import WEB_DIR, SiteBuilder, find_placeholders, load_profile
from .publisher import CONTENT_DIR, publish_json

DEFAULT_JSON = "outputs/json/research_report.json"


def _publish(args: argparse.Namespace) -> int:
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
    path = publish_json(
        args.json, title=args.title, dek=args.dek, tags=tags, slug=args.slug,
        published=args.date, featured=args.featured, draft=args.draft,
    )
    print(f"Published insight record: {path}")
    return _build(args) if args.build else 0


def _build(_: argparse.Namespace) -> int:
    builder = SiteBuilder(WEB_DIR, include_drafts=getattr(_, "drafts", False))
    out = builder.build()
    print(f"Built {len(builder.insights)} insight(s) -> {out}/index.html")
    return 0


def _serve(args: argparse.Namespace) -> int:
    _build(args)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB_DIR / "dist"))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def _check(_: argparse.Namespace) -> int:
    missing = find_placeholders(load_profile(WEB_DIR))
    if not missing:
        print("Profile complete — no placeholders left.")
        return 0
    print(f"{len(missing)} placeholder(s) still to personalise in website/profile.yaml:")
    for p in missing:
        print(f"  - {p}")
    return 1


def _research(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "-m", "src.app", "--topic", args.topic, "--mode", args.mode,
           "--tone", "thought_leadership"]
    if args.provider:
        cmd += ["--map-provider", args.provider, "--reduce-provider", args.provider]
    print("Running research agent:", " ".join(cmd))
    if subprocess.call(cmd) != 0:
        return 1
    args.json = DEFAULT_JSON
    args.build = True
    return _publish(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.publishing", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def editorial(p: argparse.ArgumentParser) -> None:
        p.add_argument("--title"); p.add_argument("--dek"); p.add_argument("--slug")
        p.add_argument("--tags", help="Comma separated; auto-detected when omitted")
        p.add_argument("--date", help="YYYY-MM-DD (default: today)")
        p.add_argument("--featured", action="store_true"); p.add_argument("--draft", action="store_true")
        p.add_argument("--build", action="store_true", help="Rebuild the site afterwards")

    p_pub = sub.add_parser("publish", help="Publish a research-agent JSON as an insight")
    p_pub.add_argument("--json", default=DEFAULT_JSON); editorial(p_pub); p_pub.set_defaults(fn=_publish)

    p_build = sub.add_parser("build", help="Render the static site into website/dist")
    p_build.add_argument("--drafts", action="store_true", help="Include draft insights")
    p_build.set_defaults(fn=_build)

    p_serve = sub.add_parser("serve", help="Build and preview locally")
    p_serve.add_argument("--port", type=int, default=8000); p_serve.add_argument("--drafts", action="store_true")
    p_serve.set_defaults(fn=_serve)

    sub.add_parser("check", help="List profile placeholders still to fill").set_defaults(fn=_check)

    p_res = sub.add_parser("research", help="Run the research agent on a topic, then publish it")
    p_res.add_argument("--topic", required=True); p_res.add_argument("--mode", choices=["quick", "deep"], default="deep")
    p_res.add_argument("--provider", choices=["gemini", "ollama"]); editorial(p_res); p_res.set_defaults(fn=_research)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
