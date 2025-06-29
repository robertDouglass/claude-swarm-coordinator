"""
Task Distributor for Claude Swarm Coordinator

Intelligently distributes tasks among agents based on complexity, dependencies, and load balancing.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from pydantic import BaseModel

from ..utils.helpers import setup_logging
from .planner import Task, TaskPlan

logger = setup_logging(__name__)


class Agent(BaseModel):
    """Agent model for task distribution."""
    
    agent_id: str
    branch_name: str
    worktree_path: str
    assigned_tasks: List[str] = []
    total_time: int = 0
    complexity_score: int = 0
    status: str = "initialized"


class TaskDistributor:
    """
    Intelligently distributes tasks among agents.
    
    Uses load balancing algorithms considering task complexity,
    dependencies, and agent capabilities.
    """
    
    def __init__(self, project_name: str, work_dir: Optional[Path] = None):
        """
        Initialize the task distributor.
        
        Args:
            project_name: Name of the project
            work_dir: Working directory (defaults to current directory)
        """
        self.project_name = project_name
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        self.project_dir = self.work_dir / ".claude-swarm" / "projects" / project_name
        
        self.tasks: List[Task] = []
        self.agents: List[Agent] = []
    
    def distribute_tasks(self, verbose: bool = False) -> Dict[str, Any]:
        """
        Distribute tasks among available agents.
        
        Args:
            verbose: Enable verbose logging
            
        Returns:
            Distribution summary
        """
        logger.info("Distributing tasks among agents...")
        
        # Load task plan and agents
        self._load_task_plan()
        self._load_agents()
        
        if not self.tasks:
            raise ValueError("No tasks found. Run task planning first.")
        
        if not self.agents:
            raise ValueError("No agents found. Initialize project first.")
        
        # Perform distribution
        self._assign_tasks()
        
        # Generate outputs
        self._generate_agent_instructions()
        self._save_distribution()
        
        # Get summary
        summary = self._get_distribution_summary()
        
        if verbose:
            self._print_distribution_summary(summary)
        
        return summary
    
    def _load_task_plan(self) -> None:
        """Load task plan from JSON file."""
        task_file = self.project_dir / "tasks" / "task_plan.json"
        
        if not task_file.exists():
            raise FileNotFoundError("Task plan not found. Run 'claude-swarm plan' first.")
        
        with open(task_file, 'r') as f:
            plan_data = json.load(f)
        
        # Convert to Task objects
        self.tasks = [Task(**task_data) for task_data in plan_data['tasks']]
        logger.info(f"Loaded {len(self.tasks)} tasks from plan")
    
    def _load_agents(self) -> None:
        """Load agent information from registry."""
        agents_file = self.project_dir / "registry" / "agents.csv"
        
        if not agents_file.exists():
            raise FileNotFoundError("Agent registry not found. Initialize project first.")
        
        with open(agents_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['agent_id']:  # Skip empty rows
                    agent = Agent(
                        agent_id=row['agent_id'],
                        branch_name=row['branch_name'],
                        worktree_path=row['worktree_path'],
                        status=row.get('status', 'initialized')
                    )
                    self.agents.append(agent)
        
        logger.info(f"Found {len(self.agents)} agents")
    
    def _assign_tasks(self) -> None:
        """Assign tasks to agents using load balancing algorithm."""
        # Sort tasks by priority and dependencies
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        sorted_tasks = sorted(
            self.tasks,
            key=lambda t: (
                len(t.dependencies),
                priority_order.get(t.priority, 1),
                -self._calculate_complexity_score(t.complexity)
            )
        )
        
        unassigned = []
        
        for task in sorted_tasks:
            assigned = False
            
            # Find eligible agents
            eligible_agents = [a for a in self.agents if self._can_assign_task(task, a)]
            
            if eligible_agents:
                # Select agent with lowest workload
                best_agent = min(eligible_agents, key=lambda a: (a.total_time, a.complexity_score))
                
                # Assign task
                self._assign_task_to_agent(task, best_agent)
                assigned = True
            
            if not assigned:
                unassigned.append(task)
        
        # Handle unassigned tasks (force assignment to least loaded agent)
        for task in unassigned:
            best_agent = min(self.agents, key=lambda a: a.total_time)
            self._assign_task_to_agent(task, best_agent)
        
        logger.info(f"Successfully distributed all {len(self.tasks)} tasks")
    
    def _can_assign_task(self, task: Task, agent: Agent) -> bool:
        """Check if a task can be assigned to an agent."""
        # Check dependencies - avoid assigning dependent tasks to same agent
        for dep_id in task.dependencies:
            dep_task = next((t for t in self.tasks if t.task_id == dep_id), None)
            if dep_task and dep_task.assigned_agent == agent.agent_id:
                return False
        
        # Check workload balance (soft limit)
        if not self.agents:
            return True
        
        avg_time = sum(a.total_time for a in self.agents) / len(self.agents)
        if agent.total_time > avg_time * 1.5:  # 50% above average
            return False
        
        return True
    
    def _assign_task_to_agent(self, task: Task, agent: Agent) -> None:
        """Assign a task to an agent."""
        task.assigned_agent = agent.agent_id
        agent.assigned_tasks.append(task.task_id)
        agent.total_time += task.estimated_time
        agent.complexity_score += self._calculate_complexity_score(task.complexity)
    
    def _calculate_complexity_score(self, complexity: str) -> int:
        """Convert complexity to numerical score."""
        scores = {'low': 1, 'medium': 3, 'high': 5}
        return scores.get(complexity, 2)
    
    def _generate_agent_instructions(self) -> None:
        """Generate specific instructions for each agent."""
        logger.info("Generating agent instructions...")
        
        # Load instruction template
        template_file = Path(__file__).parent.parent / "templates" / "agent_instructions.md"
        if template_file.exists():
            template_content = template_file.read_text()
        else:
            template_content = self._get_default_template()
        
        for agent in self.agents:
            agent_tasks = [t for t in self.tasks if t.assigned_agent == agent.agent_id]
            
            if not agent_tasks:
                continue
            
            # Generate task list
            task_list = self._generate_task_list(agent_tasks)
            
            # Replace placeholders in template
            instructions = template_content.format(
                AGENT_ID=agent.agent_id.upper(),
                PROJECT_NAME=self.project_name,
                WORKTREE_PATH=agent.worktree_path,
                BRANCH_NAME=agent.branch_name,
                COORD_DIR=self._get_coordination_dir(),
                TASK_LIST=task_list,
                NUM_TASKS=len(agent_tasks),
                TOTAL_TIME=agent.total_time,
                COMPLEXITY_SCORE=agent.complexity_score
            )
            
            # Save to project directory and worktree (if exists)
            instruction_file = self.project_dir / "tasks" / f"{agent.agent_id}_instructions.md"
            instruction_file.write_text(instructions)
            
            # Copy to worktree if it exists
            worktree_path = Path(agent.worktree_path)
            if worktree_path.exists():
                swarm_dir = worktree_path / ".swarm"
                swarm_dir.mkdir(exist_ok=True)
                
                (swarm_dir / "agent_instructions.md").write_text(instructions)
                
                # Also create tasks.md with just the task list
                (swarm_dir / "tasks.md").write_text(f"# Tasks for {agent.agent_id.upper()}\n\n{task_list}")
                
                logger.debug(f"Created instructions for {agent.agent_id}")
    
    def _generate_task_list(self, tasks: List[Task]) -> str:
        """Generate formatted task list for an agent."""
        task_list = ""
        
        # Group by category
        categories = {}
        for task in tasks:
            cat = task.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(task)
        
        for category, cat_tasks in sorted(categories.items()):
            task_list += f"### {category.replace('_', ' ').title()}\n\n"
            
            for task in cat_tasks:
                task_list += f"#### {task.task_id}: {task.description}\n"
                task_list += f"- **Complexity**: {task.complexity}\n"
                task_list += f"- **Priority**: {task.priority}\n"
                task_list += f"- **Estimated time**: {task.estimated_time} minutes\n"
                
                if task.dependencies:
                    task_list += f"- **Dependencies**: {', '.join(task.dependencies)}\n"
                
                if task.required_skills:
                    task_list += f"- **Required skills**: {', '.join(task.required_skills)}\n"
                
                task_list += "\n"
        
        return task_list
    
    def _get_coordination_dir(self) -> str:
        """Get coordination directory path."""
        return str(Path.cwd() / ".swarm-coordination" / self.project_name)
    
    def _get_default_template(self) -> str:
        """Get default agent instruction template."""
        return """# Claude Swarm Agent Instructions

