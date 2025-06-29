"""Git utilities for managing worktrees and branches."""

import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any

import git
from git.exc import GitCommandError

from .helpers import setup_logging

logger = setup_logging(__name__)


class GitWorktreeManager:
    """
    Manager for git worktree operations.
    
    Provides high-level interface for creating, managing, and cleaning up
    git worktrees for agent isolation.
    """
    
    def __init__(self, repo_path: Path):
        """
        Initialize the worktree manager.
        
        Args:
            repo_path: Path to the git repository root
        """
        self.repo_path = Path(repo_path)
        
        try:
            self.repo = git.Repo(self.repo_path)
        except git.InvalidGitRepositoryError:
            raise ValueError(f"Not a valid git repository: {repo_path}")
    
    def create_worktree(
        self,
        path: Path,
        branch: str,
        base_branch: str = "main"
    ) -> bool:
        """
        Create a new git worktree.
        
        Args:
            path: Path for the new worktree
            branch: Name of the new branch
            base_branch: Base branch to branch from
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if branch exists on remote
            remote_branch = f"origin/{branch}"
            remote_exists = False
            
            try:
                self.repo.git.rev_parse(remote_branch)
                remote_exists = True
            except GitCommandError:
                pass
            
            if remote_exists:
                # Checkout existing remote branch
                logger.info(f"Checking out existing branch {branch}")
                self.repo.git.worktree('add', str(path), branch)
            else:
                # Create new branch
                logger.info(f"Creating new worktree at {path} with branch {branch}")
                self.repo.git.worktree('add', '-b', branch, str(path), base_branch)
            
            return True
            
        except GitCommandError as e:
            logger.error(f"Failed to create worktree {path}: {e}")
            return False
    
    def remove_worktree(self, path: Path, force: bool = False) -> bool:
        """
        Remove a git worktree.
        
        Args:
            path: Path to the worktree
            force: Force removal even if worktree has uncommitted changes
            
        Returns:
            True if successful, False otherwise
        """
        try:
            args = ['remove', str(path)]
            if force:
                args.append('--force')
            
            self.repo.git.worktree(*args)
            logger.info(f"Removed worktree: {path}")
            return True
            
        except GitCommandError as e:
            logger.error(f"Failed to remove worktree {path}: {e}")
            return False
    
    def list_worktrees(self) -> List[Dict[str, str]]:
        """
        List all worktrees.
        
        Returns:
            List of worktree information dictionaries
        """
        try:
            output = self.repo.git.worktree('list', '--porcelain')
            worktrees = []
            
            current_worktree = {}
            for line in output.split('\n'):
                if line.startswith('worktree '):
                    if current_worktree:
                        worktrees.append(current_worktree)
                    current_worktree = {'path': line[9:]}  # Remove 'worktree ' prefix
                elif line.startswith('HEAD '):
                    current_worktree['head'] = line[5:]
                elif line.startswith('branch '):
                    current_worktree['branch'] = line[7:]
                elif line == 'bare':
                    current_worktree['bare'] = True
            
            if current_worktree:
                worktrees.append(current_worktree)
            
            return worktrees
            
        except GitCommandError as e:
            logger.error(f"Failed to list worktrees: {e}")
            return []
    
    def prune_worktrees(self) -> bool:
        """
        Prune stale worktree information.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.repo.git.worktree('prune')
            logger.info("Pruned stale worktrees")
            return True
            
        except GitCommandError as e:
            logger.error(f"Failed to prune worktrees: {e}")
            return False
    
    def get_branch_changes(self, branch: str, base_branch: str = "main") -> List[str]:
        """
        Get list of files changed in a branch compared to base.
        
        Args:
            branch: Branch to check
            base_branch: Base branch to compare against
            
        Returns:
            List of changed file paths
        """
        try:
            output = self.repo.git.diff('--name-only', f'{base_branch}...{branch}')
            return output.split('\n') if output.strip() else []
            
        except GitCommandError as e:
            logger.error(f"Failed to get branch changes for {branch}: {e}")
            return []
    
    def get_commit_count(self, branch: str, base_branch: str = "main") -> int:
        """
        Get number of commits in branch ahead of base.
        
        Args:
            branch: Branch to check
            base_branch: Base branch to compare against
            
        Returns:
            Number of commits ahead
        """
        try:
            output = self.repo.git.rev_list('--count', f'{base_branch}..{branch}')
            return int(output.strip()) if output.strip() else 0
            
        except (GitCommandError, ValueError) as e:
            logger.error(f"Failed to get commit count for {branch}: {e}")
            return 0
    
    def get_last_commit_info(self, branch: str) -> Optional[Dict[str, str]]:
        """
        Get information about the last commit in a branch.
        
        Args:
            branch: Branch to check
            
        Returns:
            Dictionary with commit information or None if failed
        """
        try:
            commit_hash = self.repo.git.log('-1', '--format=%h', branch)
            commit_time = self.repo.git.log('-1', '--format=%ar', branch)
            commit_message = self.repo.git.log('-1', '--format=%s', branch)
            commit_author = self.repo.git.log('-1', '--format=%an', branch)
            
            return {
                'hash': commit_hash.strip(),
                'time': commit_time.strip(),
                'message': commit_message.strip(),
                'author': commit_author.strip()
            }
            
        except GitCommandError as e:
            logger.error(f"Failed to get commit info for {branch}: {e}")
            return None
    
    def branch_exists(self, branch: str, remote: bool = False) -> bool:
        """
        Check if a branch exists.
        
        Args:
            branch: Branch name to check
            remote: Check remote branch instead of local
            
        Returns:
            True if branch exists, False otherwise
        """
        try:
            ref = f"refs/remotes/origin/{branch}" if remote else f"refs/heads/{branch}"
            self.repo.git.show_ref('--verify', '--quiet', ref)
            return True
            
        except GitCommandError:
            return False
    
    def create_archive_tag(self, tag_name: str, branch: str) -> bool:
        """
        Create an archive tag for a branch.
        
        Args:
            tag_name: Name of the tag to create
            branch: Branch to tag
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.repo.create_tag(tag_name, branch)
            logger.info(f"Created archive tag {tag_name} for branch {branch}")
            return True
            
        except GitCommandError as e:
            logger.error(f"Failed to create tag {tag_name}: {e}")
            return False
    
    def push_tags(self, remote: str = "origin") -> bool:
        """
        Push all tags to remote.
        
        Args:
            remote: Remote name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.repo.git.push(remote, '--tags')
            logger.info(f"Pushed tags to {remote}")
            return True
            
        except GitCommandError as e:
            logger.error(f"Failed to push tags to {remote}: {e}")
            return False
    
    def delete_branch(self, branch: str, force: bool = False) -> bool:
        """
        Delete a local branch.
        
        Args:
            branch: Branch name to delete
            force: Force deletion even if not fully merged
            
        Returns:
            True if successful, False otherwise
        """
        try:
            flag = '-D' if force else '-d'
            self.repo.git.branch(flag, branch)
            logger.info(f"Deleted branch {branch}")
            return True
            
        except GitCommandError as e:
            logger.error(f"Failed to delete branch {branch}: {e}")
            return False