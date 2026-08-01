# tests/fixtures_violations/violation_f1_recovery_sleep.py
# Намеренное нарушение F1: blocking sleep в recovery.
import time


def wait_ready():
    time.sleep(30)  # F1 violation
