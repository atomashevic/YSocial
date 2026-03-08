"""
Runtime PostgreSQL schema migration script.

This migration ensures PostgreSQL databases have all required tables and columns
that may be missing compared to the SQLite schema. It runs automatically at startup
when using --db postgresql.

Tables checked/created:
- image_posts (server database)

Columns checked/added:
- websites.fetch_images_from_url, websites.fetch_images_timeout (server database)
- images.remote_article_id (server database)
- post.image_post_id (server database) - links posts to standalone images
- post.created_at (server database) - real wall-clock creation timestamp
- post.dedupe_key, post.client_action_id (server database) - idempotent comment creation
- pages.fetch_images_from_url, pages.fetch_images_timeout (dashboard database)
- client.initial_agents (dashboard database)
"""

import os

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def _column_exists(cursor, table_name, column_name):
    """Check if a column exists in a PostgreSQL table."""
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def _table_exists(cursor, table_name):
    """Check if a table exists in PostgreSQL."""
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name = %s AND table_schema = 'public'
    """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_type_info(cursor, table_name, column_name):
    """Return (data_type, character_maximum_length) for a column or None."""
    cursor.execute(
        """
        SELECT data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """,
        (table_name, column_name),
    )
    return cursor.fetchone()


def migrate_dashboard_db(host, port, database, user, password):
    """
    Ensure dashboard PostgreSQL database has all required columns.

    Adds missing columns to:
    - pages: fetch_images_from_url, fetch_images_timeout
    - client: initial_agents

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        bool: True if successful, False otherwise
    """
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL dashboard database.")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        # Check and add pages columns
        if _table_exists(cursor, "pages"):
            if not _column_exists(cursor, "pages", "fetch_images_from_url"):
                cursor.execute("""
                    ALTER TABLE pages
                    ADD COLUMN fetch_images_from_url BOOLEAN DEFAULT FALSE
                """)
                print("✓ Added fetch_images_from_url column to pages table")
            else:
                print("○ fetch_images_from_url column already exists in pages table")

            if not _column_exists(cursor, "pages", "fetch_images_timeout"):
                cursor.execute("""
                    ALTER TABLE pages
                    ADD COLUMN fetch_images_timeout INTEGER DEFAULT 10
                """)
                print("✓ Added fetch_images_timeout column to pages table")
            else:
                print("○ fetch_images_timeout column already exists in pages table")

        # Check and add client columns
        if _table_exists(cursor, "client"):
            if not _column_exists(cursor, "client", "initial_agents"):
                cursor.execute("""
                    ALTER TABLE client
                    ADD COLUMN initial_agents INTEGER DEFAULT 0
                """)
                print("✓ Added initial_agents column to client table")
            else:
                print("○ initial_agents column already exists in client table")

        # Ensure admin_users.password supports modern password hash lengths
        if _table_exists(cursor, "admin_users"):
            type_info = _column_type_info(cursor, "admin_users", "password")
            if type_info:
                data_type, char_max_len = type_info
                if (
                    data_type in {"character varying", "character"}
                    and char_max_len is not None
                    and char_max_len < 120
                ):
                    cursor.execute("""
                        ALTER TABLE admin_users
                        ALTER COLUMN password TYPE TEXT
                    """)
                    print("✓ Widened admin_users.password to TEXT")
                else:
                    print("○ admin_users.password column already supports long hashes")

            # Ensure at least one admin account exists for dashboard login
            cursor.execute("SELECT COUNT(*) FROM admin_users")
            admin_count = int(cursor.fetchone()[0] or 0)
            if admin_count == 0:
                from werkzeug.security import generate_password_hash

                hashed_pw = generate_password_hash("admin", method="pbkdf2:sha256")
                cursor.execute(
                    """
                    INSERT INTO admin_users (username, email, password, last_seen, role)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    ("Admin", "admin@y-not.social", hashed_pw, "", "admin"),
                )
                print("✓ Created default admin user: Admin / admin")
            else:
                print(f"○ admin_users already has {admin_count} account(s)")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL dashboard database: {e}")
        return False


