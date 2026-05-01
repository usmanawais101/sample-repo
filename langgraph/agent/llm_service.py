"""LLM Service for code generation and verification using OpenAI-compatible APIs."""

import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


@dataclass
class LLMResponse:
    """Response from LLM call."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    raw_response: Any = None


class LLMService:
    """Service for interacting with OpenAI-compatible LLMs."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        """
        Initialize LLM service.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom base URL for OpenAI-compatible APIs
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        if not self.api_key:
            raise ValueError(
                "API key not provided. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Initialize the chat model
        client_kwargs = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "api_key": self.api_key,
        }
        
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        self.llm = ChatOpenAI(**client_kwargs)
    
    def generate_code(
        self,
        task_description: str,
        context_files: Optional[List[Dict[str, str]]] = None,
        previous_attempts: Optional[List[Dict[str, str]]] = None,
        feedback: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate Python code to solve a task.
        
        Args:
            task_description: Description of what the code should do
            context_files: List of context files with path and content
            previous_attempts: Previous code attempts with errors
            feedback: Feedback from verification steps
        
        Returns:
            LLMResponse with generated code
        """
        system_prompt = """You are an expert Python developer. Your task is to write clean, efficient, and correct Python code.

Guidelines:
1. Write complete, runnable Python code
2. Include proper error handling
3. Add docstrings and comments where appropriate
4. Follow PEP 8 style guidelines
5. Use type hints
6. Make code modular and reusable
7. Handle edge cases
8. Only output Python code, no explanations outside of code comments

The code should be saved and executed in the working directory. If you need to create files, use absolute paths or paths relative to the current working directory."""

        user_prompt_parts = [f"Task: {task_description}"]
        
        if context_files:
            user_prompt_parts.append("\nContext Files:")
            for file_info in context_files:
                user_prompt_parts.append(f"\nFile: {file_info['path']}")
                user_prompt_parts.append(f"Content:\n{file_info['content']}")
        
        if previous_attempts:
            user_prompt_parts.append("\nPrevious Attempts:")
            for i, attempt in enumerate(previous_attempts, 1):
                user_prompt_parts.append(f"\nAttempt {i}:")
                user_prompt_parts.append(f"Code:\n{attempt.get('code', '')}")
                if attempt.get('error'):
                    user_prompt_parts.append(f"Error: {attempt['error']}")
        
        if feedback:
            user_prompt_parts.append(f"\nFeedback from previous attempt: {feedback}")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        response = self.llm.invoke(messages)
        
        return LLMResponse(
            content=response.content,
            model=self.model,
            usage=getattr(response, "usage_metadata", None),
            raw_response=response,
        )
    
    def verify_code(
        self,
        code: str,
        task_description: str,
        context_files: Optional[List[Dict[str, str]]] = None,
    ) -> LLMResponse:
        """
        Verify if generated code is correct and suitable for the task.
        
        Args:
            code: The generated Python code
            task_description: Original task description
            context_files: Context files if any
        
        Returns:
            LLMResponse with verification result
        """
        system_prompt = """You are a code reviewer. Analyze the provided Python code and determine if it:
1. Correctly solves the given task
2. Is syntactically correct
3. Has proper error handling
4. Follows best practices
5. Is safe to execute

Respond with a JSON object containing:
- "is_valid": boolean indicating if code is good
- "issues": list of issues found (empty if none)
- "suggestions": list of improvement suggestions
- "ready_for_execution": boolean indicating if code can be executed"""

        user_prompt_parts = [
            f"Task: {task_description}",
            f"\nCode to review:\n```python\n{code}\n```",
        ]
        
        if context_files:
            user_prompt_parts.append("\nContext Files:")
            for file_info in context_files:
                user_prompt_parts.append(f"\nFile: {file_info['path']}")
                user_prompt_parts.append(f"Content:\n{file_info['content']}")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        response = self.llm.invoke(messages)
        
        return LLMResponse(
            content=response.content,
            model=self.model,
            usage=getattr(response, "usage_metadata", None),
            raw_response=response,
        )
    
    def verify_artifact(
        self,
        task_description: str,
        artifact_description: str,
        artifact_path: str,
        execution_output: str,
    ) -> LLMResponse:
        """
        Verify if the generated artifact meets the user's requirements.
        
        Args:
            task_description: Original task description
            artifact_description: Description of what was created
            artifact_path: Path to the generated artifact
            execution_output: Output from code execution
        
        Returns:
            LLMResponse with verification result
        """
        system_prompt = """You are evaluating whether the generated output meets the user's requirements.

Analyze the task, the execution output, and determine if:
1. The task was completed successfully
2. The output artifact is what the user requested
3. Any issues or improvements needed

Respond with a JSON object containing:
- "is_successful": boolean indicating if task is complete
- "artifact_path": path to the artifact if successful
- "issues": list of issues if any
- "feedback": detailed feedback for improvement if needed
- "requires_retry": boolean indicating if another attempt is needed"""

        user_prompt = f"""Task: {task_description}

Execution Output:
{execution_output}

Artifact Created: {artifact_path}
Artifact Description: {artifact_description}

Evaluate if this successfully completes the task."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        response = self.llm.invoke(messages)
        
        return LLMResponse(
            content=response.content,
            model=self.model,
            usage=getattr(response, "usage_metadata", None),
            raw_response=response,
        )
    
    def generate_final_response(
        self,
        task_description: str,
        artifact_path: str,
        execution_summary: str,
    ) -> LLMResponse:
        """
        Generate a final response to present to the user.
        
        Args:
            task_description: Original task
            artifact_path: Path to generated artifact
            execution_summary: Summary of what was done
        
        Returns:
            LLMResponse with user-friendly response
        """
        system_prompt = """You are a helpful assistant presenting results to a user.
Provide a clear, concise summary of what was accomplished.
Include the path to any generated artifacts.
Be friendly and professional."""

        user_prompt = f"""Task completed successfully!

Original Task: {task_description}

Summary: {execution_summary}

Generated Artifact: {artifact_path}

Please provide a friendly summary to the user."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        response = self.llm.invoke(messages)
        
        return LLMResponse(
            content=response.content,
            model=self.model,
            usage=getattr(response, "usage_metadata", None),
            raw_response=response,
        )
