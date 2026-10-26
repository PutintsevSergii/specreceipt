#!/usr/bin/env python3
"""Portable entry point; defaults to a read-only plan."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harnesslib.runtime import activate
activate()
from harnesslib.cli import main

if __name__ == '__main__':
    sys.argv = [str(ROOT/'harness'),'tools','update',*sys.argv[1:]]
    raise SystemExit(main())
