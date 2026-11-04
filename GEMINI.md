# Project: Booking

## Project Overview
This is a backend application for a hotel booking system.
The project was developed as a learning project.
The goal is to improve its architecture, code quality, reliability,
and maintainability.

## Technology Stack
- Python 3.13
- FastAPI
- PostgreSQL
- SQLAlchemy 2.0
- Alembic
- Pydantic v2
- Redis
- Celery
- Pytest
- Async programming

## Architecture
The project uses a layered architecture:

- api — API routes and dependencies
- services — business logic
- repositories — database operations
- models — SQLAlchemy models
- schemas — Pydantic schemas
- connectors — external service connections
- tasks — background tasks
- core — core application components
- utils — utility modules
- migrations — database migrations
- tests — unit and integration tests

## AI Working Rules

1. Before making changes, analyze the existing code.
2. Never assume that a file or function works in a particular way.
   Inspect the actual implementation first.
3. Do not modify files without my explicit approval.
4. Before implementing a task, provide:
   - Problem analysis
   - Proposed solution
   - Files that need modification
   - Possible risks
5. Wait for my approval before writing or modifying code.
6. Do not rewrite entire modules when a small change is sufficient.
7. Follow the existing project architecture.
8. Do not introduce new libraries without explaining why.
9. Never modify environment files or expose secrets.
10. After implementation, explain the changes and suggest tests.

## Communication

- Explain technical concepts clearly.
- Work step by step.
- Do not overwhelm me with unrelated information.
- Act as a senior Python backend developer and mentor.
- Explain not only what to do, but why.