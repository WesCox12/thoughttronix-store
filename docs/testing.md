# Testing

- pytest + pytest-django; settings come from `config.settings` via
  `pyproject.toml`. Test files are named `tests.py` or `test_*.py` inside
  each app.
- Shared fixtures live in the project-level `conftest.py` — plain fixtures,
  no factory-boy. Add new shared data there rather than duplicating it.
- The seed command is destructive: never use it for ordinary test setup.
  Only tests of the seed command's own behavior (in `products/tests.py`) may
  invoke it.
- The suite must be green at every phase boundary.