## Your Identity
You are **{AGENT_ID}** working on the **{PROJECT_NAME}** project.

## Your Workspace
- **Working Directory**: `{WORKTREE_PATH}`
- **Branch**: `{BRANCH_NAME}`
- **Coordination Directory**: `{COORD_DIR}`

## Your Assigned Tasks ({NUM_TASKS} tasks, ~{TOTAL_TIME} minutes)

{TASK_LIST}

## Critical Rules
1. **COMMIT FREQUENTLY** - After each task completion
2. **Read task requirements carefully**
3. **Report blockers immediately**
4. **Update progress log**
5. **Test your changes**

## Workflow
1. Start task: Update progress log
2. Implement solution
3. Test changes
4. Commit with descriptive message
5. Update progress log
6. Move to next task

## Communication
- Report blockers: Create file in `{COORD_DIR}/blockers/`
- Share resources: Document in `{COORD_DIR}/shared/`
- Progress updates: Update `.swarm/progress.log`

Good luck!
"""
    
    def _save_distribution(self) -> None:
        """Save task distribution to files."""
        # Update task registry with assignments
        registry_file = self.project_dir / "registry" / "tasks.csv"
        
        with open(registry_file, 'w') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'task_id', 'description', 'category', 'complexity',
                'dependencies', 'assigned_agent', 'status', 'start_time',
                'end_time', 'commits'
            ])
            writer.writeheader()
            
            for task in self.tasks:
                writer.writerow({
                    'task_id': task.task_id,
                    'description': task.description,
                    'category': task.category,
                    'complexity': task.complexity,
                    'dependencies': ';'.join(task.dependencies),
                    'assigned_agent': task.assigned_agent or '',
                    'status': task.status,
                    'start_time': '',
                    'end_time': '',
                    'commits': ''
                })
        
        # Save distribution summary
        summary_file = self.project_dir / "tasks" / "distribution_summary.json"
        
        summary = {
            'project_name': self.project_name,
            'distributed_at': datetime.utcnow().isoformat(),
            'total_tasks': len(self.tasks),
            'agents': []
        }
        
        for agent in self.agents:
            agent_summary = {
                'agent_id': agent.agent_id,
                'tasks_assigned': len(agent.assigned_tasks),
                'total_time': agent.total_time,
                'complexity_score': agent.complexity_score,
                'task_ids': agent.assigned_tasks
            }
            summary['agents'].append(agent_summary)
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Distribution saved to: {summary_file}")
    
    def _get_distribution_summary(self) -> Dict[str, Any]:
        """Get distribution summary."""
        return {
            'total_tasks': len(self.tasks),
            'total_agents': len(self.agents),
            'agent_assignments': {
                agent.agent_id: {
                    'tasks': len(agent.assigned_tasks),
                    'time': agent.total_time,
                    'complexity': agent.complexity_score
                }
                for agent in self.agents
            }
        }
    
    def _print_distribution_summary(self, summary: Dict[str, Any]) -> None:
        """Print distribution summary."""
        print(f"\n{'='*60}")
        print("Task Distribution Summary")
        print(f"{'='*60}")
        
        for agent in sorted(self.agents, key=lambda a: a.agent_id):
            tasks = len(agent.assigned_tasks)
            if tasks > 0:
                print(f"\n{agent.agent_id.upper()}:")
                print(f"  Tasks: {tasks}")
                print(f"  Time: {agent.total_time} min ({agent.total_time/60:.1f} hours)")
                print(f"  Complexity: {agent.complexity_score}")
        
        # Balance metrics
        times = [a.total_time for a in self.agents if a.assigned_tasks]
        if times:
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            
            print(f"\nLoad Balance:")
            print(f"  Average: {avg_time:.0f} min")
            print(f"  Max: {max_time:.0f} min")
            print(f"  Min: {min_time:.0f} min")
            print(f"  Balance ratio: {max_time/min_time:.2f}x")
        
        print(f"{'='*60}")