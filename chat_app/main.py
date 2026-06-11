import asyncio
import ssl
import warnings
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Configure SSL before any other imports
# Disable SSL verification globally
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

if not os.environ.get('LANGSMITH_API_KEY'):
    raise RuntimeError("LANGSMITH_API_KEY is not set. Copy chat_app/.env.example to chat_app/.env and fill in your key.")
os.environ.setdefault('LANGSMITH_TRACING', 'false')
os.environ.setdefault('LANGSMITH_PROJECT', 'chat-app-production')

# Patch SSL module to use unverified context
import ssl as ssl_module
ssl_module._create_default_https_context = ssl_module._create_unverified_context

# Disable warnings
warnings.filterwarnings('ignore')

# Monkey patch httpx before it's imported by any library
import httpx
_original_client = httpx.Client
_original_async_client = httpx.AsyncClient

class PatchedClient(httpx.Client):
    def __init__(self, *args, **kwargs):
        kwargs['verify'] = False
        super().__init__(*args, **kwargs)

class PatchedAsyncClient(httpx.AsyncClient):
    def __init__(self, *args, **kwargs):
        kwargs['verify'] = False
        super().__init__(*args, **kwargs)

httpx.Client = PatchedClient
httpx.AsyncClient = PatchedAsyncClient

# Disable urllib3 warnings
try:
    import urllib3
    urllib3.disable_warnings()
except:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
import uvicorn
from chat_handler import ChatHandler
from langserve import add_routes
from langchain_core.runnables import RunnableSerializable, RunnableConfig
from datetime import datetime
import uuid
import json

app = FastAPI(title="LangChain Chat Application")

# Add CORS middleware to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_handler = None

# In-memory storage for threads (for demo purposes)
# In production, this should use a real database
threads_storage = {}


# Define explicit input/output schemas for LangServe  
class LangServeInput(BaseModel):
    """Input schema for LangServe agent"""
    messages: List[dict] = Field(description="List of messages in the conversation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {"role": "user", "content": "Hello, how are you?"}
                ]
            }
        }


class LangServeOutput(BaseModel):
    """Output schema for LangServe agent"""
    messages: List[dict] = Field(description="List of messages including the response")


# Create a wrapper runnable with fixed schemas
class AgentWrapper(RunnableSerializable[Dict, Dict]):
    """Wrapper around agent that provides clean schemas for LangServe"""
    
    agent: Any
    
    class Config:
        arbitrary_types_allowed = True
    
    def invoke(self, input: Dict, config: Optional[RunnableConfig] = None) -> Dict:
        """Synchronous invoke"""
        # Normalize input format
        if "messages" not in input:
            # If input is a string or single message, wrap it
            if isinstance(input, str):
                input = {"messages": [{"role": "user", "content": input}]}
            else:
                # Try to extract content from malformed input
                content = input.get("", input.get("content", str(input)))
                input = {"messages": [{"role": "user", "content": content}]}
        
        # Ensure messages have proper format
        messages = input["messages"]
        normalized_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                # Ensure role and content keys exist
                if "role" not in msg and "content" not in msg:
                    # Malformed message, try to extract content
                    content = list(msg.values())[0] if msg else ""
                    normalized_messages.append({"role": "user", "content": str(content)})
                else:
                    normalized_messages.append(msg)
            elif isinstance(msg, str):
                normalized_messages.append({"role": "user", "content": msg})
            else:
                normalized_messages.append({"role": "user", "content": str(msg)})
        
        input["messages"] = normalized_messages
        
        # Ensure config has thread_id for checkpointer
        if config is None:
            config = {"configurable": {"thread_id": "default"}}
        elif "configurable" not in config:
            config["configurable"] = {"thread_id": "default"}
        elif "thread_id" not in config.get("configurable", {}):
            config["configurable"]["thread_id"] = "default"
        
        result = self.agent.invoke(input, config)
        return {"messages": result.get("messages", [])}
    
    async def ainvoke(self, input: Dict, config: Optional[RunnableConfig] = None) -> Dict:
        """Asynchronous invoke"""
        # Normalize input format
        if "messages" not in input:
            # If input is a string or single message, wrap it
            if isinstance(input, str):
                input = {"messages": [{"role": "user", "content": input}]}
            else:
                # Try to extract content from malformed input
                content = input.get("", input.get("content", str(input)))
                input = {"messages": [{"role": "user", "content": content}]}
        
        # Ensure messages have proper format
        messages = input["messages"]
        normalized_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                # Ensure role and content keys exist
                if "role" not in msg and "content" not in msg:
                    # Malformed message, try to extract content
                    content = list(msg.values())[0] if msg else ""
                    normalized_messages.append({"role": "user", "content": str(content)})
                else:
                    normalized_messages.append(msg)
            elif isinstance(msg, str):
                normalized_messages.append({"role": "user", "content": msg})
            else:
                normalized_messages.append({"role": "user", "content": str(msg)})
        
        input["messages"] = normalized_messages
        
        # Ensure config has thread_id for checkpointer
        if config is None:
            config = {"configurable": {"thread_id": "default"}}
        elif "configurable" not in config:
            config["configurable"] = {"thread_id": "default"}
        elif "thread_id" not in config.get("configurable", {}):
            config["configurable"]["thread_id"] = "default"
        
        result = await self.agent.ainvoke(input, config)
        return {"messages": result.get("messages", [])}
    
    def get_input_schema(self, config: Optional[RunnableConfig] = None) -> type[BaseModel]:
        """Return fixed input schema"""
        return LangServeInput
    
    def get_output_schema(self, config: Optional[RunnableConfig] = None) -> type[BaseModel]:
        """Return fixed output schema"""
        return LangServeOutput


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = "default_user"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    guardrails_passed: bool
    violations: Optional[list] = None
    todo_list: Optional[list] = None


