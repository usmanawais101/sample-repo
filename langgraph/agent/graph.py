"""LangGraph workflow for the coding agent."""

import uuid
from typing import Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.models.session import Task, Session, AgentState, TaskStatus
from langgraph.agent.llm_service import LLMService
from langgraph.agent.code_executor import CodeExecutor
from langgraph.models.context import ContextManager
from langgraph.agent.nodes import (
    generate_code_node,
    verify_code_node,
    execute_code_node,
    verify_artifact_node,
    generate_response_node,
    route_after_code_generation,
    route_after_verification,
    route_after_execution,
    route_after_artifact_verification,
)


class CodingAgentGraph:
    """
    LangGraph-based coding agent that generates, verifies, executes code,
    and validates artifacts.
    """
    
    def __init__(
        self,
        session: Session,
        llm_service: Optional[LLMService] = None,
        db_path: str = "sessions.db",
    ):
        """
        Initialize the coding agent graph.
        
        Args:
            session: User session with work directory
            llm_service: LLM service instance (created if not provided)
            db_path: Path to SQLite database for sessions
        """
        self.session = session
        self.context_manager = ContextManager(session)
        
        # Initialize LLM service if not provided
        if llm_service is None:
            self.llm_service = LLMService()
        else:
            self.llm_service = llm_service
        
        # Initialize code executor
        self.code_executor = CodeExecutor(session.work_directory)
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        
        # Define the state schema using AgentState
        builder = StateGraph(AgentState)
        
        # Add nodes - we need to wrap them to inject dependencies
        builder.add_node(
            "generate_code",
            lambda state: generate_code_node(state, self.llm_service, self.context_manager),
        )
        builder.add_node(
            "verify_code",
            lambda state: verify_code_node(state, self.llm_service, self.code_executor),
        )
        builder.add_node(
            "execute_code",
            lambda state: execute_code_node(state, self.code_executor),
        )
        builder.add_node(
            "verify_artifact",
            lambda state: verify_artifact_node(state, self.llm_service, self.context_manager),
        )
        builder.add_node(
            "generate_response",
            lambda state: generate_response_node(state, self.llm_service, self.context_manager),
        )
        
        # Set entry point
        builder.set_entry_point("generate_code")
        
        # Add conditional edges based on task status
        builder.add_conditional_edges(
            "generate_code",
            route_after_code_generation,
            {
                "verify_code": "verify_code",
                "failed": END,
            },
        )
        
        builder.add_conditional_edges(
            "verify_code",
            route_after_verification,
            {
                "execute_code": "execute_code",
                "generate_code": "generate_code",
                "failed": END,
            },
        )
        
        builder.add_conditional_edges(
            "execute_code",
            route_after_execution,
            {
                "verify_artifact": "verify_artifact",
                "generate_code": "generate_code",
                "failed": END,
            },
        )
        
        builder.add_conditional_edges(
            "verify_artifact",
            route_after_artifact_verification,
            {
                "generate_response": "generate_response",
                "generate_code": "generate_code",
                "failed": END,
            },
        )
        
        builder.add_edge("generate_response", END)
        
        # Compile the graph
        compiled_graph = builder.compile()
        
        # Generate and save Mermaid diagram
        self._save_mermaid_diagram(compiled_graph)
        
        return compiled_graph
    
    def _save_mermaid_diagram(self, compiled_graph: StateGraph) -> None:
        """Generate and save a Mermaid representation of the graph."""
        import os
        
        try:
            # Get the graph structure
            graph_dict = compiled_graph.get_graph()
            
            # Build Mermaid syntax
            mermaid_lines = ["graph TD"]
            
            # Add nodes
            for node_name in graph_dict.nodes:
                # Clean node name for Mermaid
                clean_name = node_name.replace(" ", "_").replace("-", "_")
                mermaid_lines.append(f"    {clean_name}[\"{node_name}\"]")
            
            # Add edges
            for edge in graph_dict.edges:
                source = edge[0].replace(" ", "_").replace("-", "_")
                target = edge[1].replace(" ", "_").replace("-", "_")
                mermaid_lines.append(f"    {source} --> {target}")
            
            # Add conditional edges if available
            if hasattr(graph_dict, 'conditional_edges'):
                for condition, edges in graph_dict.conditional_edges.items():
                    source = condition.replace(" ", "_").replace("-", "_")
                    for target, label in edges.items():
                        target_clean = target.replace(" ", "_").replace("-", "_")
                        mermaid_lines.append(f"    {source} -- {label} --> {target_clean}")
            
            mermaid_content = "\n".join(mermaid_lines)
            
            # Save to file in the context directory
            mermaid_path = os.path.join(
                self.context_manager.work_directory,
                "agent_workflow.mmd"
            )
            
            with open(mermaid_path, 'w') as f:
                f.write(mermaid_content)
            
            print(f"Mermaid diagram saved to: {mermaid_path}")
            
        except Exception as e:
            print(f"Warning: Could not generate Mermaid diagram: {e}")
    
    def run(
        self,
        task_description: str,
        max_iterations: int = 50,
    ) -> Dict[str, Any]:
        """
        Run the agent workflow for a given task.
        
        Args:
            task_description: Description of what the user wants to accomplish
            max_iterations: Maximum number of graph iterations
        
        Returns:
            Dictionary with final state and result
        """
        # Create a new task
        task = Task(
            task_id=str(uuid.uuid4()),
            session_id=self.session.session_id,
            description=task_description,
            max_retries=10,
        )
        
        # Create initial state
        initial_state = AgentState(
            task=task,
            session=self.session,
            current_step="init",
        )
        
        # Run the graph
        config = {"recursion_limit": max_iterations}
        
        try:
            final_state = self.graph.invoke(initial_state, config=config)
            
            # Update session in database
            from langgraph.models.user_management import UserManager
            user_manager = UserManager()
            user_manager.update_session(final_state["session"])
            
            # Prepare result
            result = {
                "success": final_state["task"].status == TaskStatus.ARTIFACT_VERIFIED,
                "task": final_state["task"],
                "session": final_state["session"],
                "messages": final_state.get("messages", []),
                "errors": final_state.get("errors", []),
                "final_step": final_state.get("current_step", "unknown"),
            }
            
            # Add artifact path if successful
            if result["success"] and final_state["task"].execution_result:
                artifacts = final_state["task"].execution_result.artifacts_created
                if artifacts:
                    result["artifact_path"] = artifacts[0]
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task": task,
                "session": self.session,
                "messages": initial_state.messages,
                "errors": [str(e)],
            }
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get summary of context files and artifacts."""
        return self.context_manager.get_context_summary()
    
    def list_artifacts(self) -> list:
        """List all generated artifacts."""
        return self.context_manager.list_artifacts()
