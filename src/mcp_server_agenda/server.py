import asyncio
import subprocess
from urllib.parse import quote

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Store notes as a simple key-value dict to demonstrate state management
notes: dict[str, str] = {}

server = Server("mcp-server-agenda")

class XCallbackURLHandler:
    """Handles x-callback-url execution on macOS systems."""
    
    @staticmethod
    def call_url(url: str) -> str:
        """
        Executes an x-callback-url on macOS using the 'open' command.
        """
        try:
            # Execute the URL using the macOS 'open' command without additional encoding
            # The URL parameters should already be properly encoded
            result = subprocess.run(
                ['open', url],
                check=True,
                capture_output=True,
                text=True
            )
            
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to execute x-callback-url: {e}")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=AnyUrl(f"note://internal/{name}"),
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific note's content by its URI.
    The note name is extracted from the URI host component.
    """
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        return notes[name]
    raise ValueError(f"Note not found: {name}")

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
    return [
        types.Prompt(
            name="summarize-notes",
            description="Creates a summary of all notes",
            arguments=[
                types.PromptArgument(
                    name="style",
                    description="Style of the summary (brief/detailed)",
                    required=False,
                )
            ],
        )
    ]

@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    The prompt includes all current notes and can be customized via arguments.
    """
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
                    + "\n".join(
                        f"- {name}: {content}"
                        for name, content in notes.items()
                    ),
                ),
            )
        ],
    )

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        ),
        types.Tool(
            name="create-agenda-note",
            description="Create a note in Agenda",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                    "project_title": {"type": "string"},
                    "on_the_agenda": {"type": "boolean"},
                    "date": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "template_name": {"type": "string"},
                    "template_input": {"type": "string"},
                    "collapsed": {"type": "boolean"},
                    "completed": {"type": "boolean"},
                    "pinned": {"type": "boolean"},
                    "footnote": {"type": "boolean"},
                    "select": {"type": "boolean"},
                },
                "required": ["title", "text"],
            },
        ),
        types.Tool(
            name="create-agenda-project",
            description="Create a new project in Agenda",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category_title": {"type": "string"},
                    "identifier": {"type": "string"},
                    "select": {"type": "boolean"},
                    "sort_order": {
                        "type": "string",
                        "enum": ["newest-first", "oldest-first"]
                    }
                },
                "required": ["title"]
            },
        ),
        types.Tool(
            name="open-agenda-note",
            description="Open a note in Agenda",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "identifier": {"type": "string"},
                    "project_title": {"type": "string"},
                    "separate_window": {"type": "boolean"}
                },
                # No required fields since either title or identifier can be used
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name == "add-note":
        if not arguments:
            raise ValueError("Missing arguments")

        note_name = arguments.get("name")
        content = arguments.get("content")

        if not note_name or not content:
            raise ValueError("Missing name or content")

        # Update server state
        notes[note_name] = content

        # Notify clients that resources have changed
        await server.request_context.session.send_resource_list_changed()

        return [
            types.TextContent(
                type="text",
                text=f"Added note '{note_name}' with content: {content}",
            )
        ]
    
    elif name == "create-agenda-note":
        if not arguments:
            raise ValueError("Missing arguments")

        # Build the x-callback URL
        base_url = "agenda://x-callback-url/create-note"
        params = []
        
        # Required parameters
        params.append(f"title={quote(arguments['title'])}")
        params.append(f"text={quote(arguments['text'])}")
        
        # Optional parameters
        if "project_title" in arguments:
            params.append(f"project-title={quote(arguments['project_title'])}")
        if "on_the_agenda" in arguments:
            params.append(f"on-the-agenda={str(arguments['on_the_agenda']).lower()}")
        if "date" in arguments:
            params.append(f"date={quote(arguments['date'])}")
        if "start_date" in arguments:
            params.append(f"start-date={quote(arguments['start_date'])}")
        if "end_date" in arguments:
            params.append(f"end-date={quote(arguments['end_date'])}")
        if "template_name" in arguments:
            params.append(f"template-name={quote(arguments['template_name'])}")
        if "template_input" in arguments:
            params.append(f"template-input={quote(arguments['template_input'])}")
        if "collapsed" in arguments:
            params.append(f"collapsed={str(arguments['collapsed']).lower()}")
        if "completed" in arguments:
            params.append(f"completed={str(arguments['completed']).lower()}")
        if "pinned" in arguments:
            params.append(f"pinned={str(arguments['pinned']).lower()}")
        if "footnote" in arguments:
            params.append(f"footnote={str(arguments['footnote']).lower()}")
        if "select" in arguments:
            params.append(f"select={str(arguments['select']).lower()}")
        
        url = f"{base_url}?{'&'.join(params)}"
        
        # Execute the x-callback URL
        try:
            XCallbackURLHandler.call_url(url)
            return [
                types.TextContent(
                    type="text",
                    text=f"Created note '{arguments['title']}' in Agenda",
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to create note in Agenda: {str(e)}",
                )
            ]
    
    elif name == "create-agenda-project":
        if not arguments:
            raise ValueError("Missing arguments")

        # Build the x-callback URL
        base_url = "agenda://x-callback-url/create-project"
        params = []
        
        # Required parameters
        params.append(f"title={quote(arguments['title'])}")
        
        # Optional parameters
        if "category_title" in arguments:
            params.append(f"category-title={quote(arguments['category_title'])}")
        if "identifier" in arguments:
            params.append(f"identifier={quote(arguments['identifier'])}")
        if "select" in arguments:
            params.append(f"select={str(arguments['select']).lower()}")
        if "sort_order" in arguments:
            params.append(f"sort-order={arguments['sort_order']}")
        
        url = f"{base_url}?{'&'.join(params)}"
        
        # Execute the x-callback URL
        try:
            XCallbackURLHandler.call_url(url)
            return [
                types.TextContent(
                    type="text",
                    text=f"Created project '{arguments['title']}' in Agenda",
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to create project in Agenda: {str(e)}",
                )
            ]
    
    elif name == "open-agenda-note":
        if not arguments:
            raise ValueError("Missing arguments")
        
        if not any(key in arguments for key in ["title", "identifier"]):
            raise ValueError("Either title or identifier must be provided")

        # Build the x-callback URL
        base_url = "agenda://x-callback-url/open-note"
        params = []
        
        # Optional parameters
        if "title" in arguments:
            params.append(f"title={quote(arguments['title'])}")
        if "identifier" in arguments:
            params.append(f"identifier={quote(arguments['identifier'])}")
        if "project_title" in arguments:
            params.append(f"project-title={quote(arguments['project_title'])}")
        if "separate_window" in arguments:
            params.append(f"separate-window={str(arguments['separate_window']).lower()}")
        
        url = f"{base_url}?{'&'.join(params)}"
        
        # Execute the x-callback URL
        try:
            XCallbackURLHandler.call_url(url)
            note_desc = arguments.get('title', arguments.get('identifier', 'requested note'))
            return [
                types.TextContent(
                    type="text",
                    text=f"Opened note '{note_desc}' in Agenda",
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to open note in Agenda: {str(e)}",
                )
            ]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-server-agenda",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )