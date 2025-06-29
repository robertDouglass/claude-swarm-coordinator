"""
SwarmCoordinator - Main coordination class for managing agent swarms.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import git
from pydantic import BaseModel, Field

from ..utils.git import GitWorktreeManager
from ..utils.helpers import generate_id, setup_logging
from .planner import TaskPlanner
from .distributor import TaskDistributor

logger = setup_logging(__name__)


class ProjectConfig(BaseModel):
    """Configuration for a swarm project."""
    
    project_name: str
    num_agents: int
    branch_prefix: str = "swarm-agent"
    worktree_dir: str = "../swarm-worktrees"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "initialized"
    description: Optional[str] = None


class SwarmCoordinator:
    """
    Main coordinator for managing Claude Code agent swarms.
    
    Handles project initialization, agent coordination, and lifecycle management.
    """
    
    def __init__(self, project_name: str, work_dir: Optional[Path] = None):
        """
        Initialize the swarm coordinator.
        
        Args:
            project_name: Name of the project
            work_dir: Working directory (defaults to current directory)
        """
        self.project_name = project_name
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        
        # Initialize paths
        self.projects_dir = self.work_dir / ".claude-swarm" / "projects"
        self.project_dir = self.projects_dir / project_name
        
        # Ensure directories exist
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        
        # Git repository handling
        try:
            self.repo = git.Repo(self.work_dir, search_parent_directories=True)
            self.repo_root = Path(self.repo.working_tree_dir)
        except git.InvalidGitRepositoryError:
            raise ValueError(f"Not in a git repository: {self.work_dir}")
        
        # Initialize managers
        self.git_manager = GitWorktreeManager(self.repo_root)
        
    @classmethod
    def get_active_project(cls) -> Optional[str]:
        """Get the currently active project name."""
        active_file = Path.cwd() / ".claude-swarm" / ".active_project"
        if active_file.exists():
            return active_file.read_text().strip()
        return None
    
    def set_active_project(self) -> None:
        """Set this project as the active project."""
        active_file = self.work_dir / ".claude-swarm" / ".active_project"
        active_file.parent.mkdir(parents=True, exist_ok=True)
        active_file.write_text(self.project_name)
    
    def initialize_project(
        self,
        num_agents: int = 10,
        description: Optional[str] = None,
        verbose: bool = False
    ) -> None:
        """
        Initialize a new swarm project.
        
        Args:
            num_agents: Number of agents to create
            description: Project description
            verbose: Enable verbose logging
        """
        logger.info(f"Initializing project: {self.project_name}")
        
        # Create project configuration
        config = ProjectConfig(
            project_name=self.project_name,
            num_agents=num_agents,
            description=description
        )
        
        # Create project directory structure
        directories = [
            "config",
            "tasks", 
            "registry",
            "logs",
            "reports",
            "coordination",
            "templates"
        ]
        
        for dir_name in directories:
            (self.project_dir / dir_name).mkdir(parents=True, exist_ok=True)
        
        # Save configuration
        config_file = self.project_dir / "config" / "swarm.json"
        with open(config_file, 'w') as f:
            json.dump(config.model_dump(), f, indent=2, default=str)
        
        # Initialize registries
        self._create_registries(num_agents)
        
        # Set as active project
        self.set_active_project()
        
        # Create coordination directory in repo
        coord_dir = self.repo_root / ".swarm-coordination" / self.project_name
        coord_dirs = ["blockers", "shared", "dependencies", "reports", "messages"]
        for dir_name in coord_dirs:
            (coord_dir / dir_name).mkdir(parents=True, exist_ok=True)
        
        # Create README for coordination
        readme_content = f"""# Swarm Coordination Directory

This directory contains coordination files for the {self.project_name} swarm.

## Structure
- blockers/: Agent blocker notifications
- shared/: Shared resources between agents  
- dependencies/: Inter-agent dependencies
- reports/: Daily status reports
- messages/: Inter-agent messages

## Important
This directory is in the main repository for coordination purposes.
Agents should read from here but commit changes through their own branches.
"""
        (coord_dir / "README.md").write_text(readme_content)
        
        logger.info(f"Project {self.project_name} initialized successfully")
    
    def _create_registries(self, num_agents: int) -> None:
        """Create agent and task registries."""
        # Agent registry
        agent_registry = self.project_dir / "registry" / "agents.csv"
        with open(agent_registry, 'w') as f:
            f.write("agent_id,branch_name,worktree_path,status,tasks_assigned,tasks_completed,last_commit,last_update\n")
        
        # Task registry
        task_registry = self.project_dir / "registry" / "tasks.csv"
        with open(task_registry, 'w') as f:
            f.write("task_id,description,category,complexity,dependencies,assigned_agent,status,start_time,end_time,commits\n")
        
        # Initialize empty agent entries
        for i in range(1, num_agents + 1):
            agent_id = f"agent-{i}"
            branch_name = f"swarm-agent-{self.project_name}-{i}"
            # Agent entries will be populated when worktrees are created
    
    def launch_swarm(self, mode: str = "parallel", verbose: bool = False) -> None:
        """
        Launch the agent swarm.
        
        Args:
            mode: Launch mode ("parallel" or "sequential")
            verbose: Enable verbose logging
        """
        logger.info(f"Launching swarm in {mode} mode")
        
        config = self._load_config()
        
        # Create worktrees
        self._create_worktrees(config, verbose)
        
        # Distribute tasks (if task plan exists)
        task_plan_file = self.project_dir / "tasks" / "task_plan.json"
        if task_plan_file.exists():
            distributor = TaskDistributor(self.project_name)
            distributor.distribute_tasks(verbose=verbose)
        else:
            logger.warning("No task plan found. Run 'claude-swarm plan' first.")
        
        # Generate launch instructions
        self._generate_launch_instructions(config, mode)
        
        logger.info("Swarm launched successfully")
    
    def _create_worktrees(self, config: ProjectConfig, verbose: bool = False) -> None:
        """Create git worktrees for all agents."""
        logger.info(f"Creating {config.num_agents} worktrees")
        
        base_branch = self.repo.active_branch.name
        worktree_parent = self.repo_root / config.worktree_dir / config.project_name
        worktree_parent.mkdir(parents=True, exist_ok=True)
        
        for i in range(1, config.num_agents + 1):
            agent_id = f"agent-{i}"
            branch_name = f"{config.branch_prefix}-{config.project_name}-{i}"
            worktree_path = worktree_parent / agent_id
            
            # Create worktree
            self.git_manager.create_worktree(
                path=worktree_path,
                branch=branch_name,
                base_branch=base_branch
            )
            
            # Create agent configuration
            agent_config_dir = worktree_path / ".swarm"
            agent_config_dir.mkdir(exist_ok=True)
            
            agent_config = {
                "agent_id": agent_id,
                "project_name": config.project_name,
                "branch_name": branch_name,
                "worktree_path": str(worktree_path),
                "created_at": datetime.utcnow().isoformat(),
                "base_branch": base_branch
            }
            
            with open(agent_config_dir / "agent.json", 'w') as f:
                json.dump(agent_config, f, indent=2)
            
            # Initialize progress log
            progress_file = agent_config_dir / "progress.log"
            progress_file.write_text(f"Agent {i} initialized at {datetime.utcnow()}\n")
            
            # Update agent registry
            self._update_agent_registry(agent_id, branch_name, str(worktree_path))
            
            if verbose:
                logger.info(f"Created worktree for {agent_id} at {worktree_path}")
    
    def _update_agent_registry(self, agent_id: str, branch_name: str, worktree_path: str) -> None:
        """Update the agent registry with new agent information."""
        registry_file = self.project_dir / "registry" / "agents.csv"
        
        # Read existing entries
        entries = []
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                lines = f.readlines()
                entries = lines[1:]  # Skip header
        
        # Add new entry
        new_entry = f"{agent_id},{branch_name},{worktree_path},initialized,0,0,,{datetime.utcnow().isoformat()}\n"
        entries.append(new_entry)
        
        # Write back
        with open(registry_file, 'w') as f:
            f.write("agent_id,branch_name,worktree_path,status,tasks_assigned,tasks_completed,last_commit,last_update\n")
            f.writelines(entries)
    
    def _generate_launch_instructions(self, config: ProjectConfig, mode: str) -> None:
        """Generate launch instructions for agents."""
        launch_dir = self.project_dir / "launch"
        launch_dir.mkdir(exist_ok=True)
        
        # Generate individual launch scripts
        for i in range(1, config.num_agents + 1):
            agent_id = f"agent-{i}"
            worktree_path = self.repo_root / config.worktree_dir / config.project_name / agent_id
            
            script_content = f"""#!/bin/bash
echo "Starting {agent_id} for {config.project_name}"
echo "Worktree: {worktree_path}"
echo ""
echo "Instructions:"
echo "1. cd {worktree_path}"
echo "2. Run 'claude' to start Claude Code"
echo "3. Tell Claude: 'Read .swarm/agent_instructions.md and begin working on assigned tasks'"
echo ""
echo "This agent has been assigned specific tasks listed in .swarm/tasks.md"
echo ""
echo "Press Enter to continue..."
read
"""
            
            script_file = launch_dir / f"start_{agent_id}.sh"
            script_file.write_text(script_content)
            script_file.chmod(0o755)
        
        # Generate README
        readme_content = f"""# Agent Launch Instructions

## Manual Launch
Open {config.num_agents} terminal windows and run:

{chr(10).join([f"Terminal {i}: ./start_agent-{i}.sh" for i in range(1, config.num_agents + 1)])}

## Direct Agent Start
For each agent, you can also:

{chr(10).join([f"Agent {i}:" + chr(10) + f"  cd {self.repo_root / config.worktree_dir / config.project_name / f'agent-{i}'}" + chr(10) + "  claude" + chr(10) for i in range(1, config.num_agents + 1)])}

## Important Notes
- Each agent must work in their assigned worktree
- Agents should read .swarm/agent_instructions.md first
- Tasks are listed in .swarm/tasks.md
- Commit frequently (after each task)
- Report blockers to coordination directory
"""
        
        (launch_dir / "README.md").write_text(readme_content)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current swarm status."""
        config = self._load_config()
        
        # Count active agents (simplified)
        active_agents = 0
        total_agents = config.num_agents
        
        # Count tasks (if task registry exists)
        task_registry = self.project_dir / "registry" / "tasks.csv"
        total_tasks = 0
        completed_tasks = 0
        
        if task_registry.exists():
            with open(task_registry, 'r') as f:
                lines = f.readlines()[1:]  # Skip header
                total_tasks = len(lines)
                completed_tasks = sum(1 for line in lines if ",completed," in line)
        
        # Count blockers (simplified)
        coord_dir = self.repo_root / ".swarm-coordination" / self.project_name / "blockers"
        open_blockers = 0
        if coord_dir.exists():
            open_blockers = len(list(coord_dir.glob("BLOCKER-*.json")))
        
        # Recent commits (simplified)
        recent_commits = 0
        try:
            commits = list(self.repo.iter_commits(max_count=10))
            recent_commits = len(commits)
        except:
            pass
        
        return {
            "active_agents": active_agents,
            "total_agents": total_agents,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "open_blockers": open_blockers,
            "recent_commits": recent_commits
        }
    
    def cleanup_project(self, verbose: bool = False) -> None:
        """Clean up worktrees and project data."""
        logger.info(f"Cleaning up project: {self.project_name}")
        
        config = self._load_config()
        
        # Create archive tag
        archive_tag = f"archive/{self.project_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Archive branches
        for i in range(1, config.num_agents + 1):
            branch_name = f"{config.branch_prefix}-{self.project_name}-{i}"
            try:
                self.repo.create_tag(f"{archive_tag}-agent-{i}", branch_name)
                if verbose:
                    logger.info(f"Archived branch {branch_name}")
            except:
                pass
        
        # Remove worktrees
        worktree_parent = self.repo_root / config.worktree_dir / config.project_name
        if worktree_parent.exists():
            for i in range(1, config.num_agents + 1):
                agent_id = f"agent-{i}"
                worktree_path = worktree_parent / agent_id
                if worktree_path.exists():
                    self.git_manager.remove_worktree(worktree_path)
                    if verbose:
                        logger.info(f"Removed worktree: {worktree_path}")
        
        # Archive coordination directory
        coord_dir = self.repo_root / ".swarm-coordination" / self.project_name
        if coord_dir.exists():
            import shutil
            archive_path = self.project_dir / f"coordination-archive-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
            shutil.make_archive(str(archive_path.with_suffix('')), 'gztar', coord_dir)
            shutil.rmtree(coord_dir)
            if verbose:
                logger.info(f"Archived coordination directory to {archive_path}")
        
        # Update project status
        config.status = "cleaned"
        config_file = self.project_dir / "config" / "swarm.json"
        with open(config_file, 'w') as f:
            json.dump(config.model_dump(), f, indent=2, default=str)
        
        logger.info("Project cleanup completed")
    
    def _load_config(self) -> ProjectConfig:
        """Load project configuration."""
        config_file = self.project_dir / "config" / "swarm.json"
        if not config_file.exists():
            raise FileNotFoundError(f"Project configuration not found: {config_file}")
        
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        return ProjectConfig(**config_data)