"""Allow `python -m usage_audit`."""

import sys

from usage_audit.cli import main

if __name__ == "__main__":
    sys.exit(main())
