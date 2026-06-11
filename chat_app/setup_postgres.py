"""
Setup script for PostgreSQL with langgraph-checkpoint-postgres
This script creates the necessary database for the chat application
"""

import subprocess
import sys
import os


def run_command(cmd, capture_output=True):
    """Run a shell command and return success status"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=capture_output,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_postgres_installed():
    """Check if PostgreSQL is installed"""
    success, _, _ = run_command("psql --version")
    return success


def check_postgres_running():
    """Check if PostgreSQL is running"""
    success, _, _ = run_command("pg_isready -h localhost -p 5432")
    return success


def create_database():
    """Create the langgraph database"""
    success, stdout, stderr = run_command(
        "createdb -h localhost -p 5432 -U postgres langgraph"
    )
    return success


def check_database_exists():
    """Check if the langgraph database exists"""
    success, stdout, stderr = run_command(
        "psql -h localhost -p 5432 -U postgres -lqt"
    )
    if success and stdout:
        databases = [line.split('|')[0].strip() for line in stdout.split('\n')]
        return 'langgraph' in databases
    return False


def test_connection():
    """Test connection to the database"""
    success, _, _ = run_command(
        'psql -h localhost -p 5432 -U postgres -d langgraph -c "SELECT 1;"'
    )
    return success


def main():
    print("🔧 Setting up PostgreSQL for LangGraph checkpointing...")
    print()

    # Check if PostgreSQL is installed
    print("Checking PostgreSQL installation...")
    if not check_postgres_installed():
        print("❌ PostgreSQL is not installed")
        print()
        print("To install PostgreSQL on macOS:")
        print("  brew install postgresql@15")
        print("  brew services start postgresql@15")
        print()
        print("To install PostgreSQL on Ubuntu/Debian:")
        print("  sudo apt-get install postgresql postgresql-contrib")
        print("  sudo systemctl start postgresql")
        sys.exit(1)
    
    print("✓ PostgreSQL is installed")

    # Check if PostgreSQL is running
    print("Checking if PostgreSQL is running...")
    if not check_postgres_running():
        print("⚠️  PostgreSQL is not running")
        print()
        print("To start PostgreSQL:")
        print("  macOS: brew services start postgresql@15")
        print("  Linux: sudo systemctl start postgresql")
        sys.exit(1)
    
    print("✓ PostgreSQL is running")

    # Create the database
    print()
    print("Creating 'langgraph' database...")
    
    if check_database_exists():
        print("ℹ️  Database 'langgraph' already exists")
    else:
        if create_database():
            print("✓ Database 'langgraph' created successfully")
        else:
            print("❌ Failed to create database")
            print()
            print("You may need to configure PostgreSQL to allow connections")
            print("without a password for the 'postgres' user.")
            print()
            print("You can manually create it with:")
            print("  createdb -h localhost -U postgres langgraph")
            sys.exit(1)

    # Test connection
    print()
    print("Testing connection...")
    if test_connection():
        print("✓ Connection successful!")
    else:
        print("❌ Could not connect to database")
        print("Please check your PostgreSQL configuration")
        sys.exit(1)

    print()
    print("✅ PostgreSQL setup complete!")
    print()
    print("Connection details:")
    print("  URL: postgresql://postgres@localhost:5432/langgraph")
    print("  Host: localhost")
    print("  Port: 5432")
    print("  Database: langgraph")
    print("  Username: postgres")
    print("  Password: (none)")
    print()
    print("The application will automatically create the required tables on first run.")


if __name__ == "__main__":
    main()
