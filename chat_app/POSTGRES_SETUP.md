# PostgreSQL Setup for LangGraph Checkpointing

This application uses `langgraph-checkpoint-postgres` to persist conversation history and checkpoints in PostgreSQL.

## Connection Details

- **Database URL**: `postgresql://postgres@localhost:5432/langgraph`
- **Host**: localhost
- **Port**: 5432
- **Database**: langgraph
- **Username**: postgres
- **Password**: (none)

## Quick Setup

### Option 1: Using the Python Setup Script

```bash
python setup_postgres.py
```

### Option 2: Using the Bash Setup Script

```bash
./setup_postgres.sh
```

### Option 3: Manual Setup

1. **Install PostgreSQL** (if not already installed):
   
   macOS:
   ```bash
   brew install postgresql@15
   brew services start postgresql@15
   ```
   
   Ubuntu/Debian:
   ```bash
   sudo apt-get install postgresql postgresql-contrib
   sudo systemctl start postgresql
   ```

2. **Create the database**:
   ```bash
   createdb -h localhost -U postgres langgraph
   ```

3. **Verify the connection**:
   ```bash
   psql -h localhost -U postgres -d langgraph -c "SELECT 1;"
   ```

## How It Works

1. The application automatically connects to PostgreSQL on startup
2. On first run, it creates the necessary tables using `checkpointer.setup()`
3. Conversation history is stored by session_id (thread_id)
4. Each message is persisted to the database as it's processed

## Features

- **Persistent Memory**: Conversations are saved across application restarts
- **Session Management**: Each session_id has its own conversation thread
- **Automatic Failover**: If PostgreSQL is unavailable, the app falls back to in-memory storage

## Checking Connection Status

When you start the application, you'll see:

✅ **If PostgreSQL is available**:
```
Step 2: Setting up PostgreSQL checkpointer...
✓ PostgreSQL checkpointer initialized successfully
```

⚠️ **If PostgreSQL is unavailable**:
```
Step 2: Setting up PostgreSQL checkpointer...
⚠️  Warning: Could not connect to PostgreSQL: [error message]
ℹ️  Continuing without persistent storage
```

## Testing the Setup

1. Start the application:
   ```bash
   python main.py
   ```

2. Send a chat message:
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Hello, remember this conversation",
       "session_id": "test-session-1"
     }'
   ```

3. Restart the application and retrieve the session history:
   ```bash
   curl http://localhost:8000/sessions/test-session-1
   ```

   You should see the previous conversation history.

## Troubleshooting

### Error: "could not connect to server"

PostgreSQL is not running. Start it with:
```bash
brew services start postgresql@15  # macOS
sudo systemctl start postgresql    # Linux
```

### Error: "database does not exist"

Create the database:
```bash
createdb -h localhost -U postgres langgraph
```

### Error: "password authentication failed"

The PostgreSQL user 'postgres' requires a password. You have two options:

1. **Configure PostgreSQL to allow passwordless local connections** (recommended for development):
   
   Edit `pg_hba.conf` and change:
   ```
   local   all   postgres   peer
   ```
   to:
   ```
   local   all   postgres   trust
   ```

2. **Add a password to the connection string**:
   
   In `chat_handler.py`, update:
   ```python
   postgres_url = "postgresql://postgres:your_password@localhost:5432/langgraph"
   ```

## Database Schema

The checkpointer automatically creates the necessary tables:

- `checkpoints`: Stores conversation state and messages
- `checkpoint_writes`: Stores checkpoint write operations

You can inspect them with:
```bash
psql -h localhost -U postgres -d langgraph -c "\dt"
```

## Advanced Configuration

### Changing the Database Name

In `chat_handler.py`, update the connection URL:
```python
postgres_url = "postgresql://postgres@localhost:5432/your_database_name"
```

### Using a Remote PostgreSQL Server

Update the connection URL with your server details:
```python
postgres_url = "postgresql://username:password@hostname:5432/database"
```

### Connection Pooling

The `AsyncPostgresSaver` automatically handles connection pooling for optimal performance.
