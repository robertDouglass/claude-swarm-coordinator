"""
Claude Swarm Coordinator

A generalized framework for orchestrating multiple Claude Code agents
to work in parallel on complex software projects.
"""

__version__ = "1.0.0"
__author__ = "Claude Code Swarm Project"
__email__ = "noreply@anthropic.com"

from .core.coordinator import SwarmCoordinator
from .core.planner import TaskPlanner
from .core.distributor import TaskDistributor

__all__ = [
    "SwarmCoordinator",
    "TaskPlanner", 
    "TaskDistributor",
]