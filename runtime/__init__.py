"""runtime package — Runtime Host (manifest-based components, NO wrappers).

Exposes the names the existing tests and the frozen microkernel expect:
- `RuntimeContext` (referenced by kernel/kernel.py via `from runtime import RuntimeContext`)
- `CapabilityRegistry` (referenced by existing tests via `from runtime import CapabilityRegistry`)

CRITICAL (arch-gate LAW): `runtime.*` may import ONLY `contracts.*`. It must NOT
import the `kernel` package. The concrete `Kernel` is injected from the composition
root (bootstrap_v2.py, outside the scanned packages) — never imported here. This
package depends solely on `contracts.IKernel`, never on the concrete kernel.
"""
from .context import RuntimeContext
from .capability_registry import CapabilityRegistry

__all__ = ["RuntimeContext", "CapabilityRegistry"]
