"""LangGraph nodes for the coding agent workflow."""

import json
import re
from typing import Dict, Any, TypedDict, Annotated, Sequence
from datetime import datetime

from langgraph.models.session import (
    Task,
    Session,
    AgentState,
    TaskStatus,
    GeneratedCode,
)
from langgraph.agent.llm_service import LLMService
from langgraph.agent.code_executor import CodeExecutor, CodeVerificationResult
from langgraph.models.context import ContextManager


def extract_code_from_response(response: str) -> str:
    """Extract Python code from LLM response."""
    # Try to find code in markdown code blocks
    pattern = r"```python\s*(.*?)\s*```"
    matches = re.findall(pattern, response, re.DOTALL)
    
    if matches:
        return matches[0]
    
    # If no code blocks, try to find any code-like content
    # This is a fallback - the LLM should ideally return code in blocks
    lines = response.split('\n')
    code_lines = []
    in_code = False
    
    for line in lines:
        # Skip common non-code patterns
        if line.strip().startswith(('Task:', 'Description:', 'Here', 'I\'ve', 'Let me')):
            continue
        code_lines.append(line)
    
    return '\n'.join(code_lines).strip() or response


def generate_code_node(state: AgentState, llm_service: LLMService, context_manager: ContextManager) -> Dict[str, Any]:
    """
    Node: Generate Python code based on task description.
    
    This node uses the LLM to generate code that solves the user's task.
    """
    task = state.task
    session = state.session
    
    # Update task status
    task.status = TaskStatus.IN_PROGRESS
    task.increment_retry()
    
    # Gather context files
    context_files = []
    for file_path in session.context_files:
        content = context_manager.read_context_file(file_path)
        if content:
            context_files.append({"path": file_path, "content": content})
    
    # Gather previous attempts if any
    previous_attempts = []
    if task.generated_code:
        attempt_info = {
            "code": task.generated_code.code,
        }
        if task.generated_code.verification_feedback:
            attempt_info["error"] = task.generated_code.verification_feedback
        if task.execution_result and task.execution_result.error:
            attempt_info["error"] = task.execution_result.error
        previous_attempts.append(attempt_info)
    
    # Get feedback from verification if available
    feedback = task.verification_feedback
    
    # Generate code using LLM
    response = llm_service.generate_code(
        task_description=task.description,
        context_files=context_files if context_files else None,
        previous_attempts=previous_attempts if previous_attempts else None,
        feedback=feedback,
    )
    
    # Extract code from response
    code = extract_code_from_response(response.content)
    
    # Create GeneratedCode object
    generated_code = GeneratedCode(
        code=code,
        description=task.description,
    )
    
    # Save generated code to context
    code_filename = f"task_{task.task_id}_attempt_{task.retry_count}.py"
    code_path = context_manager.save_generated_code(
        code=code,
        filename=code_filename,
        description=task.description,
    )
    
    # Update state
    task.generated_code = generated_code
    task.status = TaskStatus.CODE_GENERATED
    
    state.add_message("assistant", f"Generated code (attempt {task.retry_count}): {code_path}")
    
    return {"task": task, "session": session, "current_step": "code_generated"}


