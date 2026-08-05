"""Console logging helpers shared by Agent orchestration modules."""

import sys


class _C:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def _log(msg, color=""):
    prefix = f"{_C.BOLD}{_C.BLUE}[Agent]{_C.ENDC}"
    if color:
        print(f"{prefix} {color}{msg}{_C.ENDC}", file=sys.stderr, flush=True)
    else:
        print(f"{prefix} {msg}", file=sys.stderr, flush=True)


def _log_warn(msg):
    _log(f"⚠ {msg}", _C.WARNING)


def _log_error(msg):
    _log(f"✗ {msg}", _C.FAIL)


def _log_ok(msg):
    _log(f"✓ {msg}", _C.GREEN)


def _log_section(title):
    _log(f"── {title} " + "─" * max(0, 50 - len(title)))


def _log_round_header(round_num):
    _log(f"── Round {round_num} " + "─" * max(0, 50 - len(str(round_num)) - 7))


def _log_banner(msg):
    _log("═" * 55)
    _log(msg)
    _log("═" * 55)
