"""Tests for the task planner."""

import json
import tempfile
from pathlib import Path

import pytest

from claude_swarm.core.planner import TaskPlanner, Task


class TestTaskPlanner:
    """Test cases for TaskPlanner."""
    
    def test_init(self):
        """Test TaskPlanner initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            planner = TaskPlanner("test-project", Path(temp_dir))
            assert planner.project_name == "test-project"
            assert planner.tasks == []
            assert planner.task_id_counter == 1
    
    def test_parse_markdown_requirements(self):
        """Test parsing markdown requirements."""
        with tempfile.TemporaryDirectory() as temp_dir:
            planner = TaskPlanner("test-project", Path(temp_dir))
            
            markdown_content = """
# Project Requirements

## User Management
- User registration with email validation
- User login with JWT authentication
- Password reset functionality

## API Documentation  
- OpenAPI/Swagger documentation
- API versioning

TODO: Add rate limiting
"""
            
            planner._parse_markdown_requirements(markdown_content)
            
            # Should have created tasks
            assert len(planner.tasks) == 5  # 3 user management + 2 api docs + 1 TODO
            
            # Check task categories
            categories = [task.category for task in planner.tasks]
            assert "user_management" in categories
            assert "api_documentation" in categories
            
            # Check TODO task has high priority
            todo_tasks = [task for task in planner.tasks if task.priority == "high"]
            assert len(todo_tasks) == 1
    
    def test_parse_json_requirements(self):
        """Test parsing JSON requirements."""
        with tempfile.TemporaryDirectory() as temp_dir:
            planner = TaskPlanner("test-project", Path(temp_dir))
            
            json_content = json.dumps([
                {
                    "description": "Create user model",
                    "category": "backend",
                    "complexity": "medium"
                },
                {
                    "description": "Add authentication endpoints",
                    "category": "api",
                    "complexity": "high"
                }
            ])
            
            planner._parse_json_requirements(json_content)
            
            assert len(planner.tasks) == 2
            assert planner.tasks[0].description == "Create user model"
            assert planner.tasks[0].category == "backend"
            assert planner.tasks[0].complexity == "medium"
    
    def test_estimate_complexity(self):
        """Test complexity estimation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            planner = TaskPlanner("test-project", Path(temp_dir))
            
            # High complexity
            assert planner._estimate_complexity("Refactor the entire authentication system") == "high"
            assert planner._estimate_complexity("Design distributed architecture") == "high"
            
            # Low complexity
            assert planner._estimate_complexity("Fix typo in README") == "low"
            assert planner._estimate_complexity("Update documentation") == "low"
            
            # Medium complexity (default)
            assert planner._estimate_complexity("Implement user profile page") == "medium"
    
    def test_estimate_time(self):
        """Test time estimation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            planner = TaskPlanner("test-project", Path(temp_dir))
            
            assert planner._estimate_time("low") == 30
            assert planner._estimate_time("medium") == 90
            assert planner._estimate_time("high") == 180
    
    def test_extract_required_skills(self):
        """Test skill extraction."""
        with tempfile.TemporaryDirectory() as temp_dir:
            planner = TaskPlanner("test-project", Path(temp_dir))
            
            # API-related task
            skills = planner._extract_required_skills("Create REST API endpoints for user management")
            assert "api" in skills
            assert "backend" in skills
            
            # Frontend task
            skills = planner._extract_required_skills("Design React components for UI")
            assert "frontend" in skills
            
            # Database task
            skills = planner._extract_required_skills("Create database schema and migrations")
            assert "database" in skills
    
    def test_task_model_validation(self):
        """Test Task model validation."""
        # Valid task
        task = Task(
            task_id="TASK-0001",
            description="Test task",
            complexity="medium",
            priority="normal"
        )
        assert task.task_id == "TASK-0001"
        assert task.complexity == "medium"
        
        # Invalid complexity should raise validation error
        with pytest.raises(ValueError):
            Task(
                task_id="TASK-0002",
                description="Test task",
                complexity="invalid",
                priority="normal"
            )
    
    def test_analyze_requirements_integration(self):
        """Test the complete analyze_requirements workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temporary requirements file
            req_file = Path(temp_dir) / "requirements.md"
            req_file.write_text("""
# E-Commerce API

## User Management
- User registration
- User login

## Product Catalog
- CRUD operations for products
- Product search
""")
            
            planner = TaskPlanner("test-project", Path(temp_dir))
            task_plan = planner.analyze_requirements(req_file)
            
            # Check task plan
            assert task_plan.project_name == "test-project"
            assert task_plan.total_tasks > 0
            assert len(task_plan.tasks) == task_plan.total_tasks
            
            # Check summary
            summary = planner.get_summary()
            assert "total_tasks" in summary
            assert "total_time" in summary
            assert "complexity_breakdown" in summary