def verify_code_node(state: AgentState, llm_service: LLMService, code_executor: CodeExecutor) -> Dict[str, Any]:
    """
    Node: Verify generated code using static analysis and LLM review.
    
    This node performs:
    1. Syntax checking
    2. Linting
    3. Type checking
    4. Security analysis
    5. LLM-based code review
    """
    task = state.task
    
    if not task.generated_code:
        state.add_error("No generated code to verify")
        task.status = TaskStatus.FAILED
        return {"task": task, "current_step": "verification_failed"}
    
    code = task.generated_code.code
    
    # Run static verification
    verification_result = code_executor.verify_code(
        code=code,
        task_description=task.description,
        run_all_checks=True,
    )
    
    # Also get LLM-based verification
    llm_verification = llm_service.verify_code(
        code=code,
        task_description=task.description,
    )
    
    # Parse LLM verification result
    llm_is_valid = True
    llm_feedback = ""
    
    try:
        # Try to parse JSON from LLM response
        json_match = re.search(r'\{.*\}', llm_verification.content, re.DOTALL)
        if json_match:
            llm_result = json.loads(json_match.group())
            llm_is_valid = llm_result.get("is_valid", True)
            llm_feedback = "; ".join(llm_result.get("issues", []))
    except (json.JSONDecodeError, AttributeError):
        llm_feedback = llm_verification.content
    
    # Combine verification results
    is_valid = verification_result.is_valid and llm_is_valid
    
    if is_valid:
        task.status = TaskStatus.CODE_VERIFIED
        task.generated_code.verification_status = "passed"
        state.add_message("assistant", f"Code verification passed: {verification_result.feedback}")
    else:
        # Collect all feedback
        feedback_parts = [verification_result.feedback]
        if llm_feedback:
            feedback_parts.append(f"LLM review: {llm_feedback}")
        
        task.verification_feedback = "\n".join(feedback_parts)
        task.generated_code.verification_status = "failed"
        task.generated_code.verification_feedback = task.verification_feedback
        
        state.add_error(f"Code verification failed: {task.verification_feedback}")
        
        # Check if we can retry
        if task.can_retry():
            task.status = TaskStatus.IN_PROGRESS
            state.current_step = "generate_code"
        else:
            task.status = TaskStatus.FAILED
            state.current_step = "failed"
    
    return {"task": task, "current_step": state.current_step}


def execute_code_node(state: AgentState, code_executor: CodeExecutor) -> Dict[str, Any]:
    """
    Node: Execute the verified code.
    
    This node runs the generated code and captures output and artifacts.
    """
    task = state.task
    
    if not task.generated_code or task.generated_code.verification_status != "passed":
        state.add_error("Cannot execute code that hasn't passed verification")
        task.status = TaskStatus.FAILED
        return {"task": task, "current_step": "execution_failed"}
    
    # Execute the code
    execution_result = code_executor.execute_code(
        code=task.generated_code.code,
        timeout=60,
        capture_output=True,
    )
    
    task.execution_result = execution_result
    
    if execution_result.success:
        task.status = TaskStatus.CODE_EXECUTED
        state.add_message(
            "assistant",
            f"Code executed successfully in {execution_result.execution_time:.2f}s. "
            f"Output: {execution_result.output[:500] if execution_result.output else 'No output'}"
        )
        state.current_step = "code_executed"
    else:
        error_msg = execution_result.error or "Unknown execution error"
        task.verification_feedback = f"Execution error: {error_msg}"
        state.add_error(f"Code execution failed: {error_msg}")
        
        if task.can_retry():
            task.status = TaskStatus.IN_PROGRESS
            state.current_step = "generate_code"
        else:
            task.status = TaskStatus.FAILED
            state.current_step = "failed"
    
    return {"task": task, "current_step": state.current_step}


