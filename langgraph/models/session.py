"""Models for the LangGraph coding agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class TaskStatus(Enum):
    """Status of a task in the agent workflow."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CODE_GENERATED = "code_generated"
    CODE_VERIFIED = "code_verified"
    CODE_EXECUTED = "code_executed"
    ARTIFACT_VERIFIED = "artifact_verified"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Session:
    """Represents a user session with work directory context."""
    session_id: str
    user_id: str
    work_directory: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    context_files: List[str] = field(default_factory=list)
    generated_artifacts: List[str] = field(default_factory=list)
    
    def add_context_file(self, file_path: str) -> None:
        """Add a context file to the session."""
        if file_path not in self.context_files:
            self.context_files.append(file_path)
            self.updated_at = datetime.now()
    
    def add_generated_artifact(self, artifact_path: str) -> None:
        """Add a generated artifact to the session."""
        if artifact_path not in self.generated_artifacts:
            self.generated_artifacts.append(artifact_path)
            self.updated_at = datetime.now()


@dataclass
class GeneratedCode:
    """Represents generated Python code with metadata."""
    code: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    verification_status: Optional[str] = None
    verification_feedback: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of code execution."""
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    artifacts_created: List[str] = field(default_factory=list)


@dataclass
class Task:
    """Represents a user task/request."""
    task_id: str
    session_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    generated_code: Optional[GeneratedCode] = None
    execution_result: Optional[ExecutionResult] = None
    verification_feedback: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 10
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> None:
        """Increment retry count."""
        self.retry_count += 1


@dataclass
class AgentState:
    """State object for LangGraph workflow."""
    task: Task
    session: Session
    current_step: str = "init"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.messages.append({"role": role, "content": content})
    
    def add_error(self, error: str) -> None:
        """Add an error to the error list."""
        self.errors.append(error)
