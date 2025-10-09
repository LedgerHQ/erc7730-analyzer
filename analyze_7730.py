#!/usr/bin/env python3
"""
Wrapper script that calls the main analyzer in src/

This allows users to run `python analyze_7730.py` from the root directory.
"""

import sys
from pathlib import Path

# Add src directory to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Import and run the main function
from analyze_7730 import main

if __name__ == "__main__":
    main()
