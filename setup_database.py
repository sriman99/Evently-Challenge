"""
Setup database for Evently - creates database if it doesn't exist
"""

import psycopg2
from psycopg2 import sql

# Database configuration
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "sriman"  # As requested by user
DB_NAME = "evently"

def create_database():
    """Create the evently database if it doesn't exist"""

    # Connect to PostgreSQL server
    conn = None
    cursor = None

    try:
        # Connect to default postgres database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database="postgres"
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (DB_NAME,)
        )
        exists = cursor.fetchone()

        if not exists:
            # Create database
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(DB_NAME)
            ))
            print(f"[OK] Database '{DB_NAME}' created successfully!")
        else:
            print(f"[OK] Database '{DB_NAME}' already exists.")

            # Automatically recreate the database for testing
            print("Recreating database for testing...")
            if True:  # Auto-recreate for testing
                # Terminate existing connections
                cursor.execute(sql.SQL("""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """), (DB_NAME,))

                # Drop database
                cursor.execute(sql.SQL("DROP DATABASE {}").format(
                    sql.Identifier(DB_NAME)
                ))

                # Create database
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(DB_NAME)
                ))
                print(f"[OK] Database '{DB_NAME}' recreated successfully!")

        # Update .env file with the password
        env_content = f"""# Database Configuration
DATABASE_URL=postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}
"""

        # Read existing .env file
        try:
            with open('.env', 'r') as f:
                lines = f.readlines()

            # Update DATABASE_URL line
            updated = False
            for i, line in enumerate(lines):
                if line.startswith('DATABASE_URL='):
                    lines[i] = f"DATABASE_URL=postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}\n"
                    updated = True
                    break

            if updated:
                with open('.env', 'w') as f:
                    f.writelines(lines)
                print("[OK] Updated DATABASE_URL in .env file")
        except FileNotFoundError:
            print("[WARNING] .env file not found, please update DATABASE_URL manually")

    except psycopg2.Error as e:
        print(f"[ERROR] Database error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return True

if __name__ == "__main__":
    print("\n>>> Evently Database Setup")
    print("-" * 40)

    if create_database():
        print("\n[OK] Database setup completed!")
        print("\nNext steps:")
        print("1. Run: python seed_database.py")
        print("2. Start the backend: python -m app.main")
    else:
        print("\n[ERROR] Database setup failed!")
        print("Please check your PostgreSQL installation and credentials.")