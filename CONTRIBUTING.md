# Contributing to Mixsmith

Thank you for your interest in improving Mixsmith!

---

## Development Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/Shreyas-SK-21/mixsmith.git
   cd mixsmith
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install pytest ruff
   ```

---

## Running Tests

All pull requests must pass the complete test suite:
```bash
python -m pytest tests -v
```

---

## Code Quality & Standards

- **Formatting & Linting**: Use standard Python conventions.
- **Type Hints**: All new public functions and classes must include type annotations.
- **Pure Algorithms**: Keep core sequencing, deduplication, and de-clumping logic platform-agnostic and decoupled from Spotify API calls.
- **Safe Modifications**: Any operation modifying external services must offer a `--dry-run` flag and confirmation mechanism.

---

## Commit Guidelines

Keep commit messages concise and descriptive (e.g. `added multi-artist declumper`, `fixed title normalization regex`, `updated documentation`).
