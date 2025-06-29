# Claude Swarm Coordinator

A generalized framework for orchestrating multiple Claude Code agents to work in parallel on complex software projects.

[![PyPI version](https://badge.fury.io/py/claude-swarm-coordinator.svg)](https://badge.fury.io/py/claude-swarm-coordinator)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

Claude Swarm Coordinator enables you to break down large software projects into tasks and coordinate multiple Claude Code agents working in parallel. Each agent operates in its own git worktree, ensuring complete isolation while maintaining coordination through structured communication protocols.

## Key Features

- **🔀 Git Worktree Integration**: Complete agent isolation using git worktrees
- **📋 Intelligent Task Planning**: Automatic project breakdown with dependency analysis
- **🤝 Agent Coordination**: File-based communication protocols for real-time coordination
- **🔄 Smart Merging**: Dependency-aware merge strategies with conflict resolution
- **📊 Real-time Monitoring**: Progress tracking and performance dashboards
- **🛠️ Error Recovery**: Comprehensive blocker reporting and resolution workflows

## Installation

```bash
pip install claude-swarm-coordinator
```

For development:
```bash
pip install claude-swarm-coordinator[dev]
```

## Quick Start

### 1. Initialize a Swarm Project

```bash
# Create a new swarm project with 10 agents
claude-swarm init my-project --agents 10 --description "Build a REST API with authentication"

# Or interactively
claude-swarm init my-project
```

### 2. Plan Tasks

```bash
# Analyze requirements from a file
claude-swarm plan my-project --requirements requirements.md

# Or use interactive planning
claude-swarm plan my-project --interactive
```

### 3. Launch the Swarm

```bash
# Launch all agents in parallel
claude-swarm launch my-project --mode parallel

# Monitor progress
claude-swarm status my-project --watch
```

### 4. Merge Results

```bash
# Smart merge with dependency analysis
claude-swarm merge my-project --strategy smart

# View merge report
claude-swarm merge my-project --report
```

## Project Structure

When you initialize a swarm project, this structure is created:

```
.claude-swarm/
└── projects/
    └── my-project/
        ├── config/
        │   └── swarm.json
        ├── tasks/
        │   ├── task_plan.json
        │   └── individual_tasks/
        ├── registry/
        │   ├── agents.csv
        │   ├── tasks.csv
        │   └── progress.csv
        ├── coordination/
        │   ├── blockers/
        │   ├── shared/
        │   └── announcements/
        └── reports/
```

## Agent Workflow

Each agent follows a structured workflow:

1. **Initialization**: Agent receives tasks and sets up worktree
2. **Task Execution**: Implements assigned tasks with frequent commits
3. **Communication**: Reports progress and blockers through file protocols
4. **Coordination**: Shares reusable components and resolves dependencies
5. **Completion**: Final commits and status updates

## Programming Interface

### SwarmCoordinator

```python
from claude_swarm import SwarmCoordinator

# Initialize coordinator
coordinator = SwarmCoordinator("my-project")

# Set up project
coordinator.initialize_project(
    num_agents=10,
    description="Build a REST API"
)

# Launch swarm
coordinator.launch_swarm(mode="parallel")

# Get status
status = coordinator.get_status()
print(f"Active agents: {status['active_agents']}")
```

### TaskPlanner

```python
from claude_swarm import TaskPlanner

planner = TaskPlanner("my-project")

# Analyze requirements
task_plan = planner.analyze_requirements("requirements.md")

# Get summary
summary = planner.get_summary()
print(f"Total tasks: {summary['total_tasks']}")
print(f"Estimated time: {summary['total_time']} minutes")
```

## Requirements Format

### Markdown Format

```markdown
# Project Requirements

## User Authentication
- User registration with email validation
- JWT-based login system
- Password reset functionality

## API Endpoints
- RESTful user management
- Data validation and error handling

## Database
- User model with proper relationships
- Migration scripts
```

### JSON Format

```json
[
  {
    "description": "Create user authentication system",
    "category": "backend",
    "complexity": "high",
    "dependencies": []
  },
  {
    "description": "Build REST API endpoints", 
    "category": "api",
    "complexity": "medium",
    "dependencies": ["user-auth"]
  }
]
```

## Configuration

### Project Configuration

```json
{
  "project_name": "my-project",
  "num_agents": 10,
  "description": "Project description",
  "branch_prefix": "swarm-agent",
  "status": "active",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Agent Configuration

Each agent receives detailed instructions including:
- Task assignments with complexity estimates
- Communication protocols
- Commit and push schedules
- Blocker reporting procedures
- Quality standards

## Advanced Features

### Smart Merge Strategies

The merger analyzes task dependencies to determine optimal merge order:

```python
from claude_swarm.merge import SmartMerger

merger = SmartMerger("my-project")
result = merger.execute_merge(strategy="smart")

if result['success']:
    print(f"Merged {result['merged_branches']} branches")
else:
    print(f"Merge failed: {result['error']}")
```

### Real-time Monitoring

```python
from claude_swarm.evaluation import ProgressDashboard

dashboard = ProgressDashboard("my-project")
dashboard.start_monitoring()  # Real-time progress display
```

### Conflict Resolution

Automatic conflict resolution for:
- Documentation files (`.md`, `.txt`)
- Configuration files (`.json`, `.yaml`)
- Generated files
- Custom resolution rules

## Best Practices

### Project Setup
- Start with clear, detailed requirements
- Use descriptive task names
- Set realistic complexity estimates
- Plan for dependencies

### Agent Management
- Monitor agent progress regularly
- Address blockers quickly
- Ensure frequent commits
- Review merge conflicts

### Quality Assurance
- Run tests after merges
- Code review parallel branches
- Maintain coding standards
- Document shared components

## Troubleshooting

### Common Issues

**Agents not committing frequently enough:**
```bash
# Check agent activity
claude-swarm status my-project --detailed

# Review progress logs
cat .claude-swarm/projects/my-project/coordination/*/progress.log
```

**Merge conflicts:**
```bash
# Use manual merge strategy
claude-swarm merge my-project --strategy manual

# Review conflict report
claude-swarm merge my-project --report
```

**Blocked agents:**
```bash
# Check for blockers
ls .claude-swarm/projects/my-project/coordination/blockers/

# Review blocker details
cat .claude-swarm/projects/my-project/coordination/blockers/BLOCKER-*.md
```

## Development

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Submit a pull request

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=claude_swarm

# Run specific test file
pytest tests/test_coordinator.py
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code  
ruff check src/ tests/

# Type checking
mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- [Documentation](https://claude-swarm-coordinator.readthedocs.io)
- [Issues](https://github.com/anthropics/claude-swarm-coordinator/issues)
- [Discussions](https://github.com/anthropics/claude-swarm-coordinator/discussions)

## Citation

If you use Claude Swarm Coordinator in your research or projects, please cite:

```bibtex
@software{claude_swarm_coordinator,
  title = {Claude Swarm Coordinator: A Framework for Multi-Agent Parallel Development},
  author = {Claude Code Swarm Project},
  year = {2024},
  url = {https://github.com/anthropics/claude-swarm-coordinator}
}
```