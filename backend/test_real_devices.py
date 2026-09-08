#!/usr/bin/env python3
"""Convenience wrapper: run the real-device read-only test from the repo root.

Windows usage::

    cd backend
    python test_real_devices.py
    python test_real_devices.py --json --out real_device_report.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import asyncio  # noqa: E402
from scripts.test_real_devices import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())
