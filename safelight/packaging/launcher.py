"""Entry point for the packaged app (PyInstaller)."""
import sys

from safelight.app import main

if __name__ == '__main__':
    sys.exit(main())
