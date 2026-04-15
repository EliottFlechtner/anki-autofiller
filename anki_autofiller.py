#!/usr/bin/env python3
"""Backward-compatible entrypoint for the CLI.

The implementation now lives in smaller modules for readability.
"""

from cli import main


if __name__ == "__main__":
    main()
