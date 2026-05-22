import asyncio
import os
import sys
from typing import Any, Optional

# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from mcp.server.models import InitializationOptions
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
import mcp.types as types

# We'll use the MimClient to communicate with the local server
# This assumes api.server is running, or we can use the runtime directly.
# Using runtime directly is safer for an MCP server as it doesn't depend on another process.
from runtime.core import mems, index, runtime, embed_provider, restore_all, VisibilityResolver, cert_index, scope_graph, index_store
from runtime.actor import MemoryActor
from runtime.extractor import DialogueMessage, MockExtractor
import time

server = Server("mim-memory")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="remember",
            description="Store a new memory for a user. Use this when the user explicitly tells you to remember something or when you identify important information.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user (e.g., 'rachel')"},
                    "content": {"type": "string", "description": "The memory content to store"},
                    "memory_type": {"type": "string", "description": "Type of memory (e.g., project, task, fact)", "default": "project"},
                    "tag": {"type": "string", "description": "A tag for categorization", "default": "mcp"},
                },
                "required": ["user_id", "content"],
            },
        ),
        types.Tool(
            name="search",
            description="Search for relevant memories using semantic similarity. Use this to find background information related to the current conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user"},
                    "query": {"type": "string", "description": "The search query (natural language)"},
                    "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
                },
                "required": ["user_id", "query"],
            },
        ),
        types.Tool(
            name="recall",
            description="Recall memories for a user, optionally filtered by tag. Use this for browsing or exact tag lookup.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user"},
                    "tag": {"type": "string", "description": "Optional tag to filter by"},
                },
                "required": ["user_id"],
            },
        ),
        types.Tool(
            name="ingest_dialogue",
            description="Extract memories automatically from a dialogue segment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user"},
                    "text": {"type": "string", "description": "The text or dialogue to extract memories from"},
                },
                "required": ["user_id", "text"],
            },
        ),
        types.Tool(
            name="graph_query",
            description="Perform a Spreading Activation search in the knowledge graph to find non-obvious associations. Use this for deep knowledge discovery.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user"},
                    "query": {"type": "string", "description": "The search query (natural language)"},
                    "max_hops": {"type": "integer", "description": "Maximum number of hops for energy spreading", "default": 3},
                },
                "required": ["user_id", "query"],
            },
        ),
        types.Tool(
            name="auto_context",
            description="Automatically recall relevant MIM context for Claude Code sessions. Use this at the beginning of a task to get relevant historical background.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The unique ID of the user"},
                    "query": {"type": "string", "description": "The current task or query context"},
                    "limit": {"type": "integer", "description": "Maximum number of insights to return", "default": 8},
                },
                "required": ["user_id", "query"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    if not arguments:
        return [types.TextContent(type="text", text="Missing arguments")]

    if name == "remember":
        user_id = arguments["user_id"]
        content = arguments["content"]
        mem_type = arguments.get("memory_type", "project")
        tag = arguments.get("tag", "mcp")

        mem_id = f"mem_mcp_{int(time.time()*1000)}"
        mem = MemoryActor(id=mem_id, owner_id=user_id, content="", memory_type=mem_type, tags=[])
        mems[mem_id] = mem
        runtime.dispatch(mem, "update_content", {"content": content})
        runtime.dispatch(mem, "add_tag", {"tag": tag})
        index_store.save(index)

        return [types.TextContent(type="text", text=f"Memory stored successfully. ID: {mem_id}")]

    elif name == "search":
        user_id = arguments["user_id"]
        query = arguments["query"]
        top_k = arguments.get("top_k", 5)

        raw_results = index.hybrid_query(owner=user_id, query_text=query, provider=embed_provider, top_k=top_k)

        output = []
        for mid, score in raw_results:
            mem = mems.get(mid)
            if mem:
                output.append(f"- [{score:.4f}] {mem.content.value} (Type: {mem.memory_type.value})")

        if not output:
            return [types.TextContent(type="text", text="No relevant memories found.")]

        return [types.TextContent(type="text", text=f"Found {len(output)} relevant memories:\n" + "\n".join(output))]

    elif name == "recall":
        user_id = arguments["user_id"]
        tag = arguments.get("tag")

        vis = VisibilityResolver(cert_index, scope_graph)
        ids = index.query(owner=user_id, tag=tag)

        output = []
        for mid in ids:
            mem = mems.get(mid)
            if mem and vis.object_visible(mem):
                output.append(f"- [{mem.id}] ({mem.memory_type.value}) {mem.content.value}")

        if not output:
            return [types.TextContent(type="text", text="No memories found for this user/tag.")]

        return [types.TextContent(type="text", text=f"User {user_id} has {len(output)} memories:\n" + "\n".join(output))]

    elif name == "ingest_dialogue":
        user_id = arguments["user_id"]
        text = arguments["text"]

        extractor = MockExtractor()
        messages = [DialogueMessage(role="user", content=text)]
        extracted = runtime.ingest_dialogue(user_id, messages, extractor)

        for mem in extracted:
            mems[mem.id] = mem
        index_store.save(index)

        return [types.TextContent(type="text", text=f"Extracted and stored {len(extracted)} memories from the text.")]

    elif name == "graph_query":
        user_id = arguments["user_id"]
        query = arguments["query"]
        max_hops = arguments.get("max_hops", 3)

        results = runtime.graph_query(user_id, query, max_hops=max_hops)

        output = []
        for res in results:
            output.append(f"- [{res['score']:.4f}] {res['id']}: {res['content']} (Path: {res['path']})")

        if not output:
            return [types.TextContent(type="text", text="No associated memories found via graph search.")]

        return [types.TextContent(type="text", text=f"Found {len(output)} associated memories via spreading activation:\n" + "\n".join(output))]

    elif name == "auto_context":
        user_id = arguments["user_id"]
        query = arguments["query"]
        limit = arguments.get("limit", 8)

        # 1. 执行深度图查询
        results = runtime.graph_query(user_id, query, max_hops=3)
        top_results = results[:limit]

        if not top_results:
            return [types.TextContent(type="text", text="No relevant background context found in MIM.")]

        # 2. 构建格式化上下文块
        context_lines = [
            f"[MIM Auto Context]",
            f"User: {user_id}",
            f"Query context: {query}",
            "",
            "Relevant historical memories retrieved from knowledge graph:"
        ]

        for i, res in enumerate(top_results, 1):
            context_lines.append(f"{i}. {res['content']} (Relevance: {res['score']:.2f})")

        context_lines.append("")
        context_lines.append("Use these memories to inform your current responses and maintain continuity.")

        full_context = "\n".join(context_lines)

        return [types.TextContent(type="text", text=full_context)]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    # Load existing state on startup
    restore_all()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mim-memory",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
