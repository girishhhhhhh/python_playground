#!/bin/bash

# Setup script for PostgreSQL with langgraph-checkpoint-postgres
# This script creates the necessary database for the chat application

echo "🔧 Setting up PostgreSQL for LangGraph checkpointing..."
echo ""

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL is not installed"
    echo ""
    echo "To install PostgreSQL on macOS:"
    echo "  brew install postgresql@15"
    echo "  brew services start postgresql@15"
    exit 1
fi

echo "✓ PostgreSQL is installed"

# Check if PostgreSQL is running
if ! pg_isready -h localhost -p 5432 &> /dev/null; then
    echo "⚠️  PostgreSQL is not running"
    echo ""
    echo "To start PostgreSQL:"
    echo "  brew services start postgresql@15"
    echo "  # or"
    echo "  pg_ctl -D /usr/local/var/postgres start"
    exit 1
fi

echo "✓ PostgreSQL is running"

# Create the database
echo ""
echo "Creating 'langgraph' database..."

# Try to create the database (will fail if it already exists, which is fine)
createdb -h localhost -p 5432 -U postgres langgraph 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✓ Database 'langgraph' created successfully"
else
    # Check if database already exists
    if psql -h localhost -p 5432 -U postgres -lqt | cut -d \| -f 1 | grep -qw langgraph; then
        echo "ℹ️  Database 'langgraph' already exists"
    else
        echo "❌ Failed to create database"
        echo ""
        echo "You can manually create it with:"
        echo "  createdb -h localhost -U postgres langgraph"
        exit 1
    fi
fi

# Test connection
echo ""
echo "Testing connection..."
if psql -h localhost -p 5432 -U postgres -d langgraph -c "SELECT 1;" &> /dev/null; then
    echo "✓ Connection successful!"
else
    echo "❌ Could not connect to database"
    exit 1
fi

echo ""
echo "✅ PostgreSQL setup complete!"
echo ""
echo "Connection details:"
echo "  URL: postgresql://postgres@localhost:5432/langgraph"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: langgraph"
echo "  Username: postgres"
echo "  Password: (none)"
echo ""
echo "The application will automatically create the required tables on first run."
