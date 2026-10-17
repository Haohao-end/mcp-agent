# Parallel MCP web research example

Search current web sources and fetch page excerpts using
[Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
at `https://search.parallel.ai/mcp`. This standalone example demonstrates the
MCP SDK's Streamable HTTP transport. It calls the tools directly, without an LLM
or local MCP server.

Anonymous search uses Fast mode and needs no account or API key. Free access has
usage limits and is intended for exploration and light use. The example does not
read `.env` files or use saved credentials. Queries and requested page URLs are
sent to Parallel. The existing weather, You.com search and RAG clients remain
unchanged.

## Setup

Use Python 3.10+ and run these commands from the repository root:

```bash
python -m venv examples/parallel_search/.venv
source examples/parallel_search/.venv/bin/activate
python -m pip install -r examples/parallel_search/requirements.txt
```

On Windows, activate with `examples\parallel_search\.venv\Scripts\activate`
instead. Only the MCP SDK and HTTP client are needed; the LangChain, embedding
and vector-store dependencies are unnecessary for this example.

## Search and read sources

Give search one focused objective and one or more related keyword queries:

```bash
python examples/parallel_search/client.py search \
  "Find the Python MCP SDK documentation for Streamable HTTP clients" \
  --query "MCP Python Streamable HTTP client" \
  --query "MCP Python SDK client examples"
```

The command prints the MCP result as JSON, with source URLs and excerpts in the
tool content. If those excerpts answer the question, no fetch is needed. When
you need details from a particular page, pass its URL to `fetch`:

```bash
python examples/parallel_search/client.py fetch \
  https://github.com/modelcontextprotocol/python-sdk \
  --objective "Find the Streamable HTTP client example"
```

Fetch accepts up to 20 HTTP/HTTPS URLs and an optional objective of up to 200
characters. It uses the service's default excerpt mode rather than requesting
full pages. These commands return tool results for you to read or pass to your
own application; they do not run a conversation or modify the existing agents.

The default deadline for connecting and calling a tool is 60 seconds. Set it
before the subcommand, for example `client.py --timeout 90 search ...`. Transport
errors, timeouts and MCP tool errors exit with status 1; tool-error JSON is kept
on standard output. Ctrl+C cancels the request. If the service reports a usage
limit, wait as directed by the response before trying again.

## Offline checks

After setup, run the transport tests without making live requests:

```bash
python -m unittest discover -s examples/parallel_search/tests -v
```
