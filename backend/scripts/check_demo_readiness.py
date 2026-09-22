#!/usr/bin/env python3
"""ML Dependency Readiness Check Script.

Validates that all critical local ML dependencies and model weights are installed
and operable for offline demonstration and evaluation:
1. sentence_transformers
2. spacy (load en_core_web_sm)
3. torch

Prints PASS/FAIL per library with exact error details on failure.
Exits with code 0 if all pass, or 1 if any check fails.
"""

from __future__ import annotations

import sys
import traceback


def check_dependencies() -> bool:
    checks = [
        ("torch", _check_torch),
        ("sentence_transformers", _check_sentence_transformers),
        ("spacy (en_core_web_sm)", _check_spacy),
    ]

    all_passed = True
    print("=" * 60)
    print("OIL HSE Decision Support System — ML Dependency Readiness Check")
    print("=" * 60)

    for name, check_fn in checks:
        passed, details = check_fn()
        status_str = "PASS" if passed else "FAIL"
        print(f"[{status_str}] {name}: {details}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("OVERALL STATUS: ALL ML DEPENDENCIES OPERATIONAL (PASS)")
    else:
        print("OVERALL STATUS: MISSING OR MISCONFIGURED DEPENDENCIES (FAIL)")
    print("=" * 60)

    return all_passed


def _check_torch() -> tuple[bool, str]:
    try:
        import torch

        version = getattr(torch, "__version__", "unknown")
        cuda_avail = torch.cuda.is_available()
        mps_avail = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        accel = "cuda" if cuda_avail else ("mps" if mps_avail else "cpu")
        return True, f"installed (v{version}, device={accel})"
    except Exception as e:
        return False, f"ImportError / Execution error: {e}\n{traceback.format_exc()}"


def _check_sentence_transformers() -> tuple[bool, str]:
    try:
        import sentence_transformers

        version = getattr(sentence_transformers, "__version__", "unknown")
        return True, f"installed (v{version})"
    except Exception as e:
        return False, f"ImportError / Execution error: {e}\n{traceback.format_exc()}"


def _check_spacy() -> tuple[bool, str]:
    try:
        import spacy

        version = getattr(spacy, "__version__", "unknown")
        nlp = spacy.load("en_core_web_sm")
        pipeline = nlp.pipe_names
        return True, f"installed (v{version}, pipeline={pipeline})"
    except Exception as e:
        return False, f"Model load failure / Execution error: {e}\n{traceback.format_exc()}"


def main() -> None:
    success = check_dependencies()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
