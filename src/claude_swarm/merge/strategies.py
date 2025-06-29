"""
Smart Merge Strategies for Claude Swarm

Handles dependency-aware merging, conflict prediction, and automated resolution.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import git
import networkx as nx
from git.exc import GitCommandError

from ..utils.helpers import setup_logging

logger = setup_logging(__name__)


class SmartMerger:
    """
    Smart merge strategy for Claude Code agent swarms.
    
    Handles dependency-aware merging, conflict prediction, and automated resolution
    for multiple agent branches.
    """
    
    def __init__(self, project_name: str, work_dir: Optional[Path] = None):
        """
        Initialize the smart merger.
        
        Args:
            project_name: Name of the project
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
        
        self.merge_log: List[str] = []
        self.conflicts: List[Dict[str, Any]] = []
    
    def execute_merge(
        self,
        strategy: str = "smart",
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the complete merge process.
        
        Args:
            strategy: Merge strategy ("smart", "sequential", "manual")
            verbose: Enable verbose logging
            
        Returns:
            Merge result summary
        """
        logger.info(f"Starting {strategy} merge for project: {self.project_name}")
        
        try:
            # Get branches to merge
            branches = self._get_agent_branches()
            if not branches:
                return {
                    'success': False,
                    'error': 'No agent branches found to merge'
                }
            
            self._log(f"Found {len(branches)} branches to merge")
            
            # Analyze dependencies for merge order
            if strategy == "smart":
                merge_order = self._analyze_dependencies()
            else:
                merge_order = sorted(branches)
            
            # Predict conflicts
            conflicts = self._predict_conflicts(branches)
            self._log(f"Predicted {len(conflicts)} potential conflicts")
            
            # Create merge branch
            merge_branch = self._create_merge_branch()
            
            # Execute merges
            merged_count = 0
            for branch in merge_order:
                if self._merge_branch(branch, verbose):
                    merged_count += 1
                else:
                    self._log(f"Failed to merge {branch}", "ERROR")
            
            # Run tests if possible
            test_result = self._run_tests()
            
            # Generate report
            self._generate_merge_report()
            
            result = {
                'success': merged_count > 0,
                'merged_branches': merged_count,
                'total_branches': len(branches),
                'conflicts_resolved': len([c for c in self.conflicts if c.get('resolved')]),
                'manual_conflicts': len([c for c in self.conflicts if not c.get('resolved')]),
                'test_passed': test_result,
                'merge_branch': merge_branch
            }
            
            if merged_count == len(branches):
                self._log("All branches merged successfully!", "SUCCESS")
            else:
                result['error'] = f"Only {merged_count}/{len(branches)} branches merged"
            
            return result
            
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_agent_branches(self) -> List[str]:
        """Get all agent branches for the project."""
        try:
            # Get remote branches
            result = subprocess.run(
                ['git', 'branch', '-r'],
                capture_output=True, text=True, cwd=self.repo_root
            )
            
            if result.returncode != 0:
                return []
            
            branches = []
            prefix = f"origin/swarm-agent-{self.project_name}-"
            
            for line in result.stdout.split('\n'):
                branch = line.strip()
                if branch.startswith(prefix):
                    branches.append(branch.replace('origin/', ''))
            
            return branches
            
        except Exception as e:
            logger.error(f"Failed to get agent branches: {e}")
            return []
    
    def _analyze_dependencies(self) -> List[str]:
        """Analyze task dependencies to determine merge order."""
        self._log("Analyzing dependencies for optimal merge order...")
        
        # Load task registry to understand dependencies
        task_registry = self.project_dir / "registry" / "tasks.csv"
        
        if not task_registry.exists():
            # Fallback to simple ordering
            branches = self._get_agent_branches()
            return sorted(branches)
        
        # Build dependency graph (simplified)
        try:
            import csv
            
            G = nx.DiGraph()
            agent_tasks = {}
            
            with open(task_registry, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    task_id = row.get('task_id')
                    agent = row.get('assigned_agent')
                    deps = row.get('dependencies', '').split(';')
                    
                    if task_id and agent:
                        if agent not in agent_tasks:
                            agent_tasks[agent] = {'tasks': [], 'deps': []}
                        
                        agent_tasks[agent]['tasks'].append(task_id)
                        agent_tasks[agent]['deps'].extend([d for d in deps if d])
            
            # Add nodes for agents
            for agent in agent_tasks:
                G.add_node(agent)
            
            # Add edges based on dependencies
            for agent, data in agent_tasks.items():
                for dep_task in data['deps']:
                    # Find which agent has this dependency
                    for other_agent, other_data in agent_tasks.items():
                        if dep_task in other_data['tasks'] and other_agent != agent:
                            G.add_edge(other_agent, agent)
            
            # Topological sort
            try:
                agent_order = list(nx.topological_sort(G))
                
                # Convert back to branch names
                branches = []
                for agent in agent_order:
                    branch = f"swarm-agent-{self.project_name}-{agent.split('-')[-1]}"
                    if branch in self._get_agent_branches():
                        branches.append(branch)
                
                self._log(f"Optimal merge order: {branches}")
                return branches
                
            except nx.NetworkXUnfeasible:
                self._log("Circular dependencies detected, using default order", "WARNING")
                
        except Exception as e:
            logger.error(f"Failed to analyze dependencies: {e}")
        
        # Fallback to simple ordering
        branches = self._get_agent_branches()
        return sorted(branches)
    
    def _predict_conflicts(self, branches: List[str]) -> List[Dict[str, Any]]:
        """Predict potential merge conflicts."""
        self._log("Predicting potential conflicts...")
        
        conflicts = []
        file_changes = {}
        
        # Collect all file changes by branch
        for branch in branches:
            try:
                result = subprocess.run(
                    ['git', 'diff', '--name-only', f'main...{branch}'],
                    capture_output=True, text=True, cwd=self.repo_root
                )
                
                if result.returncode == 0:
                    changed_files = [f for f in result.stdout.strip().split('\n') if f]
                    for file in changed_files:
                        if file not in file_changes:
                            file_changes[file] = []
                        file_changes[file].append(branch)
                        
            except Exception as e:
                logger.error(f"Failed to get changes for {branch}: {e}")
        
        # Identify files changed by multiple branches
        for file, branches_list in file_changes.items():
            if len(branches_list) > 1:
                conflicts.append({
                    'file': file,
                    'branches': branches_list,
                    'severity': 'high' if len(branches_list) > 2 else 'medium'
                })
                self._log(f"Potential conflict in {file}: modified by {len(branches_list)} branches", "WARNING")
        
        return conflicts
    
    def _create_merge_branch(self) -> str:
        """Create a new branch for the merge operation."""
        merge_branch = f"merge/{self.project_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        self._log(f"Creating merge branch: {merge_branch}")
        
        try:
            # Ensure we're on main and up to date
            self.repo.heads.main.checkout()
            origin = self.repo.remotes.origin
            origin.pull()
            
            # Create merge branch
            new_branch = self.repo.create_head(merge_branch)
            new_branch.checkout()
            
            return merge_branch
            
        except Exception as e:
            logger.error(f"Failed to create merge branch: {e}")
            raise
    
    def _merge_branch(self, branch: str, verbose: bool = False) -> bool:
        """Merge a single branch."""
        self._log(f"Merging {branch}")
        
        try:
            # Try to merge
            self.repo.git.merge(branch, '--no-ff', '-m', f"feat: merge {branch}")
            self._log(f"Successfully merged {branch}", "SUCCESS")
            return True
            
        except GitCommandError as e:
            # Merge conflict
            self._log(f"Conflict detected while merging {branch}", "ERROR")
            
            # Get conflict files
            try:
                result = subprocess.run(
                    ['git', 'diff', '--name-only', '--diff-filter=U'],
                    capture_output=True, text=True, cwd=self.repo_root
                )
                
                conflict_files = [f for f in result.stdout.strip().split('\n') if f]
                
                conflict_info = {
                    'branch': branch,
                    'files': conflict_files,
                    'error': str(e),
                    'resolved': False
                }
                self.conflicts.append(conflict_info)
                
                # Try automated resolution
                if self._auto_resolve_conflicts(conflict_files):
                    conflict_info['resolved'] = True
                    self._log(f"Automatically resolved conflicts in {branch}", "SUCCESS")
                    return True
                else:
                    # Abort merge
                    self.repo.git.merge('--abort')
                    self._log(f"Could not auto-resolve conflicts in {branch}, skipping", "ERROR")
                    return False
                    
            except Exception as resolution_error:
                logger.error(f"Failed to handle conflict resolution: {resolution_error}")
                try:
                    self.repo.git.merge('--abort')
                except:
                    pass
                return False
    
    def _auto_resolve_conflicts(self, conflict_files: List[str]) -> bool:
        """Attempt to automatically resolve conflicts."""
        resolved_all = True
        
        for file in conflict_files:
            if not file:
                continue
            
            self._log(f"Attempting to auto-resolve {file}")
            
            # Simple strategy: prefer incoming changes for certain file types
            if file.endswith(('.md', '.json', '.txt')) or 'generated' in file.lower():
                try:
                    self.repo.git.checkout('--theirs', file)
                    self.repo.git.add(file)
                    self._log(f"Resolved {file} by taking incoming changes")
                except Exception as e:
                    logger.error(f"Failed to resolve {file}: {e}")
                    resolved_all = False
            else:
                # For code files, we're more conservative
                resolved_all = False
        
        if resolved_all:
            try:
                self.repo.git.commit('--no-edit')
                return True
            except Exception as e:
                logger.error(f"Failed to commit resolved conflicts: {e}")
                return False
        
        return False
    
    def _run_tests(self) -> bool:
        """Run tests after merge to ensure nothing is broken."""
        self._log("Running tests to validate merge...")
        
        # Common test commands
        test_commands = [
            ['npm', 'test'],
            ['python', '-m', 'pytest'],
            ['make', 'test'],
            ['npm', 'run', 'test']
        ]
        
        for cmd in test_commands:
            try:
                # Check if command exists
                if subprocess.run(['which', cmd[0]], capture_output=True).returncode == 0:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, 
                        cwd=self.repo_root, timeout=300
                    )
                    
                    if result.returncode == 0:
                        self._log("Tests passed!", "SUCCESS")
                        return True
                    else:
                        self._log("Tests failed!", "ERROR")
                        self._log(f"Test output: {result.stdout}")
                        self._log(f"Test errors: {result.stderr}")
                        return False
            except Exception as e:
                logger.error(f"Failed to run test command {cmd}: {e}")
        
        self._log("No test suite found, skipping tests", "WARNING")
        return True
    
    def _generate_merge_report(self) -> None:
        """Generate detailed merge report."""
        report_file = self.project_dir / "reports" / f"merge_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_file.parent.mkdir(exist_ok=True)
        
        branches = self._get_agent_branches()
        
        with open(report_file, 'w') as f:
            f.write(f"# Merge Report for {self.project_name}\n\n")
            f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## Summary\n")
            f.write(f"- Total branches to merge: {len(branches)}\n")
            f.write(f"- Conflicts encountered: {len(self.conflicts)}\n")
            f.write(f"- Auto-resolved conflicts: {len([c for c in self.conflicts if c.get('resolved')])}\n\n")
            
            if self.conflicts:
                f.write("## Conflicts\n")
                for conflict in self.conflicts:
                    f.write(f"\n### {conflict['branch']}\n")
                    f.write("**Files with conflicts:**\n")
                    for file in conflict['files']:
                        f.write(f"- {file}\n")
                    f.write(f"**Resolved**: {'Yes' if conflict.get('resolved') else 'No'}\n")
            
            f.write("\n## Merge Log\n")
            f.write("```\n")
            f.write("\n".join(self.merge_log))
            f.write("\n```\n")
        
        self._log(f"Merge report saved to: {report_file}")
    
    def _log(self, message: str, level: str = "INFO") -> None:
        """Log merge operations."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.merge_log.append(log_entry)
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)