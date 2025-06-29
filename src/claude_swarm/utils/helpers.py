"""Helper utilities for Claude Swarm Coordinator."""

import logging
import uuid
import hashlib
from typing import Optional
from pathlib import Path


def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Set up logging for a module.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    
    return logger


def generate_id(prefix: str = "", length: int = 8) -> str:
    """
    Generate a unique ID.
    
    Args:
        prefix: Optional prefix for the ID
        length: Length of the random part
        
    Returns:
        Unique ID string
    """
    random_part = str(uuid.uuid4()).replace('-', '')[:length]
    return f"{prefix}{random_part}" if prefix else random_part


def hash_content(content: str) -> str:
    """
    Generate MD5 hash of content.
    
    Args:
        content: Content to hash
        
    Returns:
        MD5 hash string
    """
    return hashlib.md5(content.encode()).hexdigest()


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists, creating if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        The path (for chaining)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_file_safe(path: Path, default: str = "") -> str:
    """
    Safely read a file, returning default if file doesn't exist.
    
    Args:
        path: File path
        default: Default content if file doesn't exist
        
    Returns:
        File content or default
    """
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return default


def write_file_safe(path: Path, content: str) -> bool:
    """
    Safely write content to file, creating directories if needed.
    
    Args:
        path: File path
        content: Content to write
        
    Returns:
        True if successful, False otherwise
    """
    try:
        ensure_directory(path.parent)
        path.write_text(content, encoding='utf-8')
        return True
    except Exception as e:
        logger = setup_logging(__name__)
        logger.error(f"Failed to write file {path}: {e}")
        return False


def format_duration(minutes: int) -> str:
    """
    Format duration in minutes to human-readable string.
    
    Args:
        minutes: Duration in minutes
        
    Returns:
        Formatted duration string
    """
    if minutes < 60:
        return f"{minutes} minutes"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes == 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    
    return f"{hours} hour{'s' if hours != 1 else ''} {remaining_minutes} minutes"


def parse_git_url(url: str) -> Optional[dict]:
    """
    Parse a git URL into components.
    
    Args:
        url: Git URL (HTTPS or SSH)
        
    Returns:
        Dictionary with URL components or None if invalid
    """
    import re
    
    # HTTPS URL pattern
    https_pattern = r'https://([^/]+)/([^/]+)/([^/.]+)(?:\.git)?'
    https_match = re.match(https_pattern, url)
    
    if https_match:
        return {
            'protocol': 'https',
            'host': https_match.group(1),
            'owner': https_match.group(2),
            'repo': https_match.group(3)
        }
    
    # SSH URL pattern
    ssh_pattern = r'git@([^:]+):([^/]+)/([^/.]+)(?:\.git)?'
    ssh_match = re.match(ssh_pattern, url)
    
    if ssh_match:
        return {
            'protocol': 'ssh',
            'host': ssh_match.group(1),
            'owner': ssh_match.group(2),
            'repo': ssh_match.group(3)
        }
    
    return None