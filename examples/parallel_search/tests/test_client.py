"""Exercise the CLI through the real MCP transport with local HTTP responses."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx


SPEC = importlib.util.spec_from_file_location(
    "parallel_example", Path(__file__).resolve().parents[1] / "client.py"
)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)
HTTP_CLIENT = httpx.AsyncClient


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.tool_result = {
            "content": [{"type": "text", "text": "Source: https://example.org/docs\nMCP client documentation"}],
            "isError": False,
        }
        self.cancelled = False

    async def respond(self, request):
        message = json.loads(request.content)
        self.requests.append((request, message))
        if message["method"] == "notifications/initialized":
            return httpx.Response(202)
        if message["method"] == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-server", "version": "1"},
            }
        elif message["method"] == "tools/list":
            result = {"tools": [
                {"name": name, "inputSchema": {"type": "object"}}
                for name in ("web_search", "web_fetch")
            ]}
        else:
            self.assertEqual(message["method"], "tools/call")
            result = self.tool_result
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": message["id"], "result": result},
        )

    def client_factory(self, handler):
        return lambda **kwargs: HTTP_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    def run_cli(self, argv, handler=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(example.httpx, "AsyncClient", self.client_factory(handler or self.respond)),
            patch.dict("os.environ", {"PARALLEL_API_KEY": "must-not-be-used", "API_KEY": "must-not-be-used"}),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = example.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_requests(self, name, arguments):
        calls = []
        for request, message in self.requests:
            self.assertEqual(str(request.url), "https://search.parallel.ai/mcp")
            self.assertEqual(
                request.headers["user-agent"],
                "mcp-agent-parallel-example/1.0 (+https://github.com/Haohao-end/mcp-agent)",
            )
            self.assertNotIn("authorization", request.headers)
            if message["method"] == "tools/call":
                calls.append(message["params"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], name)
        self.assertEqual(calls[0]["arguments"], arguments)
        self.assertEqual(self.requests[0][1]["method"], "initialize")

    def test_search_cli_preserves_sources_and_uses_anonymous_http(self):
        code, stdout, stderr = self.run_cli([
            "search", "Find MCP documentation", "--query", "MCP Python client examples",
            "--query", "MCP Streamable HTTP transport",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertIn("https://example.org/docs", json.loads(stdout)["content"][0]["text"])
        self.assert_requests("web_search", {
            "objective": "Find MCP documentation",
            "search_queries": ["MCP Python client examples", "MCP Streamable HTTP transport"],
        })

    def test_fetch_cli_preserves_structured_content(self):
        self.tool_result["structuredContent"] = {"url": "https://example.org/docs", "excerpts": ["Details"]}
        code, stdout, stderr = self.run_cli([
            "fetch", "https://example.org/docs", "https://example.org/api",
            "--objective", "Read client details",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["structuredContent"]["excerpts"], ["Details"])
        self.assert_requests("web_fetch", {
            "urls": ["https://example.org/docs", "https://example.org/api"],
            "objective": "Read client details",
        })

    def test_fetch_without_objective_uses_service_defaults(self):
        code, _, stderr = self.run_cli(["fetch", "https://example.org/docs"])
        self.assertEqual(code, 0, stderr)
        self.assert_requests("web_fetch", {"urls": ["https://example.org/docs"]})

    def test_tool_error_is_visible_and_exits_nonzero(self):
        self.tool_result = {"content": [{"type": "text", "text": "Usage limit reached"}], "isError": True}
        code, stdout, stderr = self.run_cli(["fetch", "https://example.org/docs"])
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(stdout)["isError"])
        self.assertIn("Usage limit reached", stdout)
        self.assertIn("tool error", stderr)

    def test_connection_failure_exits_nonzero(self):
        def disconnected(request):
            raise httpx.ConnectError("offline", request=request)
        code, stdout, stderr = self.run_cli(["fetch", "https://example.org/docs"], disconnected)
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("request failed", stderr)
        self.assertIn("offline", stderr)

    async def stalled_call(self, request):
        message = json.loads(request.content)
        if message["method"] != "tools/call":
            return await self.respond(request)
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True

    def test_overall_timeout_cancels_inflight_request(self):
        code, stdout, stderr = self.run_cli([
            "--timeout", "0.1", "fetch", "https://example.org/docs",
        ], self.stalled_call)
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("timed out", stderr)
        self.assertTrue(self.cancelled)

    def test_external_cancellation_propagates_and_cleans_up(self):
        async def cancel_request():
            args = example.parse_args(["fetch", "https://example.org/docs"])
            task = asyncio.create_task(example.request(args))
            # Wait until the transport has received the tool call before cancelling.
            started = asyncio.Event()
            async def handler(request):
                if json.loads(request.content)["method"] == "tools/call":
                    started.set()
                return await self.stalled_call(request)
            with patch.object(example.httpx, "AsyncClient", self.client_factory(handler)):
                await asyncio.wait_for(started.wait(), timeout=5)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(self.cancelled)
        asyncio.run(cancel_request())

    def test_invalid_arguments_fail_before_network(self):
        cases = [
            ["search", "objective"],
            ["search", " ", "--query", "query"],
            ["fetch", "file:///tmp/example"],
            ["fetch"] + ["https://example.org"] * 21,
            ["fetch", "https://example.org", "--objective", "x" * 201],
            ["--timeout", "nan", "fetch", "https://example.org"],
            ["--timeout", "0", "fetch", "https://example.org"],
        ]
        for argv in cases:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    example.parse_args(argv)
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
