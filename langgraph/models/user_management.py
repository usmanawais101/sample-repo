"""User management module with session handling."""

import sqlite3
import uuid
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from langgraph.models.session import Session


class SessionManager:
    """Manages user sessions with SQLite persistence."""
    
    def __init__(self, db_path: str = "sessions.db"):
        """Initialize session manager with database path."""
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                work_directory TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                context_files TEXT,
                generated_artifacts TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_session(self, user_id: str, work_directory: str) -> Session:
        """Create a new session for a user."""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            user_id=user_id,
            work_directory=work_directory
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO sessions 
            (session_id, user_id, work_directory, created_at, updated_at, context_files, generated_artifacts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session.session_id,
            session.user_id,
            session.work_directory,
            session.created_at.isoformat(),
            session.updated_at.isoformat(),
            ",".join(session.context_files),
            ",".join(session.generated_artifacts)
        ))
        
        conn.commit()
        conn.close()
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        return Session(
            session_id=row[0],
            user_id=row[1],
            work_directory=row[2],
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
            context_files=row[5].split(",") if row[5] else [],
            generated_artifacts=row[6].split(",") if row[6] else []
        )
    
    def update_session(self, session: Session) -> None:
        """Update an existing session."""
        session.updated_at = datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE sessions 
            SET updated_at = ?, context_files = ?, generated_artifacts = ?
            WHERE session_id = ?
        """, (
            session.updated_at.isoformat(),
            ",".join(session.context_files),
            ",".join(session.generated_artifacts),
            session.session_id
        ))
        
        conn.commit()
        conn.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        deleted = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return deleted
    
    def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all sessions for a user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        sessions = []
        for row in rows:
            sessions.append(Session(
                session_id=row[0],
                user_id=row[1],
                work_directory=row[2],
                created_at=datetime.fromisoformat(row[3]),
                updated_at=datetime.fromisoformat(row[4]),
                context_files=row[5].split(",") if row[5] else [],
                generated_artifacts=row[6].split(",") if row[6] else []
            ))
        
        return sessions


class UserManager:
    """Manages users and their sessions."""
    
    def __init__(self, db_path: str = "sessions.db"):
        """Initialize user manager with database path."""
        self.db_path = db_path
        self.session_manager = SessionManager(db_path)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_user(self, username: str) -> str:
        """Create a new user and return user ID."""
        user_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, created_at)
                VALUES (?, ?, ?)
            """, (user_id, username, datetime.now().isoformat()))
            
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"Username '{username}' already exists")
        
        conn.close()
        return user_id
    
    def get_user_by_username(self, username: str) -> Optional[str]:
        """Get user ID by username."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def create_or_get_user(self, username: str) -> str:
        """Create a new user or get existing user ID."""
        user_id = self.get_user_by_username(username)
        if user_id is None:
            user_id = self.create_user(username)
        return user_id
    
    def create_session_for_user(self, username: str, work_directory: str) -> Session:
        """Create a session for a user (creates user if doesn't exist)."""
        user_id = self.create_or_get_user(username)
        
        # Ensure work directory exists
        work_dir = Path(work_directory)
        work_dir.mkdir(parents=True, exist_ok=True)
        
        return self.session_manager.create_session(user_id, str(work_dir.absolute()))
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.session_manager.get_session(session_id)
    
    def update_session(self, session: Session) -> None:
        """Update a session."""
        self.session_manager.update_session(session)
    
    def get_user_sessions(self, username: str) -> List[Session]:
        """Get all sessions for a user."""
        user_id = self.get_user_by_username(username)
        if user_id is None:
            return []
        return self.session_manager.get_user_sessions(user_id)
