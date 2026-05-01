"""Tests for the coding agent."""

import pytest
import tempfile
import os
from pathlib import Path

from langgraph.models.session import Session, Task, TaskStatus
from langgraph.models.user_management import UserManager
from langgraph.models.context import ContextManager
from langgraph.agent.code_executor import CodeExecutor


class TestCodeExecutor:
    """Test code execution and verification."""
    
    @pytest.fixture
    def executor(self, tmp_path):
        """Create a code executor with temp directory."""
        return CodeExecutor(str(tmp_path))
    
    def test_syntax_verification_valid(self, executor):
        """Test syntax verification with valid code."""
        code = "def hello():\n    return 'world'"
        is_valid, error = executor.verify_syntax(code)
        assert is_valid is True
        assert error is None
    
    def test_syntax_verification_invalid(self, executor):
        """Test syntax verification with invalid code."""
        code = "def hello(\n    return 'world'"
        is_valid, error = executor.verify_syntax(code)
        assert is_valid is False
        assert error is not None
    
    def test_execute_simple_code(self, executor):
        """Test executing simple Python code."""
        code = "print('Hello, World!')"
        result = executor.execute_code(code)
        assert result.success is True
        assert "Hello, World!" in result.output
    
    def test_execute_code_with_error(self, executor):
        """Test executing code that raises an error."""
        code = "raise ValueError('Test error')"
        result = executor.execute_code(code)
        assert result.success is False
        assert "ValueError" in result.error
    
    def test_security_check_eval(self, executor):
        """Test security check detects eval usage."""
        code = "result = eval('1 + 1')"
        issues = executor.check_security(code)
        assert len(issues) > 0
        assert "eval" in str(issues).lower()


class TestContextManager:
    """Test context management."""
    
    @pytest.fixture
    def session(self, tmp_path):
        """Create a test session."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        return Session(
            session_id="test-session",
            user_id="test-user",
            work_directory=str(work_dir),
        )
    
    @pytest.fixture
    def context_manager(self, session):
        """Create a context manager."""
        return ContextManager(session)
    
    def test_create_directories(self, context_manager):
        """Test that required directories are created."""
        assert context_manager.code_dir.exists()
        assert context_manager.artifacts_dir.exists()
        assert context_manager.input_dir.exists()
    
    def test_save_generated_code(self, context_manager):
        """Test saving generated code."""
        code = "def test(): pass"
        path = context_manager.save_generated_code(code, "test.py", "Test function")
        assert path.endswith(".py")
        assert context_manager.work_directory.joinpath(path).exists()
    
    def test_save_text_artifact(self, context_manager):
        """Test saving text artifact."""
        content = "Test content"
        path = context_manager.save_text_artifact(content, "output.txt")
        assert path.endswith(".txt")
        assert context_manager.work_directory.joinpath(path).exists()
    
    def test_read_context_file(self, context_manager):
        """Test reading context files."""
        # First save a file to input directory
        input_file = context_manager.input_dir / "test.txt"
        input_file.write_text("Test content")
        
        # Scan for context files
        context_manager._scan_context_files()
        
        # Read it back
        content = context_manager.read_context_file("input/test.txt")
        assert content == "Test content"


class TestSession:
    """Test session model."""
    
    def test_session_creation(self):
        """Test creating a session."""
        session = Session(
            session_id="test-123",
            user_id="user-456",
            work_directory="/tmp/test",
        )
        assert session.session_id == "test-123"
        assert session.user_id == "user-456"
        assert session.context_files == []
        assert session.generated_artifacts == []
    
    def test_add_context_file(self):
        """Test adding context files to session."""
        session = Session(
            session_id="test-123",
            user_id="user-456",
            work_directory="/tmp/test",
        )
        session.add_context_file("input/file1.txt")
        assert "input/file1.txt" in session.context_files
        
        # Adding same file again should not duplicate
        session.add_context_file("input/file1.txt")
        assert session.context_files.count("input/file1.txt") == 1


class TestTask:
    """Test task model."""
    
    def test_task_creation(self):
        """Test creating a task."""
        task = Task(
            task_id="task-123",
            session_id="session-456",
            description="Test task",
        )
        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 0
        assert task.max_retries == 10
    
    def test_task_retry(self):
        """Test task retry logic."""
        task = Task(
            task_id="task-123",
            session_id="session-456",
            description="Test task",
            max_retries=3,
        )
        assert task.can_retry() is True
        
        task.increment_retry()
        task.increment_retry()
        task.increment_retry()
        
        assert task.can_retry() is False
        assert task.retry_count == 3


class TestUserManager:
    """Test user management."""
    
    @pytest.fixture
    def user_manager(self, tmp_path):
        """Create user manager with temp database."""
        db_path = tmp_path / "test_sessions.db"
        return UserManager(str(db_path))
    
    def test_create_user(self, user_manager):
        """Test creating a user."""
        user_id = user_manager.create_user("testuser")
        assert user_id is not None
        
        # Verify user exists
        retrieved_id = user_manager.get_user_by_username("testuser")
        assert retrieved_id == user_id
    
    def test_create_or_get_user(self, user_manager):
        """Test create or get user."""
        # First call creates user
        user_id1 = user_manager.create_or_get_user("newuser")
        assert user_id1 is not None
        
        # Second call gets existing user
        user_id2 = user_manager.create_or_get_user("newuser")
        assert user_id2 == user_id1
    
    def test_create_session_for_user(self, user_manager, tmp_path):
        """Test creating session for user."""
        work_dir = tmp_path / "work"
        session = user_manager.create_session_for_user("sessionuser", str(work_dir))
        
        assert session.session_id is not None
        assert session.user_id is not None
        assert work_dir.exists()
        
        # Verify session can be retrieved
        retrieved = user_manager.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
