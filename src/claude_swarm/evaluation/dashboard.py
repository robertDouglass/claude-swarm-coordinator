"""
Real-time Dashboard for Claude Swarm Monitoring

Provides visual monitoring of agent progress, task completion, and system health.
"""

import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import git
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.text import Text

from ..utils.helpers import setup_logging

logger = setup_logging(__name__)
console = Console()


class SwarmDashboard:
    """
    Real-time dashboard for monitoring Claude Code agent swarms.
    
    Provides live updates on agent status, task progress, blockers,
    and performance metrics.
    """
    
    def __init__(self, project_name: str, work_dir: Optional[Path] = None):
        """
        Initialize the swarm dashboard.
        
        Args:
            project_name: Name of the project to monitor
            work_dir: Working directory (defaults to current directory)
        """
        self.project_name = project_name
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()
        self.project_dir = self.work_dir / ".claude-swarm" / "projects" / project_name
        
        # Find git repository
        try:
            self.repo = git.Repo(self.work_dir, search_parent_directories=True)
            self.repo_root = Path(self.repo.working_tree_dir)
        except git.InvalidGitRepositoryError:
            raise ValueError(f"Not in a git repository: {self.work_dir}")
        
        self.coord_dir = self.repo_root / ".swarm-coordination" / project_name
    
    def run(self, refresh_interval: int = 30) -> None:
        """
        Run the dashboard with auto-refresh.
        
        Args:
            refresh_interval: Refresh interval in seconds
        """
        try:
            with Live(self._generate_layout(), refresh_per_second=1/refresh_interval) as live:
                while True:
                    live.update(self._generate_layout())
                    time.sleep(refresh_interval)
        except KeyboardInterrupt:
            console.print("\n👋 Dashboard closed.")
    
    def _generate_layout(self) -> Panel:
        """Generate the complete dashboard layout."""
        # Get all data
        agents = self._get_agent_status()
        task_stats = self._get_task_status()
        blockers = self._get_blockers()
        recent_activity = self._get_recent_activity()
        metrics = self._calculate_metrics(agents, task_stats)
        
        # Create sections
        header = self._create_header()
        overview = self._create_overview(metrics, task_stats, len(blockers))
        task_progress = self._create_task_progress(task_stats)
        agent_table = self._create_agent_table(agents, task_stats)
        blockers_section = self._create_blockers_section(blockers)
        activity_section = self._create_activity_section(recent_activity)
        
        # Combine all sections
        content = Text()
        content.append(header)
        content.append("\n\n")
        content.append(overview)
        content.append("\n\n")
        content.append(task_progress)
        content.append("\n\n")
        content.append(agent_table)
        
        if blockers:
            content.append("\n\n")
            content.append(blockers_section)
        
        if recent_activity:
            content.append("\n\n")
            content.append(activity_section)
        
        return Panel(
            content,
            title=f"Claude Swarm Dashboard - {self.project_name}",
            border_style="blue"
        )
    
    def _create_header(self) -> str:
        """Create dashboard header."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"📊 CLAUDE SWARM DASHBOARD - {self.project_name.upper()}\nUpdated: {timestamp}"
    
    def _create_overview(self, metrics: Dict[str, Any], task_stats: Dict[str, Any], blocker_count: int) -> str:
        """Create overview section."""
        overview = "📈 OVERVIEW\n"
        overview += "─" * 40 + "\n"
        overview += f"Active Agents:     {metrics['active_agents']}/{metrics['total_agents']}\n"
        overview += f"Task Progress:     {task_stats['completed']}/{task_stats['total']} "
        overview += f"({metrics['completion_rate']:.1f}%)\n"
        overview += f"Open Blockers:     {blocker_count}\n"
        overview += f"Est. Completion:   {metrics['estimated_completion']}\n"
        return overview
    
    def _create_task_progress(self, task_stats: Dict[str, Any]) -> str:
        """Create task progress section."""
        progress_text = "📋 TASK STATUS\n"
        progress_text += "─" * 40 + "\n"
        progress_text += f"✅ Completed:    {task_stats['completed']:3d}\n"
        progress_text += f"🔄 In Progress:  {task_stats['in_progress']:3d}\n"
        progress_text += f"⏳ Pending:      {task_stats['pending']:3d}\n"
        progress_text += f"🚫 Blocked:      {task_stats['blocked']:3d}\n"
        return progress_text
    
    def _create_agent_table(self, agents: List[Dict[str, Any]], task_stats: Dict[str, Any]) -> str:
        """Create agent status table."""
        table_text = "🤖 AGENT STATUS\n"
        table_text += "─" * 80 + "\n"
        table_text += f"{'Agent':<10} {'Branch':<25} {'Tasks':<15} {'Commits':<10} {'Last Activity':<20}\n"
        table_text += "─" * 80 + "\n"
        
        for agent in sorted(agents, key=lambda a: a['agent_id']):
            agent_id = agent['agent_id']
            branch = agent['branch_name'][:23] + '..' if len(agent['branch_name']) > 25 else agent['branch_name']
            
            agent_tasks = task_stats['by_agent'].get(agent_id, {'assigned': 0, 'completed': 0})
            tasks = f"{agent_tasks['completed']}/{agent_tasks['assigned']}"
            
            status_icon = "🟢" if agent['last_commit'] and 'minute' in agent['last_commit'] else "🟡"
            
            table_text += f"{status_icon} {agent_id:<8} {branch:<25} {tasks:<15} "
            table_text += f"{agent['commits']:<10} {agent['last_commit']:<20}\n"
        
        return table_text
    
    def _create_blockers_section(self, blockers: List[Dict[str, Any]]) -> str:
        """Create blockers section."""
        if not blockers:
            return ""
        
        blockers_text = "🚨 ACTIVE BLOCKERS\n"
        blockers_text += "─" * 80 + "\n"
        
        for blocker in blockers[:5]:  # Show max 5
            blockers_text += f"[{blocker['agent_id']}] {blocker['title'][:60]}\n"
        
        return blockers_text
    
    def _create_activity_section(self, activity: List[Dict[str, Any]]) -> str:
        """Create recent activity section."""
        if not activity:
            return ""
        
        activity_text = "📝 RECENT ACTIVITY (Last 30 min)\n"
        activity_text += "─" * 80 + "\n"
        
        for act in activity[-5:]:  # Show last 5
            branch_short = act['branch'].split('/')[-1][:15]
            msg = act['message'][:40] + '..' if len(act['message']) > 40 else act['message']
            activity_text += f"[{branch_short}] {act['commit']} - {msg} ({act['time']})\n"
        
        return activity_text
    
    def _get_agent_status(self) -> List[Dict[str, Any]]:
        """Get current status of all agents."""
        agents = []
        agents_file = self.project_dir / "registry" / "agents.csv"
        
        if not agents_file.exists():
            return agents
        
        with open(agents_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('agent_id'):
                    continue
                
                agent = row.copy()
                
                # Get latest commit info
                branch = row['branch_name']
                try:
                    # Get commit count
                    result = subprocess.run(
                        ['git', 'rev-list', '--count', f'main..{branch}'],
                        capture_output=True, text=True, cwd=self.repo_root
                    )
                    agent['commits'] = int(result.stdout.strip()) if result.returncode == 0 else 0
                    
                    # Get last commit time
                    result = subprocess.run(
                        ['git', 'log', '-1', '--format=%ar', branch],
                        capture_output=True, text=True, cwd=self.repo_root
                    )
                    agent['last_commit'] = result.stdout.strip() if result.returncode == 0 else 'Never'
                    
                except Exception:
                    agent['commits'] = 0
                    agent['last_commit'] = 'Unknown'
                
                agents.append(agent)
        
        return agents
    
    def _get_task_status(self) -> Dict[str, Any]:
        """Get current task completion status."""
        task_stats = {
            'total': 0,
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
            'blocked': 0,
            'by_agent': defaultdict(lambda: {'assigned': 0, 'completed': 0})
        }
        
        tasks_file = self.project_dir / "registry" / "tasks.csv"
        
        if not tasks_file.exists():
            return task_stats
        
        with open(tasks_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('task_id'):
                    continue
                
                task_stats['total'] += 1
                status = row.get('status', 'pending')
                
                if status == 'pending':
                    task_stats['pending'] += 1
                elif status == 'in_progress':
                    task_stats['in_progress'] += 1
                elif status == 'completed':
                    task_stats['completed'] += 1
                elif status == 'blocked':
                    task_stats['blocked'] += 1
                
                agent = row.get('assigned_agent', '')
                if agent:
                    task_stats['by_agent'][agent]['assigned'] += 1
                    if status == 'completed':
                        task_stats['by_agent'][agent]['completed'] += 1
        
        return task_stats
    
    def _get_blockers(self) -> List[Dict[str, Any]]:
        """Get current blockers."""
        blockers = []
        blockers_dir = self.coord_dir / "blockers"
        
        if not blockers_dir.exists():
            return blockers
        
        for blocker_file in blockers_dir.glob("BLOCKER-*.json"):
            try:
                with open(blocker_file, 'r') as f:
                    blocker = json.load(f)
                    if blocker.get('status') == 'open':
                        blockers.append(blocker)
            except Exception:
                pass
        
        return blockers
    
    def _get_recent_activity(self, minutes: int = 30) -> List[Dict[str, Any]]:
        """Get recent commit activity."""
        activity = []
        
        try:
            # Get all swarm branches
            result = subprocess.run(
                ['git', 'branch', '-r'],
                capture_output=True, text=True, cwd=self.repo_root
            )
            
            if result.returncode != 0:
                return activity
            
            branches = [
                b.strip() for b in result.stdout.split('\n')
                if f'swarm-agent-{self.project_name}' in b
            ]
            
            for branch in branches:
                # Get recent commits
                result = subprocess.run(
                    ['git', 'log', branch, '--since', f'{minutes} minutes ago',
                     '--format=%h|%ar|%s|%an'],
                    capture_output=True, text=True, cwd=self.repo_root
                )
                
                if result.returncode == 0 and result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        parts = line.split('|')
                        if len(parts) == 4:
                            activity.append({
                                'commit': parts[0],
                                'time': parts[1],
                                'message': parts[2],
                                'author': parts[3],
                                'branch': branch
                            })
        
        except Exception as e:
            logger.error(f"Failed to get recent activity: {e}")
        
        return sorted(activity, key=lambda x: x['time'])
    
    def _calculate_metrics(self, agents: List[Dict[str, Any]], task_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate performance metrics."""
        metrics = {
            'completion_rate': 0,
            'avg_commits_per_agent': 0,
            'active_agents': 0,
            'total_agents': len(agents),
            'tasks_per_hour': 0,
            'estimated_completion': 'Unknown'
        }
        
        if not agents:
            return metrics
        
        # Completion rate
        if task_stats['total'] > 0:
            metrics['completion_rate'] = (task_stats['completed'] / task_stats['total']) * 100
        
        # Average commits
        total_commits = sum(a['commits'] for a in agents)
        metrics['avg_commits_per_agent'] = total_commits / len(agents)
        
        # Active agents (committed in last hour)
        for agent in agents:
            last_commit = agent.get('last_commit', '')
            if last_commit and ('minute' in last_commit or 'hour ago' in last_commit):
                metrics['active_agents'] += 1
        
        # Simple completion estimate
        if task_stats['completed'] > 0 and metrics['active_agents'] > 0:
            remaining = task_stats['total'] - task_stats['completed']
            # Very simplified estimation
            if remaining > 0:
                hours_remaining = remaining / max(1, metrics['active_agents'])
                metrics['estimated_completion'] = f"{hours_remaining:.1f} hours"
            else:
                metrics['estimated_completion'] = "Complete!"
        
        return metrics
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current swarm status.
        
        Returns:
            Status summary dictionary
        """
        agents = self._get_agent_status()
        task_stats = self._get_task_status()
        blockers = self._get_blockers()
        metrics = self._calculate_metrics(agents, task_stats)
        
        return {
            'project_name': self.project_name,
            'timestamp': datetime.now().isoformat(),
            'agents': {
                'total': len(agents),
                'active': metrics['active_agents']
            },
            'tasks': task_stats,
            'blockers': len(blockers),
            'metrics': metrics
        }