def migrate_server_db(host, port, database, user, password):
    """
    Ensure server PostgreSQL database has all required tables and columns.

    Creates missing tables:
    - image_posts

    Adds missing columns to:
    - websites: fetch_images_from_url, fetch_images_timeout
    - images: remote_article_id
    - post: image_post_id, created_at

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name (typically experiment-specific)
        user: Database user
        password: Database password

    Returns:
        bool: True if successful, False otherwise
    """
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL server database.")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        # Create image_posts table if it doesn't exist
        if not _table_exists(cursor, "image_posts"):
            cursor.execute("""
                CREATE TABLE image_posts (
                    id           SERIAL PRIMARY KEY,
                    url          VARCHAR(500) NOT NULL,
                    source_url   VARCHAR(500),
                    title        VARCHAR(300),
                    subreddit    VARCHAR(100),
                    description  TEXT,
                    fetched_on   VARCHAR(20),
                    used         BOOLEAN DEFAULT FALSE,
                    local_path   VARCHAR(500),
                    high_res_url VARCHAR(500)
                )
            """)
            print("✓ Created image_posts table")
        else:
            print("○ image_posts table already exists")

        # Check and add websites columns
        if _table_exists(cursor, "websites"):
            if not _column_exists(cursor, "websites", "fetch_images_from_url"):
                cursor.execute("""
                    ALTER TABLE websites
                    ADD COLUMN fetch_images_from_url BOOLEAN DEFAULT FALSE
                """)
                print("✓ Added fetch_images_from_url column to websites table")
            else:
                print("○ fetch_images_from_url column already exists in websites table")

            if not _column_exists(cursor, "websites", "fetch_images_timeout"):
                cursor.execute("""
                    ALTER TABLE websites
                    ADD COLUMN fetch_images_timeout INTEGER DEFAULT 10
                """)
                print("✓ Added fetch_images_timeout column to websites table")
            else:
                print("○ fetch_images_timeout column already exists in websites table")

        # Check and add images columns
        if _table_exists(cursor, "images"):
            if not _column_exists(cursor, "images", "remote_article_id"):
                cursor.execute("""
                    ALTER TABLE images
                    ADD COLUMN remote_article_id INTEGER
                """)
                print("✓ Added remote_article_id column to images table")
            else:
                print("○ remote_article_id column already exists in images table")

        # Check and add post.image_post_id column (links to image_posts table)
        if _table_exists(cursor, "post"):
            if not _column_exists(cursor, "post", "image_post_id"):
                cursor.execute("""
                    ALTER TABLE post
                    ADD COLUMN image_post_id INTEGER REFERENCES image_posts(id) ON DELETE CASCADE
                """)
                print("✓ Added image_post_id column to post table")
            else:
                print("○ image_post_id column already exists in post table")

            # Ensure post.created_at exists for minute-level wall-clock timestamps.
            if not _column_exists(cursor, "post", "created_at"):
                cursor.execute("""
                    ALTER TABLE post
                    ADD COLUMN created_at TIMESTAMP
                """)
                print("✓ Added created_at column to post table")
            else:
                print("○ created_at column already exists in post table")

            # Backfill legacy rows from simulation day/hour when possible.
            if _table_exists(cursor, "rounds"):
                cursor.execute("""
                    UPDATE post p
                    SET created_at = (
                        date_trunc('day', NOW())
                        + (CASE WHEN r.day < 0 THEN 0 ELSE r.day END) * INTERVAL '1 day'
                        + (
                            CASE
                                WHEN r.hour < 0 THEN 0
                                WHEN r.hour > 23 THEN 23
                                ELSE r.hour
                            END
                        ) * INTERVAL '1 hour'
                    )
                    FROM rounds r
                    WHERE p.round = r.id
                      AND p.created_at IS NULL
                """)

            # Final fallback for unresolved rows.
            cursor.execute("""
                UPDATE post
                SET created_at = NOW()
                WHERE created_at IS NULL
            """)

            # Set stable defaults/constraints for future writes.
            cursor.execute("""
                ALTER TABLE post
                ALTER COLUMN created_at SET DEFAULT NOW()
            """)
            cursor.execute("""
                ALTER TABLE post
                ALTER COLUMN created_at SET NOT NULL
            """)

            # Ensure idempotent comment dedupe columns exist.
            if not _column_exists(cursor, "post", "dedupe_key"):
                cursor.execute("""
                    ALTER TABLE post
                    ADD COLUMN dedupe_key VARCHAR(64)
                """)
                print("✓ Added dedupe_key column to post table")
            else:
                print("○ dedupe_key column already exists in post table")

            if not _column_exists(cursor, "post", "client_action_id"):
                cursor.execute("""
                    ALTER TABLE post
                    ADD COLUMN client_action_id VARCHAR(96)
                """)
                print("✓ Added client_action_id column to post table")
            else:
                print("○ client_action_id column already exists in post table")

            # Indexes for idempotency/deduplication on new comments.
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_post_comment_action_id_uniq
                ON post (user_id, client_action_id)
                WHERE client_action_id IS NOT NULL
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_post_comment_dedupe_uniq
                ON post (user_id, comment_to, round, dedupe_key)
                WHERE comment_to <> -1 AND dedupe_key IS NOT NULL
            """)

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL server database: {e}")
        return False


def migrate_postgresql(host, port, dashboard_db, user, password):
    """
    Run all PostgreSQL schema migrations for the dashboard database.

    This is the main entry point called from y_web/__init__.py at startup.

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        dashboard_db: Dashboard database name
        user: Database user
        password: Database password

    Returns:
        bool: True if all migrations successful, False otherwise
    """
    print("Running PostgreSQL schema migrations...")

    # Migrate dashboard database
    dashboard_success = migrate_dashboard_db(host, port, dashboard_db, user, password)

    return dashboard_success


def main():
    """Run migration from command line."""
    print("YSocial PostgreSQL Schema Migration")
    print("=" * 60)
    print()

    # Read PostgreSQL configuration from environment variables
    pg_host = os.environ.get("PG_HOST", "localhost")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_database = os.environ.get("PG_DBNAME", "dashboard")
    pg_user = os.environ.get("PG_USER", "postgres")
    pg_password = os.environ.get("PG_PASSWORD", "")

    if not pg_password:
        print("✗ PG_PASSWORD environment variable not set")
        print("  To migrate PostgreSQL, set the following environment variables:")
        print("  - PG_HOST (default: localhost)")
        print("  - PG_PORT (default: 5432)")
        print("  - PG_DBNAME (default: dashboard)")
        print("  - PG_USER (default: postgres)")
        print("  - PG_PASSWORD (required)")
        return 1

    success = migrate_postgresql(pg_host, pg_port, pg_database, pg_user, pg_password)

    print()
    print("=" * 60)
    print(f"Migration: {'✓ Success' if success else '✗ Failed'}")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