@app.on_event("startup")
async def startup_event():
    """Initialize chat handler on startup"""
    global chat_handler
    chat_handler = ChatHandler()
    await chat_handler.initialize()
    
    # Wrap agent with custom wrapper that provides clean schemas for LangServe
    # This avoids schema introspection issues with NotRequired fields from TodoListMiddleware
    wrapped_agent = AgentWrapper(agent=chat_handler.agent)
    
    # Add LangServe routes to expose agent with playground UI
    # Using /agent path to avoid conflict with FastAPI /chat endpoint
    add_routes(
        app,
        wrapped_agent,
        path="/agent",
        enabled_endpoints=["invoke", "stream", "stream_log", "playground"],
    )
    
    print("✓ Chat application initialized successfully")
    print("✓ LangServe playground available at /agent/playground")
    print("✓ LangServe agent endpoints: /agent/invoke, /agent/stream")
    print("✓ FastAPI chat endpoint available at POST /chat (with guardrails & session management)")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if chat_handler:
        await chat_handler.cleanup()
    print("✓ Chat application shut down")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "online", "message": "LangChain Chat Application"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint that handles user messages with guardrails
    """
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")

    try:
        result = await chat_handler.process_message(
            message=request.message,
            session_id=request.session_id,
            user_id=request.user_id
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}")
async def get_session_history(session_id: str):
    """Get conversation history for a session"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")

    try:
        history = await chat_handler.get_session_history(session_id)
        return {"session_id": session_id, "history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear a specific session"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")
    
    try:
        await chat_handler.clear_session(session_id)
        return {"message": f"Session {session_id} cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# LangGraph SDK-compatible endpoints for my-chat-ui frontend
@app.post("/threads/search")
async def search_threads(limit: int = 10, offset: int = 0):
    """Search/list threads - LangGraph SDK compatible endpoint"""
    # Return list of threads from storage
    thread_list = list(threads_storage.values())
    return thread_list[offset:offset+limit]


@app.post("/threads")
async def create_thread():
    """Create a new thread - LangGraph SDK compatible endpoint"""
    thread_id = str(uuid.uuid4())
    thread = {
        "thread_id": thread_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "metadata": {}
    }
    threads_storage[thread_id] = thread
    return thread


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get thread by ID - LangGraph SDK compatible endpoint"""
    if thread_id not in threads_storage:
        raise HTTPException(status_code=404, detail="Thread not found")
    return threads_storage[thread_id]


@app.post("/threads/{thread_id}/history")
async def get_thread_history(thread_id: str):
    """Get conversation history for a thread - LangGraph SDK compatible endpoint"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")
    
    try:
        # Use the existing session history functionality
        # Thread ID maps to session ID in our implementation
        history = await chat_handler.get_session_history(thread_id)
        
        # Transform history to LangGraph SDK format (array of checkpoint states)
        # Each checkpoint needs: checkpoint_id, parent_checkpoint_id, values, next, etc.
        if not isinstance(history, list):
            history = []
        
        checkpoints = []
        parent_id = None
        for idx, msg in enumerate(history):
            checkpoint_id = str(uuid.uuid4())
            checkpoint = {
                "checkpoint_id": checkpoint_id,
                "checkpoint_ns": "",
                "parent_checkpoint_id": parent_id,
                "values": {"messages": [msg] if isinstance(msg, dict) else []},
                "next": [],
                "metadata": {
                    "step": idx,
                    "source": "input" if idx % 2 == 0 else "loop",
                    "writes": None
                },
                "created_at": datetime.now().isoformat(),
                "thread_id": thread_id
            }
            checkpoints.append(checkpoint)
            parent_id = checkpoint_id
        
        return checkpoints
    except Exception as e:
        # If no history exists yet, return empty array
        return []


@app.post("/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, request: dict):
    """Stream agent run - LangGraph SDK compatible endpoint"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not initialized")
    
    # Ensure thread exists
    if thread_id not in threads_storage:
        threads_storage[thread_id] = {
            "thread_id": thread_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": {}
        }
    
    # Process message using existing chat handler
    input_data = request.get("input", {})
    messages = input_data.get("messages", [])
    
    async def generate_stream():
        if messages:
            last_message = messages[-1]
            message_content = last_message.get("content", "")
            
            # Use the chat endpoint logic
            result = await chat_handler.process_message(
                message=message_content,
                session_id=thread_id,
                user_id="default_user"
            )
            
            # Update thread timestamp
            threads_storage[thread_id]["updated_at"] = datetime.now().isoformat()
            
            # Send events in LangGraph SDK stream format
            # Event 1: metadata
            yield json.dumps({
                "event": "metadata",
                "data": {"run_id": str(uuid.uuid4())}
            }) + "\n"
            
            # Event 2: values with the response
            yield json.dumps({
                "event": "values",
                "data": {
                    "messages": [
                        {"role": "user", "content": message_content},
                        {"role": "assistant", "content": result["response"]}
                    ]
                }
            }) + "\n"
            
            # Event 3: end
            yield json.dumps({
                "event": "end",
                "data": {}
            }) + "\n"
        else:
            yield json.dumps({"error": "No messages provided"}) + "\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream"
    )


@app.post("/assistants/search")
async def search_assistants():
    """Search assistants - LangGraph SDK compatible endpoint"""
    # Return a single assistant for the agent
    return [{
        "assistant_id": "agent",
        "graph_id": "agent",
        "name": "Chat Agent",
        "description": "LangChain chat agent with guardrails and todo tracking",
        "config": {},
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }]


@app.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str):
    """Get assistant by ID - LangGraph SDK compatible endpoint"""
    if assistant_id != "agent":
        raise HTTPException(status_code=404, detail="Assistant not found")
    
    return {
        "assistant_id": "agent",
        "graph_id": "agent",
        "name": "Chat Agent",
        "description": "LangChain chat agent with guardrails and todo tracking",
        "config": {},
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }


@app.get("/assistants/{assistant_id}/schemas")
async def get_assistant_schemas(assistant_id: str):
    """Get assistant schemas - LangGraph SDK compatible endpoint"""
    if assistant_id != "agent":
        raise HTTPException(status_code=404, detail="Assistant not found")
    
    return {
        "config_schema": {},
        "input_schema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            }
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object"
                    }
                }
            }
        }
    }


@app.get("/info")
async def get_info():
    """Get API info - LangGraph SDK compatible endpoint"""
    return {
        "version": "1.0.0",
        "type": "langgraph-api"
    }


async def run_app():
    """Run FastAPI app using asyncio"""
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(run_app())
