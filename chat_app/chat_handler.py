import os
from typing import Dict, Any
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware, ModelCallLimitMiddleware
from guardrails import Guard
import json


class ChatHandler:
    def __init__(self):
        self.llm = None
        self.checkpointer = None
        self.checkpointer_cm = None
        self.agent = None
        self.input_guard = None
        self.output_guard = None
        
    async def initialize(self):
        """Initialize all components"""
        print("Step 1: Initializing HuggingFace model...")
        # Initialize HuggingFace model using init_chat_model
        # Set HuggingFace API token in environment
        os.environ["GOOGLE_API_KEY"] = "AIzaSyD44svfNi_xxGw4QHmKfcicefSFKUanbqM"
        
        self.llm  = init_chat_model(
            model="google_genai:gemini-2.5-flash-lite",
            max_tokens=1024,
            temperature=0.7,
        )
        print("✓ HuggingFace model initialized")
        
        print("Step 2: Setting up PostgreSQL checkpointer...")
        # Initialize PostgreSQL checkpointer with connection string
        # postgresql://username@host:port/database
        postgres_url = "postgresql://postgres@localhost:5432/langgraph"
        
        try:
            # Create the PostgreSQL checkpointer
            # Store the context manager and enter it
            self.checkpointer_cm = AsyncPostgresSaver.from_conn_string(postgres_url)
            self.checkpointer = await self.checkpointer_cm.__aenter__()
            
            # Setup the database tables
            await self.checkpointer.setup()
            print("✓ PostgreSQL checkpointer initialized successfully")
        except Exception as e:
            print(f"⚠️  Warning: Could not connect to PostgreSQL: {e}")
            print("ℹ️  Continuing without persistent storage")
            print("ℹ️  To enable persistence, ensure PostgreSQL is running on localhost:5432")
            print("ℹ️  and the 'langgraph' database exists")
            self.checkpointer = None
            self.checkpointer_cm = None
        
        # Initialize guardrails with guardrails-ai
        # Using basic guardrails - add validators with guard.use() or install hub validators
        # Example: guard.use(ValidatorClass(...))
        # Or install hub validators: guardrails hub install hub://guardrails/detect_pii
        self.input_guard = Guard()
        self.output_guard = Guard()
        print("✓ Guardrails initialized (add validators with guard.use() if needed)")
        
        print("Step 3: Creating agent with checkpointer and middleware...")
        # Create agent with model, tools, checkpointer, and middleware
        # TodoListMiddleware helps manage multi-step tasks
        self.agent = create_agent(
            self.llm,
            tools=[],  # Add your tools here if needed
            checkpointer=self.checkpointer,
            system_prompt=(
                "You are a helpful AI assistant. When given a multi-step task:\n"
                "1. Break it down into steps internally\n"
                "2. COMPLETE each step fully\n"
                "3. Actually perform the work for each task\n"
                "4. Continue until ALL steps are completed\n"
                "5. Provide ONLY the final answer/result in your response\n\n"
                "IMPORTANT: Do NOT include todo lists, step-by-step breakdowns, or markdown tables in your response. "
                "Only provide the direct answer to the user's question."
            ),
            middleware=[TodoListMiddleware(), ModelCallLimitMiddleware(thread_limit=50, run_limit=25, exit_behavior="end")],
            debug=True,
        )
        print("✓ Agent created successfully with TodoListMiddleware")
        
        print("✓ Chat handler initialized successfully")
    
    async def process_message(
        self, 
        message: str, 
        session_id: str,
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Process a chat message with memory and guardrails"""
        
        # Check input guardrails (skipped if no validators configured)
        # To add validators: guard.use(ValidatorClass(...))
        # Or install hub validators: guardrails hub install hub://guardrails/detect_pii
        if self.input_guard:
            try:
                result = self.input_guard.validate(message)
                # If validation fails, result will have failures
                if result.validation_passed is False:
                    return {
                        "response": "I cannot process this message due to content policy violations.",
                        "session_id": session_id,
                        "guardrails_passed": False,
                        "violations": [str(f) for f in result.raw_llm_output if hasattr(result, 'raw_llm_output')]
                    }
            except Exception:
                # No validators configured, skip validation
                pass
        
        # Configure the agent with thread_id for memory persistence and recursion limit
        # Include LangSmith tracing metadata
        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": 25,  # Maximum loop iterations per request (increased for simple queries)
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": "production"
            },
            "tags": ["chat", "user-interaction", f"user:{user_id}"]
        }
        
        # Invoke the agent - it automatically handles memory via checkpointer
        try:
            result = await self.agent.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                config=config
            )
            # Extract the AI response from agent result
            ai_response = result["messages"][-1].content
            
            
            # Get the agent state to extract todo list
            state = await self.agent.aget_state(config)
            todo_list = state.values.get("todos", [])  # Fixed: Use 'todos' not 'todo_list'
            
            # Debug: Print state keys to understand structure
            # print(f"\n🔍 Debug: State keys available: {list(state.values.keys())}")
            # print(f"🔍 Debug: Todo list from state: {todo_list}")
            
            # Log todo list if it exists
            # if todo_list:
            #     print("\n📋 Todo List:")
            #     for idx, todo in enumerate(todo_list, 1):
            #         status = todo.get("status", "unknown")
            #         title = todo.get("content", todo.get("title", "Untitled"))  # TodoListMiddleware uses 'content'
            #         # Handle both 'in-progress' and 'in_progress' status values
            #         status_icon = "✅" if status == "completed" else "⏳" if status in ["in-progress", "in_progress"] else "⬜"
            #         print(f"  {status_icon} {idx}. [{status}] {title}")
            #     print()
            # else:
            #     print("ℹ️  No structured todo list found in agent state (todos may be in response text only)")
        except Exception as e:
            return {
                "response": f"Error generating response: {str(e)}",
                "session_id": session_id,
                "guardrails_passed": False,
                "violations": [f"Agent error: {str(e)}"]
            }
        
        # Check output guardrails (skipped if no validators configured)
        if self.output_guard:
            try:
                result = self.output_guard.validate(ai_response)
                # If validation fails, result will have failures
                if result.validation_passed is False:
                    return {
                        "response": "I apologize, but I cannot provide that response due to content policy violations.",
                        "session_id": session_id,
                        "guardrails_passed": False,
                        "violations": [str(f) for f in result.raw_llm_output if hasattr(result, 'raw_llm_output')]
                    }
            except Exception:
                # No validators configured, skip validation
                pass
        
        # Get final state with todo list
        final_state = await self.agent.aget_state(config)
        todo_list = final_state.values.get("todos", [])  # Fixed: Use 'todos' not 'todo_list'
        
        return {
            "response": ai_response,
            "session_id": session_id,
            "guardrails_passed": True,
            "violations": None,
            "todo_list": todo_list
        }
    
    async def get_session_history(self, session_id: str):
        """Get conversation history for a session"""
        config = {"configurable": {"thread_id": session_id}}
        
        if not self.checkpointer:
            return []
        
        try:
            # Get the state from the agent's checkpointer
            state = await self.agent.aget_state(config)
            messages = state.values.get("messages", [])
            
            history = []
            for msg in messages:
                if hasattr(msg, 'type'):
                    if msg.type == "human":
                        history.append({"role": "user", "content": msg.content})
                    elif msg.type == "ai":
                        history.append({"role": "assistant", "content": msg.content})
            
            return history
        except Exception as e:
            print(f"Warning: Could not retrieve history: {e}")
            return []
    
    async def clear_session(self, session_id: str):
        """Clear a specific session"""
        config = {"configurable": {"thread_id": session_id}}
        
        if self.checkpointer:
            try:
                # Update the state to empty messages
                await self.agent.aupdate_state(config, {"messages": []})
            except Exception as e:
                print(f"Warning: Could not clear session: {e}")
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.checkpointer_cm:
            try:
                # Exit the async context manager
                await self.checkpointer_cm.__aexit__(None, None, None)
            except Exception as e:
                print(f"Warning: Error closing checkpointer: {e}")
        print("✓ Chat handler cleaned up")
