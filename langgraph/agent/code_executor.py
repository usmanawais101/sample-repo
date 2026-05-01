"""Code execution and verification module."""

import ast
import subprocess
import sys
import tempfile
import time
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass

from langgraph.models.session import GeneratedCode, ExecutionResult


@dataclass
class CodeVerificationResult:
    """Result of code verification."""
    is_valid: bool
    syntax_ok: bool
    lint_issues: List[str]
    type_check_issues: List[str]
    security_issues: List[str]
    feedback: str


class CodeExecutor:
    """Executes and verifies Python code safely."""
    
    def __init__(self, work_directory: str):
        """
        Initialize code executor.
        
        Args:
            work_directory: Directory where code will be executed
        """
        self.work_directory = Path(work_directory)
        self.work_directory.mkdir(parents=True, exist_ok=True)
    
    def verify_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Verify Python syntax.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
    
    def verify_with_linter(self, code: str) -> List[str]:
        """
        Run linting checks on code.
        
        Returns:
            List of linting issues
        """
        issues = []
        
        try:
            import pylint.lint
            from io import StringIO
            
            # Create temporary file for linting
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                # Run pylint
                output = StringIO()
                old_stdout = sys.stdout
                sys.stdout = output
                
                try:
                    pylint.lint.Run([temp_file, "--disable=all", "--enable=E,W"], exit=False)
                except SystemExit:
                    pass
                finally:
                    sys.stdout = old_stdout
                
                lint_output = output.getvalue()
                
                # Parse output for issues
                for line in lint_output.split('\n'):
                    if ':' in line and ('error' in line.lower() or 'warning' in line.lower()):
                        issues.append(line.strip())
                        
            finally:
                os.unlink(temp_file)
                
        except ImportError:
            # Pylint not available, skip linting
            pass
        
        return issues
    
    def verify_type_hints(self, code: str) -> List[str]:
        """
        Run type checking on code.
        
        Returns:
            List of type checking issues
        """
        issues = []
        
        try:
            import mypy.api
            
            # Create temporary file for type checking
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                result = mypy.api.run([temp_file, "--ignore-missing-imports"])
                
                # Parse mypy output
                stdout = result[0]
                for line in stdout.split('\n'):
                    if line.strip() and 'error:' in line.lower():
                        issues.append(line.strip())
                        
            finally:
                os.unlink(temp_file)
                
        except ImportError:
            # Mypy not available, skip type checking
            pass
        
        return issues
    
    def check_security(self, code: str) -> List[str]:
        """
        Check for potential security issues.
        
        Returns:
            List of security concerns
        """
        issues = []
        
        # Simple pattern-based security checks
        dangerous_patterns = [
            ("os.system(", "Use subprocess instead of os.system"),
            ("eval(", "Avoid using eval - potential code injection"),
            ("exec(", "Avoid using exec - potential code injection"),
            ("__import__(", "Dynamic imports can be dangerous"),
            ("subprocess.call.*shell=True", "Avoid shell=True in subprocess calls"),
            ("pickle.load(", "Unpickling untrusted data is dangerous"),
        ]
        
        for pattern, message in dangerous_patterns:
            if pattern in code:
                issues.append(f"Security concern: {message}")
        
        return issues
    
    def verify_code(
        self,
        code: str,
        task_description: str,
        run_all_checks: bool = True,
    ) -> CodeVerificationResult:
        """
        Perform comprehensive code verification.
        
        Args:
            code: Python code to verify
            task_description: What the code should do
            run_all_checks: Whether to run all verification checks
        
        Returns:
            CodeVerificationResult with verification details
        """
        # Syntax check (always run)
        syntax_ok, syntax_error = self.verify_syntax(code)
        
        if not syntax_ok:
            return CodeVerificationResult(
                is_valid=False,
                syntax_ok=False,
                lint_issues=[],
                type_check_issues=[],
                security_issues=[],
                feedback=f"Code has syntax errors: {syntax_error}",
            )
        
        lint_issues = []
        type_check_issues = []
        security_issues = []
        
        if run_all_checks:
            lint_issues = self.verify_with_linter(code)
            type_check_issues = self.verify_type_hints(code)
        
        # Security check (always run)
        security_issues = self.check_security(code)
        
        # Determine overall validity
        is_valid = (
            syntax_ok and
            len(security_issues) == 0 and
            len([i for i in lint_issues if 'error' in i.lower()]) == 0
        )
        
        # Build feedback
        feedback_parts = []
        
        if lint_issues:
            feedback_parts.append(f"Linting issues: {len(lint_issues)}")
        
        if type_check_issues:
            feedback_parts.append(f"Type checking issues: {len(type_check_issues)}")
        
        if security_issues:
            feedback_parts.append(f"Security concerns: {len(security_issues)}")
        
        if is_valid:
            feedback = "Code verification passed. Ready for execution."
            if feedback_parts:
                feedback += " Notes: " + "; ".join(feedback_parts)
        else:
            feedback = "Code verification failed. " + "; ".join(feedback_parts)
        
        return CodeVerificationResult(
            is_valid=is_valid,
            syntax_ok=syntax_ok,
            lint_issues=lint_issues,
            type_check_issues=type_check_issues,
            security_issues=security_issues,
            feedback=feedback,
        )
    
    def execute_code(
        self,
        code: str,
        timeout: int = 60,
        capture_output: bool = True,
    ) -> ExecutionResult:
        """
        Execute Python code safely.
        
        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds
            capture_output: Whether to capture stdout/stderr
        
        Returns:
            ExecutionResult with execution outcome
        """
        # Create a temporary script file
        script_path = self.work_directory / "temp_script.py"
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        start_time = time.time()
        artifacts_created = []
        
        try:
            # Execute the script
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(self.work_directory),
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONPATH": str(self.work_directory)},
            )
            
            execution_time = time.time() - start_time
            
            # Check for created files (artifacts)
            artifacts_created = self._detect_new_files()
            
            if result.returncode == 0:
                return ExecutionResult(
                    success=True,
                    output=result.stdout,
                    execution_time=execution_time,
                    artifacts_created=artifacts_created,
                )
            else:
                return ExecutionResult(
                    success=False,
                    output=result.stdout,
                    error=result.stderr,
                    execution_time=execution_time,
                    artifacts_created=artifacts_created,
                )
                
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout} seconds",
                execution_time=timeout,
                artifacts_created=artifacts_created,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time,
                artifacts_created=artifacts_created,
            )
        finally:
            # Clean up temporary script
            if script_path.exists():
                script_path.unlink()
    
    def _detect_new_files(self) -> List[str]:
        """Detect newly created files in work directory."""
        # This is a simple implementation
        # A more sophisticated version would track file timestamps
        new_files = []
        
        for ext in ['*.txt', '*.csv', '*.json', '*.png', '*.jpg', '*.pdf', '*.xlsx']:
            for file_path in self.work_directory.glob(ext):
                rel_path = str(file_path.relative_to(self.work_directory))
                if rel_path != "temp_script.py":
                    new_files.append(rel_path)
        
        return new_files