def verify_artifact_node(
    state: AgentState,
    llm_service: LLMService,
    context_manager: ContextManager,
) -> Dict[str, Any]:
    """
    Node: Verify if the generated artifact meets user requirements.
    
    This node uses LLM to evaluate if the output is what the user wanted.
    """
    task = state.task
    
    if not task.execution_result:
        state.add_error("No execution result to verify")
        task.status = TaskStatus.FAILED
        return {"task": task, "current_step": "artifact_verification_failed"}
    
    execution_result = task.execution_result
    
    # Determine artifact description
    artifact_path = ""
    artifact_description = ""
    
    if execution_result.artifacts_created:
        artifact_path = execution_result.artifacts_created[0]
        artifact_description = f"Created file: {artifact_path}"
    elif execution_result.output:
        artifact_path = "stdout"
        artifact_description = f"Output: {execution_result.output[:200]}"
    
    # Use LLM to verify artifact
    verification = llm_service.verify_artifact(
        task_description=task.description,
        artifact_description=artifact_description,
        artifact_path=artifact_path,
        execution_output=execution_result.output or "",
    )
    
    # Parse verification result
    is_successful = False
    requires_retry = True
    feedback = ""
    
    try:
        json_match = re.search(r'\{.*\}', verification.content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            is_successful = result.get("is_successful", False)
            requires_retry = result.get("requires_retry", True)
            feedback = result.get("feedback", "")
            
            if result.get("issues"):
                feedback += " Issues: " + "; ".join(result["issues"])
    except (json.JSONDecodeError, AttributeError):
        # If parsing fails, make a heuristic judgment
        is_successful = execution_result.success and not execution_result.error
        feedback = verification.content
        requires_retry = not is_successful
    
    if is_successful:
        task.status = TaskStatus.ARTIFACT_VERIFIED
        task.completed_at = datetime.now()
        state.add_message("assistant", f"Artifact verified successfully: {artifact_path}")
        state.current_step = "success"
    elif requires_retry and task.can_retry():
        task.verification_feedback = feedback or "Artifact does not meet requirements"
        task.status = TaskStatus.IN_PROGRESS
        state.add_error(f"Artifact verification failed: {feedback}")
        state.current_step = "generate_code"
    else:
        task.status = TaskStatus.FAILED
        task.verification_feedback = feedback or "Artifact verification failed after max retries"
        state.add_error(task.verification_feedback)
        state.current_step = "failed"
    
    return {"task": task, "current_step": state.current_step}


def generate_response_node(
    state: AgentState,
    llm_service: LLMService,
    context_manager: ContextManager,
) -> Dict[str, Any]:
    """
    Node: Generate final response to present to user.
    
    This node creates a user-friendly summary of the completed task.
    """
    task = state.task
    
    if task.status != TaskStatus.ARTIFACT_VERIFIED:
        return {"current_step": "cannot_generate_response"}
    
    # Determine artifact path
    artifact_path = "N/A"
    if task.execution_result and task.execution_result.artifacts_created:
        artifact_path = task.execution_result.artifacts_created[0]
    
    # Create execution summary
    summary_parts = []
    
    if task.execution_result:
        summary_parts.append(f"Execution time: {task.execution_result.execution_time:.2f}s")
        
        if task.execution_result.output:
            output_preview = task.execution_result.output[:200]
            if len(task.execution_result.output) > 200:
                output_preview += "..."
            summary_parts.append(f"Output: {output_preview}")
    
    execution_summary = ". ".join(summary_parts)
    
    # Generate final response
    response = llm_service.generate_final_response(
        task_description=task.description,
        artifact_path=artifact_path,
        execution_summary=execution_summary,
    )
    
    state.add_message("assistant", response.content)
    state.current_step = "complete"
    
    return {"task": task, "current_step": "complete"}


def route_after_code_generation(state: AgentState) -> str:
    """Route decision after code generation."""
    if state.task.status == TaskStatus.CODE_GENERATED:
        return "verify_code"
    return "failed"


def route_after_verification(state: AgentState) -> str:
    """Route decision after code verification."""
    if state.task.status == TaskStatus.CODE_VERIFIED:
        return "execute_code"
    elif state.task.status == TaskStatus.IN_PROGRESS:
        return "generate_code"
    return "failed"


def route_after_execution(state: AgentState) -> str:
    """Route decision after code execution."""
    if state.task.status == TaskStatus.CODE_EXECUTED:
        return "verify_artifact"
    elif state.task.status == TaskStatus.IN_PROGRESS:
        return "generate_code"
    return "failed"


def route_after_artifact_verification(state: AgentState) -> str:
    """Route decision after artifact verification."""
    if state.task.status == TaskStatus.ARTIFACT_VERIFIED:
        return "generate_response"
    elif state.task.status == TaskStatus.IN_PROGRESS:
        return "generate_code"
    return "failed"
