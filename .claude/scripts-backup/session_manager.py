#!/usr/bin/env python3
"""
Claude Code Session Manager (PostgreSQL) - Multi-Project Template

Core module for session tracking, tool logging, and event detection.
Supports multi-repository deployments with project_name field.

USAGE:
    # Auto-detect project from ENV
    manager = ClaudeSessionManager()

    # Explicit project name
    manager = ClaudeSessionManager(project_name="UTXOracle")

ENV VARIABLES:
    CLAUDE_PROJECT_NAME: Project identifier (default: "unknown")
    DATABASE_URL: PostgreSQL connection string
"""

import psycopg2
import os
import sys
from datetime import datetime

class ClaudeSessionManager:
    def __init__(self, db_url=None, project_name=None):
        """
        Initialize session manager with PostgreSQL connection.

        Args:
            db_url: PostgreSQL connection string (default: $DATABASE_URL or localhost)
            project_name: Project identifier (default: $CLAUDE_PROJECT_NAME or "unknown")
        """
        self.db_url = db_url or os.getenv("DATABASE_URL", "postgresql://localhost:5432/claude_sessions")
        self.project_name = project_name or os.getenv("CLAUDE_PROJECT_NAME", "unknown")
        self.conn = None
        self._ensure_db()

    def _ensure_db(self):
        """Initialize database connection."""
        try:
            self.conn = psycopg2.connect(self.db_url)
        except psycopg2.Error as e:
            raise ConnectionError(
                f"Failed to connect to PostgreSQL database.\n"
                f"Connection string: {self.db_url}\n"
                f"Error: {e}\n"
                f"Hint: Run 'python3 .claude/scripts/init_db.py' to create database schema."
            )

    def create_session(self, session_id, git_branch=None, task=None):
        """Initialize new session record."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (session_id, project_name, started_at, git_branch, task_description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
            """, (session_id, self.project_name, datetime.now(), git_branch, task))
            self.conn.commit()
            cursor.close()
            return session_id
        except psycopg2.Error as e:
            print(f"Warning: Failed to create session {session_id}: {e}", file=sys.stderr)
            return None

    def log_tool_use(self, session_id, tool_name, duration_ms, success, error=None, tool_params=None):
        """Log single tool invocation with optional tool parameters."""
        try:
            cursor = self.conn.cursor()
            # Convert tool_params dict to JSON string for JSONB column
            import json
            tool_params_json = json.dumps(tool_params) if tool_params else None

            cursor.execute("""
                INSERT INTO tool_usage (session_id, project_name, tool_name, tool_params, timestamp, duration_ms, success, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (session_id, self.project_name, tool_name, tool_params_json, datetime.now(), duration_ms, success, error))
            self.conn.commit()
            cursor.close()
        except psycopg2.Error as e:
            print(f"Warning: Failed to log tool use for {tool_name}: {e}", file=sys.stderr)

    def log_event(self, session_id, event_type, tool_name=None, error_message=None, severity='medium'):
        """Log error/block event (uses JSONB data field for flexible storage)."""
        try:
            cursor = self.conn.cursor()
            import json

            # Pack event details into JSONB data field
            event_data = {
                "tool_name": tool_name,
                "error_message": error_message,
                "severity": severity
            }
            event_data_json = json.dumps(event_data)

            cursor.execute("""
                INSERT INTO events (session_id, project_name, event_type, timestamp, data)
                VALUES (%s, %s, %s, %s, %s)
            """, (session_id, self.project_name, event_type, datetime.now(), event_data_json))
            self.conn.commit()
            cursor.close()
        except psycopg2.Error as e:
            print(f"Warning: Failed to log event {event_type}: {e}", file=sys.stderr)

    def upsert_session(self, session_id, tokens_input, tokens_output, tokens_cache,
                       cost_usd, lines_added, lines_removed, git_branch, task_desc, agent_name):
        """
        UPSERT session metrics (called by context-monitor every 1-2 sec).

        Updates session metrics in PostgreSQL for real-time tracking.
        Uses ON CONFLICT to update existing session or insert new one.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (
                    session_id, project_name, total_tokens_input, total_tokens_output,
                    total_tokens_cache, total_cost_usd, lines_added, lines_removed,
                    git_branch, task_description, agent_name, started_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (session_id) DO UPDATE SET
                    project_name = EXCLUDED.project_name,
                    total_tokens_input = EXCLUDED.total_tokens_input,
                    total_tokens_output = EXCLUDED.total_tokens_output,
                    total_tokens_cache = EXCLUDED.total_tokens_cache,
                    total_cost_usd = EXCLUDED.total_cost_usd,
                    lines_added = EXCLUDED.lines_added,
                    lines_removed = EXCLUDED.lines_removed,
                    git_branch = EXCLUDED.git_branch,
                    task_description = EXCLUDED.task_description,
                    agent_name = EXCLUDED.agent_name,
                    updated_at = CURRENT_TIMESTAMP
            """, (session_id, self.project_name, tokens_input, tokens_output, tokens_cache, cost_usd,
                  lines_added, lines_removed, git_branch, task_desc, agent_name))
            self.conn.commit()
            cursor.close()
        except psycopg2.Error as e:
            print(f"Warning: Failed to upsert session {session_id}: {e}", file=sys.stderr)

    def generate_summary(self, session_id):
        """Generate analytics summary for session."""
        try:
            cursor = self.conn.cursor()

            # Query tool_usage stats
            cursor.execute("""
                SELECT tool_name, COUNT(*) as count, AVG(duration_ms) as avg_duration
                FROM tool_usage WHERE session_id = %s
                GROUP BY tool_name
            """, (session_id,))
            tool_stats = [{"tool": row[0], "count": row[1], "avg_duration": float(row[2]) if row[2] else 0}
                          for row in cursor.fetchall()]

            # Query events
            cursor.execute("""
                SELECT event_type, COUNT(*) as count
                FROM events WHERE session_id = %s
                GROUP BY event_type
            """, (session_id,))
            event_stats = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.close()

            return {
                "session_id": session_id,
                "project_name": self.project_name,
                "tool_stats": tool_stats,
                "event_stats": event_stats
            }
        except psycopg2.Error as e:
            print(f"Warning: Failed to generate summary for session {session_id}: {e}", file=sys.stderr)
            return {
                "session_id": session_id,
                "project_name": self.project_name,
                "tool_stats": [],
                "event_stats": {},
                "error": str(e)
            }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
