"""
Task Planner for Claude Swarm Coordinator

Analyzes project requirements and creates task breakdown for distribution among agents.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from pydantic import BaseModel, Field

from ..utils.helpers import setup_logging

logger = setup_logging(__name__)


class Task(BaseModel):
    """Individual task model."""
    
    task_id: str
    description: str
    category: str = "general"
    complexity: str = Field(default="medium", pattern="^(low|medium|high)$")
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    dependencies: List[str] = Field(default_factory=list)
    estimated_time: int = Field(default=60, description="Estimated time in minutes")
    required_skills: List[str] = Field(default_factory=list)
    assigned_agent: Optional[str] = None
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed|blocked)$")


class TaskPlan(BaseModel):
    """Complete task plan model."""
    
    project_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    total_tasks: int
    total_estimated_time: int
    complexity_breakdown: Dict[str, int]
    tasks: List[Task]


class TaskPlanner:
    """
    Analyzes project requirements and creates structured task breakdown.
    
    Supports multiple input formats (Markdown, JSON, text) and generates
    optimized task distributions for agent assignment.
    """
    
    def __init__(self, project_name: str, work_dir: Optional[Path] = None):
        """
        Initialize the task planner.
        
        Args:
            project_name: Name of the project
            work_dir: Working directory (defaults to current directory)
        """
        self.project_name = project_name
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        self.project_dir = self.work_dir / ".claude-swarm" / "projects" / project_name
        
        self.tasks: List[Task] = []
        self.task_id_counter = 1
        
        # Ensure project directory exists
        self.project_dir.mkdir(parents=True, exist_ok=True)
    
    def analyze_requirements(self, requirements_file: Path, verbose: bool = False) -> TaskPlan:
        """
        Analyze requirements file and extract tasks.
        
        Args:
            requirements_file: Path to requirements file
            verbose: Enable verbose logging
            
        Returns:
            TaskPlan object with all extracted tasks
        """
        logger.info(f"Analyzing requirements from: {requirements_file}")
        
        content = requirements_file.read_text(encoding='utf-8')
        
        # Parse based on file extension
        if requirements_file.suffix == '.md':
            self._parse_markdown_requirements(content)
        elif requirements_file.suffix == '.json':
            self._parse_json_requirements(content)
        else:
            self._parse_text_requirements(content)
        
        # Post-processing
        self._analyze_dependencies()
        self._optimize_task_order()
        
        # Create task plan
        task_plan = self._create_task_plan()
        
        # Save task plan
        self._save_task_plan(task_plan)
        
        if verbose:
            self._print_summary(task_plan)
        
        return task_plan
    
    def _parse_markdown_requirements(self, content: str) -> None:
        """Parse markdown-formatted requirements."""
        lines = content.split('\n')
        current_category = "general"
        
        for line in lines:
            line = line.strip()
            
            # Category headers (## or ###)
            if line.startswith('##'):
                current_category = line.strip('#').strip().lower().replace(' ', '_')
                continue
            
            # Task items (- or * or numbered lists)
            if line.startswith(('-', '*')) or re.match(r'^\d+\.', line):
                task_desc = re.sub(r'^[-*\d.]+\s*', '', line).strip()
                if task_desc:
                    self._add_task(task_desc, current_category)
            
            # TODO items
            if 'TODO:' in line or 'todo:' in line:
                task_desc = line.split('TODO:', 1)[-1].strip()
                if task_desc:
                    self._add_task(task_desc, current_category, priority='high')
    
    def _parse_json_requirements(self, content: str) -> None:
        """Parse JSON-formatted requirements."""
        try:
            data = json.loads(content)
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        self._add_task(
                            item.get('description', str(item)),
                            item.get('category', 'general'),
                            complexity=item.get('complexity', 'medium'),
                            dependencies=item.get('dependencies', [])
                        )
                    else:
                        self._add_task(str(item), 'general')
            
            elif isinstance(data, dict):
                for category, tasks in data.items():
                    if isinstance(tasks, list):
                        for task in tasks:
                            self._add_task(str(task), category)
                    else:
                        self._add_task(str(tasks), category)
                        
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing JSON requirements: {e}")
    
    def _parse_text_requirements(self, content: str) -> None:
        """Parse plain text requirements."""
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                self._add_task(line, 'general')
    
    def _add_task(
        self,
        description: str,
        category: str,
        complexity: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        priority: str = 'normal'
    ) -> None:
        """Add a task to the task list."""
        task_id = f"TASK-{self.task_id_counter:04d}"
        
        # Estimate complexity if not provided
        if complexity is None:
            complexity = self._estimate_complexity(description)
        
        task = Task(
            task_id=task_id,
            description=description,
            category=category,
            complexity=complexity,
            dependencies=dependencies or [],
            priority=priority,
            estimated_time=self._estimate_time(complexity),
            required_skills=self._extract_required_skills(description)
        )
        
        self.tasks.append(task)
        self.task_id_counter += 1
    
    def _estimate_complexity(self, description: str) -> str:
        """Estimate task complexity based on description."""
        desc_lower = description.lower()
        
        # High complexity indicators
        high_indicators = [
            'refactor', 'architect', 'design', 'optimize', 'migration',
            'security', 'performance', 'scale', 'distributed', 'integration'
        ]
        
        # Low complexity indicators
        low_indicators = [
            'fix', 'update', 'add', 'remove', 'rename', 'move',
            'document', 'comment', 'typo', 'format'
        ]
        
        high_count = sum(1 for word in high_indicators if word in desc_lower)
        low_count = sum(1 for word in low_indicators if word in desc_lower)
        
        if high_count > low_count:
            return 'high'
        elif low_count > 0:
            return 'low'
        else:
            return 'medium'
    
    def _estimate_time(self, complexity: str) -> int:
        """Estimate time in minutes based on complexity."""
        time_map = {
            'low': 30,
            'medium': 90,
            'high': 180
        }
        return time_map.get(complexity, 60)
    
    def _extract_required_skills(self, description: str) -> List[str]:
        """Extract required skills from task description."""
        skills = []
        desc_lower = description.lower()
        
        # Technology indicators
        tech_skills = {
            'api': ['api', 'endpoint', 'rest', 'graphql'],
            'database': ['database', 'sql', 'query', 'schema', 'migration'],
            'frontend': ['ui', 'ux', 'react', 'vue', 'angular', 'css', 'html'],
            'backend': ['server', 'api', 'endpoint', 'controller', 'service'],
            'testing': ['test', 'spec', 'tdd', 'unit', 'integration'],
            'devops': ['deploy', 'ci', 'cd', 'docker', 'kubernetes'],
            'security': ['security', 'auth', 'encrypt', 'permission', 'role']
        }
        
        for skill, keywords in tech_skills.items():
            if any(keyword in desc_lower for keyword in keywords):
                skills.append(skill)
        
        return skills or ['general']
    
    def _analyze_dependencies(self) -> None:
        """Analyze and detect task dependencies."""
        logger.debug("Analyzing task dependencies...")
        
        for i, task in enumerate(self.tasks):
            desc_lower = task.description.lower()
            
            # Look for explicit dependencies
            if 'after' in desc_lower or 'depends on' in desc_lower:
                for j, other_task in enumerate(self.tasks):
                    if i != j and other_task.description.lower() in desc_lower:
                        task.dependencies.append(other_task.task_id)
            
            # Implicit dependencies based on categories
            if task.category == 'testing' and not task.dependencies:
                # Testing tasks depend on implementation tasks
                impl_tasks = [
                    t.task_id for t in self.tasks
                    if t.category in ['feature', 'implementation'] and t.task_id != task.task_id
                ]
                task.dependencies.extend(impl_tasks[:2])  # Limit dependencies
    
    def _optimize_task_order(self) -> None:
        """Optimize task order based on dependencies."""
        # Simple topological sort by priority and dependencies
        self.tasks.sort(key=lambda t: (
            len(t.dependencies),
            {'high': 0, 'normal': 1, 'low': 2}[t.priority],
            {'high': 0, 'medium': 1, 'low': 2}[t.complexity]
        ))
    
    def _create_task_plan(self) -> TaskPlan:
        """Create a complete task plan from analyzed tasks."""
        complexity_breakdown = {
            'high': len([t for t in self.tasks if t.complexity == 'high']),
            'medium': len([t for t in self.tasks if t.complexity == 'medium']),
            'low': len([t for t in self.tasks if t.complexity == 'low'])
        }
        
        return TaskPlan(
            project_name=self.project_name,
            total_tasks=len(self.tasks),
            total_estimated_time=sum(t.estimated_time for t in self.tasks),
            complexity_breakdown=complexity_breakdown,
            tasks=self.tasks
        )
    
    def _save_task_plan(self, task_plan: TaskPlan) -> None:
        """Save task plan to project directory."""
        # Ensure tasks directory exists
        tasks_dir = self.project_dir / "tasks"
        tasks_dir.mkdir(exist_ok=True)
        
        # Save JSON version
        json_file = tasks_dir / "task_plan.json"
        with open(json_file, 'w') as f:
            json.dump(task_plan.model_dump(), f, indent=2, default=str)
        
        # Save CSV version for easy viewing
        csv_file = tasks_dir / "task_plan.csv"
        with open(csv_file, 'w') as f:
            f.write("task_id,description,category,complexity,estimated_time,dependencies,priority\n")
            for task in self.tasks:
                deps = ';'.join(task.dependencies)
                f.write(f"{task.task_id},{task.description},{task.category},"
                       f"{task.complexity},{task.estimated_time},{deps},{task.priority}\n")
        
        logger.info(f"Task plan saved to: {json_file}")
    
    def _print_summary(self, task_plan: TaskPlan) -> None:
        """Print task plan summary."""
        print(f"\n{'='*60}")
        print(f"Task Plan Summary for {self.project_name}")
        print(f"{'='*60}")
        print(f"Total tasks: {task_plan.total_tasks}")
        print(f"Total estimated time: {task_plan.total_estimated_time} minutes")
        print(f"Average time per task: {task_plan.total_estimated_time / task_plan.total_tasks:.1f} minutes")
        
        print(f"\nComplexity breakdown:")
        for complexity, count in task_plan.complexity_breakdown.items():
            print(f"  {complexity.capitalize()}: {count} tasks")
        
        print(f"\nCategory breakdown:")
        categories = {}
        for task in self.tasks:
            categories[task.category] = categories.get(task.category, 0) + 1
        
        for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"  {category}: {count} tasks")
        
        deps_count = len([t for t in self.tasks if t.dependencies])
        print(f"\nTasks with dependencies: {deps_count}")
        print(f"{'='*60}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get task plan summary as dictionary."""
        if not self.tasks:
            return {}
        
        complexity_breakdown = {
            'high': len([t for t in self.tasks if t.complexity == 'high']),
            'medium': len([t for t in self.tasks if t.complexity == 'medium']),
            'low': len([t for t in self.tasks if t.complexity == 'low'])
        }
        
        return {
            'total_tasks': len(self.tasks),
            'total_time': sum(t.estimated_time for t in self.tasks),
            'complexity_breakdown': complexity_breakdown
        }