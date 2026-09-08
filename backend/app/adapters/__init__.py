"""Attendance device adapters.

Adapters translate brand/protocol-specific behaviour into the neutral
``AttendanceAdapter`` interface defined in ``base.py``.  The core system never
depends on a specific vendor: adapters are discovered through the registry and
selected based on evidence collected by the discovery engine.
"""
