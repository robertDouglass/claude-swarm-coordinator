"""
Communication Protocols for Claude Swarm

Manages inter-agent communication through file-based protocols.
"""

import json
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from pydantic import BaseModel, Field

from ..utils.helpers import setup_logging

logger = setup_logging(__name__)


class Blocker(BaseModel):
    """Blocker notification model."""
    
    id: str
    agent_id: str
    task_id: str
    title: str
    description: str
    impact: str
    status: str = "open"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None


class SharedResource(BaseModel):
    """Shared resource model."""
    
    id: str
    name: str
    created_by: str
    file_path: str
    description: str
    usage_example: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    used_by: List[str] = Field(default_factory=list)


class Message(BaseModel):
    """Inter-agent message model."""
    
    id: str
    from_agent: str
    to_agent: str
    subject: str
    body: str
    priority: str = "normal"
    status: str = "unread"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None


class CommunicationCoordinator:
    """
    Manages inter-agent communication through file-based protocols.
    
    Provides structured communication channels for blockers, resource sharing,
    messages, and progress reporting between agents.
    """
    
    def __init__(self, project_name: str, repo_root: Path):
        """
        Initialize the communication coordinator.
        
        Args:
            project_name: Name of the project
            repo_root: Root path of the git repository
        """
        self.project_name = project_name
        self.repo_root = Path(repo_root)
        self.coord_dir = self.repo_root / ".swarm-coordination" / project_name
        
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure all coordination directories exist."""
        dirs = ['blockers', 'shared', 'dependencies', 'reports', 'messages']
        for dir_name in dirs:
            (self.coord_dir / dir_name).mkdir(parents=True, exist_ok=True)
    
    def post_blocker(
        self,
        agent_id: str,
        task_id: str,
        title: str,
        description: str,
        impact: str
    ) -> str:
        """
        Post a blocker notification.
        
        Args:
            agent_id: ID of the agent reporting the blocker
            task_id: ID of the blocked task
            title: Brief title of the blocker
            description: Detailed description
            impact: Description of the impact
            
        Returns:
            Blocker ID
        """
        timestamp = int(time.time())
        blocker_id = f"BLOCKER-{agent_id}-{timestamp}"
        
        blocker = Blocker(
            id=blocker_id,
            agent_id=agent_id,
            task_id=task_id,
            title=title,
            description=description,
            impact=impact
        )
        
        # Write blocker file
        blocker_file = self.coord_dir / 'blockers' / f"{blocker_id}.json"
        with open(blocker_file, 'w') as f:
            json.dump(blocker.model_dump(), f, indent=2, default=str)
        
        # Also create markdown for easy reading
        md_file = self.coord_dir / 'blockers' / f"{blocker_id}.md"
        with open(md_file, 'w') as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Agent**: {agent_id}\n")
            f.write(f"**Task**: {task_id}\n")
            f.write(f"**Created**: {blocker.created_at}\n\n")
            f.write(f"## Description\n{description}\n\n")
            f.write(f"## Impact\n{impact}\n")
        
        logger.info(f"Posted blocker {blocker_id} from {agent_id}")
        return blocker_id
    
    def resolve_blocker(self, blocker_id: str, resolution: str) -> bool:
        """
        Mark a blocker as resolved.
        
        Args:
            blocker_id: ID of the blocker to resolve
            resolution: Description of the resolution
            
        Returns:
            True if successful, False otherwise
        """
        blocker_file = self.coord_dir / 'blockers' / f"{blocker_id}.json"
        
        if not blocker_file.exists():
            logger.error(f"Blocker {blocker_id} not found")
            return False
        
        try:
            with open(blocker_file, 'r') as f:
                blocker_data = json.load(f)
            
            blocker = Blocker(**blocker_data)
            blocker.status = 'resolved'
            blocker.resolved_at = datetime.utcnow()
            blocker.resolution = resolution
            
            with open(blocker_file, 'w') as f:
                json.dump(blocker.model_dump(), f, indent=2, default=str)
            
            logger.info(f"Resolved blocker {blocker_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resolve blocker {blocker_id}: {e}")
            return False
    
    def share_resource(
        self,
        agent_id: str,
        resource_name: str,
        file_path: str,
        description: str,
        usage_example: str
    ) -> str:
        """
        Share a resource with other agents.
        
        Args:
            agent_id: ID of the agent sharing the resource
            resource_name: Name of the resource
            file_path: Path to the resource file
            description: Description of the resource
            usage_example: Example of how to use the resource
            
        Returns:
            Resource ID
        """
        resource_id = hashlib.md5(f"{resource_name}{agent_id}".encode()).hexdigest()[:8]
        
        resource = SharedResource(
            id=resource_id,
            name=resource_name,
            created_by=agent_id,
            file_path=file_path,
            description=description,
            usage_example=usage_example
        )
        
        # Write resource file
        resource_file = self.coord_dir / 'shared' / f"SHARED-{resource_name}.json"
        with open(resource_file, 'w') as f:
            json.dump(resource.model_dump(), f, indent=2, default=str)
        
        # Create markdown documentation
        md_file = self.coord_dir / 'shared' / f"SHARED-{resource_name}.md"
        with open(md_file, 'w') as f:
            f.write(f"# SHARED RESOURCE: {resource_name}\n\n")
            f.write(f"**Created By**: {agent_id}\n")
            f.write(f"**Location**: `{file_path}`\n")
            f.write(f"**Created**: {resource.created_at}\n\n")
            f.write(f"## Description\n{description}\n\n")
            f.write(f"## Usage Example\n```\n{usage_example}\n```\n")
        
        logger.info(f"Shared resource {resource_name} from {agent_id}")
        return resource_id
    
    def send_message(
        self,
        from_agent: str,
        to_agent: str,
        subject: str,
        body: str,
        priority: str = 'normal'
    ) -> str:
        """
        Send a message between agents.
        
        Args:
            from_agent: Sender agent ID
            to_agent: Recipient agent ID
            subject: Message subject
            body: Message body
            priority: Message priority ('low', 'normal', 'high')
            
        Returns:
            Message ID
        """
        msg_id = f"MSG-{int(time.time())}-{from_agent}-{to_agent}"
        
        message = Message(
            id=msg_id,
            from_agent=from_agent,
            to_agent=to_agent,
            subject=subject,
            body=body,
            priority=priority
        )
        
        msg_file = self.coord_dir / 'messages' / f"{msg_id}.json"
        with open(msg_file, 'w') as f:
            json.dump(message.model_dump(), f, indent=2, default=str)
        
        logger.info(f"Sent message from {from_agent} to {to_agent}")
        return msg_id
    
    def get_messages(self, agent_id: str, status: str = 'unread') -> List[Message]:
        """
        Get messages for an agent.
        
        Args:
            agent_id: Agent ID to get messages for
            status: Message status to filter by
            
        Returns:
            List of messages
        """
        messages = []
        messages_dir = self.coord_dir / 'messages'
        
        if not messages_dir.exists():
            return messages
        
        for msg_file in messages_dir.glob("MSG-*.json"):
            try:
                with open(msg_file, 'r') as f:
                    msg_data = json.load(f)
                
                message = Message(**msg_data)
                if message.to_agent == agent_id and message.status == status:
                    messages.append(message)
                    
            except Exception as e:
                logger.error(f"Failed to read message {msg_file}: {e}")
        
        return sorted(messages, key=lambda m: m.created_at)
    
    def mark_message_read(self, msg_id: str) -> bool:
        """
        Mark a message as read.
        
        Args:
            msg_id: Message ID to mark as read
            
        Returns:
            True if successful, False otherwise
        """
        msg_file = self.coord_dir / 'messages' / f"{msg_id}.json"
        
        if not msg_file.exists():
            return False
        
        try:
            with open(msg_file, 'r') as f:
                msg_data = json.load(f)
            
            message = Message(**msg_data)
            message.status = 'read'
            message.read_at = datetime.utcnow()
            
            with open(msg_file, 'w') as f:
                json.dump(message.model_dump(), f, indent=2, default=str)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark message {msg_id} as read: {e}")
            return False
    
    def get_blockers(self, status: str = 'open') -> List[Blocker]:
        """
        Get blockers by status.
        
        Args:
            status: Blocker status to filter by
            
        Returns:
            List of blockers
        """
        blockers = []
        blockers_dir = self.coord_dir / 'blockers'
        
        if not blockers_dir.exists():
            return blockers
        
        for blocker_file in blockers_dir.glob("BLOCKER-*.json"):
            try:
                with open(blocker_file, 'r') as f:
                    blocker_data = json.load(f)
                
                blocker = Blocker(**blocker_data)
                if blocker.status == status:
                    blockers.append(blocker)
                    
            except Exception as e:
                logger.error(f"Failed to read blocker {blocker_file}: {e}")
        
        return sorted(blockers, key=lambda b: b.created_at)
    
    def get_shared_resources(self) -> List[SharedResource]:
        """
        Get all shared resources.
        
        Returns:
            List of shared resources
        """
        resources = []
        shared_dir = self.coord_dir / 'shared'
        
        if not shared_dir.exists():
            return resources
        
        for resource_file in shared_dir.glob("SHARED-*.json"):
            try:
                with open(resource_file, 'r') as f:
                    resource_data = json.load(f)
                
                resource = SharedResource(**resource_data)
                resources.append(resource)
                
            except Exception as e:
                logger.error(f"Failed to read resource {resource_file}: {e}")
        
        return sorted(resources, key=lambda r: r.created_at)
    
    def get_coordination_summary(self) -> Dict[str, Any]:
        """
        Get summary of all coordination activities.
        
        Returns:
            Summary dictionary
        """
        blockers = self.get_blockers('open')
        resources = self.get_shared_resources()
        
        summary = {
            'blockers': {
                'open': len(blockers),
                'resolved': len(self.get_blockers('resolved')),
                'list': [{'id': b.id, 'agent': b.agent_id, 'title': b.title} for b in blockers]
            },
            'shared_resources': [
                {'name': r.name, 'created_by': r.created_by, 'file_path': r.file_path}
                for r in resources
            ],
            'recent_messages': len(self.get_messages('all', 'unread'))
        }
        
        return summary


class AgentCommunicator:
    """
    Communication interface for individual agents.
    
    Provides simplified interface for agents to communicate with
    the coordination system.
    """
    
    def __init__(self, agent_id: str, project_name: str, repo_root: Path):
        """
        Initialize the agent communicator.
        
        Args:
            agent_id: ID of this agent
            project_name: Name of the project
            repo_root: Root path of the git repository
        """
        self.agent_id = agent_id
        self.coordinator = CommunicationCoordinator(project_name, repo_root)
    
    def report_blocker(
        self,
        task_id: str,
        title: str,
        description: str,
        impact: str = "1 task blocked"
    ) -> str:
        """
        Report a blocking issue.
        
        Args:
            task_id: ID of the blocked task
            title: Brief title of the blocker
            description: Detailed description
            impact: Description of the impact
            
        Returns:
            Blocker ID
        """
        return self.coordinator.post_blocker(
            self.agent_id, task_id, title, description, impact
        )
    
    def share_utility(
        self,
        name: str,
        file_path: str,
        description: str,
        example: str
    ) -> str:
        """
        Share a utility or helper function.
        
        Args:
            name: Name of the utility
            file_path: Path to the utility file
            description: Description of what it does
            example: Usage example
            
        Returns:
            Resource ID
        """
        return self.coordinator.share_resource(
            self.agent_id, name, file_path, description, example
        )
    
    def check_messages(self) -> List[Message]:
        """
        Check for new messages.
        
        Returns:
            List of unread messages
        """
        return self.coordinator.get_messages(self.agent_id)
    
    def send_message(
        self,
        to_agent: str,
        subject: str,
        body: str,
        priority: str = 'normal'
    ) -> str:
        """
        Send message to another agent.
        
        Args:
            to_agent: Recipient agent ID
            subject: Message subject
            body: Message body
            priority: Message priority
            
        Returns:
            Message ID
        """
        return self.coordinator.send_message(
            self.agent_id, to_agent, subject, body, priority
        )