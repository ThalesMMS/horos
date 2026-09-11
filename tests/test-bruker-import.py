#!/usr/bin/env python3
"""Same Bruker/Enhanced gate, under the bruker glob the suite is asked to run."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name('test-dicom-bruker-import.py')), run_name='__main__')
