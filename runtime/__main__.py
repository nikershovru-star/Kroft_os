"""runtime/__main__.py — thin entry point for `python -m runtime`.

Does NOT duplicate the microkernel. Delegates to runtime.kernel_runtime.main().
"""
from runtime.kernel_runtime import main

if __name__ == "__main__":
    raise SystemExit(main())
