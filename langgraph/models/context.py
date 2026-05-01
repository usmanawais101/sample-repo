"""Context management for handling work directory and files."""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from langgraph.models.session import Session


class ContextManager:
    """Manages the context directory where agent saves generated code and artifacts."""
    
    def __init__(self, session: Session):
        """Initialize context manager with a session."""
        self.session = session
        self.work_directory = Path(session.work_directory)
        
        # Create subdirectories for organization
        self.code_dir = self.work_directory / "generated_code"
        self.artifacts_dir = self.work_directory / "artifacts"
        self.input_dir = self.work_directory / "input"
        
        self._ensure_directories()
        self._scan_context_files()
    
    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.code_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)
    
    def _scan_context_files(self) -> None:
        """Scan the input directory for user-provided files."""
        if self.input_dir.exists():
            for file_path in self.input_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = str(file_path.relative_to(self.work_directory))
                    self.session.add_context_file(rel_path)
    
    def get_context_files(self) -> List[Path]:
        """Get all context files in the work directory."""
        files = []
        
        # Get user-provided input files
        if self.input_dir.exists():
            files.extend(self.input_dir.rglob("*"))
        
        # Filter to only files
        return [f for f in files if f.is_file()]
    
    def read_context_file(self, file_path: str) -> Optional[str]:
        """Read a context file by path (relative to work directory)."""
        full_path = self.work_directory / file_path
        
        if not full_path.exists() or not full_path.is_file():
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of all context files."""
        context_files = self.get_context_files()
        
        file_info = []
        for file_path in context_files:
            try:
                stat = file_path.stat()
                rel_path = str(file_path.relative_to(self.work_directory))
                file_info.append({
                    "path": rel_path,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": file_path.suffix
                })
            except Exception:
                continue
        
        return {
            "work_directory": str(self.work_directory),
            "total_files": len(file_info),
            "files": file_info,
            "context_files": self.session.context_files,
            "generated_artifacts": self.session.generated_artifacts
        }
    
    def save_generated_code(self, code: str, filename: str, description: str = "") -> str:
        """Save generated Python code to the code directory."""
        if not filename.endswith('.py'):
            filename += '.py'
        
        # Ensure unique filename
        base_name = Path(filename).stem
        counter = 1
        code_path = self.code_dir / filename
        
        while code_path.exists():
            code_path = self.code_dir / f"{base_name}_{counter}.py"
            counter += 1
        
        # Save code with metadata comment
        metadata = f'"""Generated code\nDescription: {description}\nGenerated at: {datetime.now().isoformat()}\n"""\n\n'
        
        with open(code_path, 'w', encoding='utf-8') as f:
            f.write(metadata + code)
        
        rel_path = str(code_path.relative_to(self.work_directory))
        self.session.add_context_file(rel_path)
        
        return rel_path
    
    def save_artifact(self, content: bytes, filename: str, artifact_type: str = "output") -> str:
        """Save a generated artifact to the artifacts directory."""
        artifact_path = self.artifacts_dir / filename
        
        # Ensure unique filename
        if artifact_path.exists():
            base_name = Path(filename).stem
            extension = Path(filename).suffix
            counter = 1
            
            while artifact_path.exists():
                artifact_path = self.artifacts_dir / f"{base_name}_{counter}{extension}"
                counter += 1
        
        with open(artifact_path, 'wb') as f:
            f.write(content)
        
        rel_path = str(artifact_path.relative_to(self.work_directory))
        self.session.add_generated_artifact(rel_path)
        
        return rel_path
    
    def save_text_artifact(self, content: str, filename: str) -> str:
        """Save a text-based artifact."""
        artifact_path = self.artifacts_dir / filename
        
        if artifact_path.exists():
            base_name = Path(filename).stem
            extension = Path(filename).suffix
            counter = 1
            
            while artifact_path.exists():
                artifact_path = self.artifacts_dir / f"{base_name}_{counter}{extension}"
                counter += 1
        
        with open(artifact_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        rel_path = str(artifact_path.relative_to(self.work_directory))
        self.session.add_generated_artifact(rel_path)
        
        return rel_path
    
    def get_artifact_path(self, artifact_name: str) -> Optional[Path]:
        """Get the full path to an artifact by name."""
        artifact_path = self.artifacts_dir / artifact_name
        
        if artifact_path.exists():
            return artifact_path
        
        return None
    
    def list_artifacts(self) -> List[Dict[str, Any]]:
        """List all generated artifacts."""
        artifacts = []
        
        if self.artifacts_dir.exists():
            for artifact_path in self.artifacts_dir.rglob("*"):
                if artifact_path.is_file():
                    try:
                        stat = artifact_path.stat()
                        rel_path = str(artifact_path.relative_to(self.work_directory))
                        artifacts.append({
                            "path": rel_path,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "type": artifact_path.suffix
                        })
                    except Exception:
                        continue
        
        return artifacts
    
    def clean_workspace(self, keep_inputs: bool = True) -> None:
        """Clean the workspace by removing generated files."""
        if not keep_inputs:
            # Remove everything except input directory
            for item in self.work_directory.iterdir():
                if item.name != "input" and item.is_dir():
                    shutil.rmtree(item)
                elif item.name != "input" and item.is_file():
                    item.unlink()
        else:
            # Only clean generated code and artifacts
            if self.code_dir.exists():
                shutil.rmtree(self.code_dir)
            if self.artifacts_dir.exists():
                shutil.rmtree(self.artifacts_dir)
            
            # Recreate directories
            self._ensure_directories()
        
        # Reset session tracking
        self.session.context_files = [f for f in self.session.context_files if f.startswith("input/")]
        self.session.generated_artifacts = []
