"""Mark engine library shared by all hooks and CLI tools.

Constraints for everything under this package:
- Python 3.11+ standard library only (hooks must run with zero setup).
- Never write state under the plugin root (CLAUDE_PLUGIN_ROOT changes on every
  update). Project state lives in the project's `.mark/` directory.
"""

__version__ = "0.1.0"
