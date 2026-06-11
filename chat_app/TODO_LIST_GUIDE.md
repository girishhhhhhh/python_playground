# TodoListMiddleware Integration Guide

## Overview
The chat application now includes **TodoListMiddleware** from LangChain, which automatically tracks and manages multi-step tasks.

## Features Added

### 1. **Automatic Todo List Tracking**
- The agent automatically creates and manages todo lists when users request multi-step tasks
- TodoListMiddleware tracks task status: `not-started`, `in-progress`, `completed`

### 2. **Todo List in Response**
Every chat response now includes a `todo_list` field:

```json
{
  "response": "I'll help you build that website...",
  "session_id": "my-session",
  "guardrails_passed": true,
  "violations": null,
  "todo_list": [
    {
      "id": 1,
      "title": "Design homepage layout",
      "status": "completed"
    },
    {
      "id": 2,
      "title": "Create navigation menu",
      "status": "in-progress"
    },
    {
      "id": 3,
      "title": "Add contact form",
      "status": "not-started"
    }
  ]
}
```

### 3. **Terminal Logging**
The server logs show todo lists with visual indicators:

```
📋 Todo List:
  ✅ 1. [completed] Design homepage layout
  ⏳ 2. [in-progress] Create navigation menu
  ⬜ 3. [not-started] Add contact form
```

### 4. **Dedicated Endpoint**
Get the current todo list for any session:

```bash
GET /sessions/{session_id}/todos
```

**Response:**
```json
{
  "session_id": "my-session",
  "todo_list": [...]
}
```

## API Endpoints

### POST /chat
Standard chat with todo list in response

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Help me build a website. First design the layout, then add navigation, finally add a contact form.",
    "session_id": "website-project"
  }'
```

### GET /sessions/{session_id}/todos
Get current todo list

```bash
curl http://localhost:8000/sessions/website-project/todos
```

## Example Usage in Postman

### 1. Send Multi-Step Task
**POST** `http://localhost:8000/chat`

**Headers:**
```
Content-Type: application/json
```

**Body:**
```json
{
  "message": "I need to: 1) Research competitors, 2) Design mockups, 3) Implement features, 4) Test everything",
  "session_id": "project-alpha"
}
```

**Expected Response:**
```json
{
  "response": "I'll help you with that project. Let me break this down...",
  "session_id": "project-alpha",
  "guardrails_passed": true,
  "violations": null,
  "todo_list": [
    {
      "id": 1,
      "title": "Research competitors",
      "status": "in-progress"
    },
    {
      "id": 2,
      "title": "Design mockups",
      "status": "not-started"
    },
    {
      "id": 3,
      "title": "Implement features",
      "status": "not-started"
    },
    {
      "id": 4,
      "title": "Test everything",
      "status": "not-started"
    }
  ]
}
```

### 2. Check Todo List Progress
**GET** `http://localhost:8000/sessions/project-alpha/todos`

**Response:**
```json
{
  "session_id": "project-alpha",
  "todo_list": [
    {
      "id": 1,
      "title": "Research competitors",
      "status": "completed"
    },
    {
      "id": 2,
      "title": "Design mockups",
      "status": "in-progress"
    },
    ...
  ]
}
```

### 3. Continue Conversation
The agent maintains the todo list across messages in the same session:

**POST** `http://localhost:8000/chat`
```json
{
  "message": "I finished the mockups, what's next?",
  "session_id": "project-alpha"
}
```

The agent will update the todo list status and guide you to the next task.

## How TodoListMiddleware Works

1. **Automatic Detection**: When you describe multiple steps or tasks, the middleware automatically creates a todo list
2. **Status Tracking**: As the conversation progresses, task statuses update automatically
3. **Persistence**: Todo lists are stored in PostgreSQL along with conversation history
4. **Context Aware**: The agent uses the todo list to maintain focus and guide multi-step workflows

## Example Prompts That Trigger Todo Lists

✅ **Good prompts:**
- "Help me build X. First do A, then B, finally C"
- "I need to complete these tasks: 1) X, 2) Y, 3) Z"
- "Create a plan to achieve X with multiple steps"
- "Break down how to accomplish X into actionable items"

❌ **Simple prompts** (won't create todos):
- "What's the weather?"
- "Tell me a joke"
- "Explain quantum physics"

## Terminal Output Example

```bash
$ curl -X POST http://localhost:8000/chat ...

# Server logs:
INFO:     127.0.0.1:52000 - "POST /chat HTTP/1.1" 200 OK

📋 Todo List:
  ✅ 1. [completed] Initialize project structure
  ⏳ 2. [in-progress] Set up database
  ⬜ 3. [not-started] Implement API endpoints
  ⬜ 4. [not-started] Write tests
```

## Troubleshooting

### Todo list is empty
- The prompt may not be complex enough to trigger todo creation
- Try explicitly asking for a step-by-step plan
- Use phrases like "First... Second... Third..."

### Todo list not updating
- Ensure you're using the same `session_id` across requests
- Check PostgreSQL is running and connected
- Verify the server logs show the todo list

### Rate Limiting
- Gemini API free tier has limits (20 requests/day for gemini-2.5-flash-lite)
- Wait for the rate limit to reset or upgrade your API plan
- Check: https://ai.google.dev/gemini-api/docs/rate-limits

## Benefits

1. **Task Management**: Automatically track complex multi-step projects
2. **Progress Visibility**: See what's done, what's in progress, what's next
3. **Conversation Continuity**: Agent maintains context across messages
4. **Client Integration**: Easy to build task trackers in your UI using the API

## Next Steps

- Build a UI dashboard to visualize todo lists
- Add task prioritization
- Implement subtasks and dependencies
- Add time estimates and deadlines
