"""Call Parallel's hosted search and fetch tools without an LLM or API key."""

import argparse
import asyncio
import math
import sys
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ENDPOINT = "https://search.parallel.ai/mcp"
USER_AGENT = (
    "mcp-agent-parallel-example/1.0 "
    "(+https://github.com/Haohao-end/mcp-agent)"
)


def nonempty(value):
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return value


def positive_seconds(value):
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive number") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return seconds


def page_url(value):
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ("http", "https") and parsed.hostname
    except ValueError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError("must be an HTTP or HTTPS URL")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout", type=positive_seconds, default=60,
        help="overall request deadline in seconds (default: 60)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="find current web sources")
    search.add_argument("objective", type=nonempty)
    search.add_argument(
        "--query", type=nonempty, action="append", required=True,
        help="keyword query; repeat for related queries (3-6 words each)",
    )
    fetch = commands.add_parser("fetch", help="read relevant excerpts from pages")
    fetch.add_argument("urls", type=page_url, nargs="+")
    fetch.add_argument("--objective", type=nonempty)
    args = parser.parse_args(argv)
    if args.command == "fetch":
        if len(args.urls) > 20:
            parser.error("fetch accepts at most 20 URLs")
        if args.objective and len(args.objective) > 200:
            parser.error("fetch objective must be at most 200 characters")
    return args


async def request(args):
    if args.command == "search":
        name = "web_search"
        arguments = {"objective": args.objective, "search_queries": args.query}
    else:
        name = "web_fetch"
        arguments = {"urls": args.urls}
        if args.objective:
            arguments["objective"] = args.objective

    # This client does not load .env files, saved credentials, or API keys.
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(args.timeout),
        follow_redirects=True,
    ) as client:
        async with streamable_http_client(ENDPOINT, http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                return await session.call_tool(name, arguments)


def error_message(error):
    # AnyIO can wrap transport errors in nested task-group exceptions.
    children = getattr(error, "exceptions", None)
    if children:
        return "; ".join(error_message(child) for child in children)
    return str(error)


def main(argv=None):
    args = parse_args(argv)
    try:
        result = asyncio.run(asyncio.wait_for(request(args), timeout=args.timeout))
    except asyncio.TimeoutError:
        print(f"Parallel MCP request timed out after {args.timeout:g}s.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"Parallel MCP request failed: {error_message(error)}", file=sys.stderr)
        return 1
    # Preserve the MCP content and structured result, including source URLs.
    print(result.model_dump_json(indent=2))
    if result.isError:
        print("Parallel returned a tool error; see the JSON response.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
