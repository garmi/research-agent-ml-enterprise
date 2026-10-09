#!/usr/bin/env python3
"""Example usage of the research agent."""

import sys
from src.app import main

if __name__ == "__main__":
    print("Starting Research Agent...\n")
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
