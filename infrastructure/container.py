"""Dependency Injection Container — the Composition Root.

Single point of truth for:
  * registering service factories (lazy or eager),
  * resolving instantiated, fully-wired components,
  * preventing hard coupling between services and adapters.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, Type


class DependencyContainer:
    """Factory + resolver for the system's components."""

    def __init__(self) -> None:
        # name -> factory callable (called on resolve)
        self._factories: Dict[str, Callable[..., Any]] = {}
        # name -> singleton instance (cached after first resolve)
        self._singletons: Dict[str, Any] = {}
        self._registered_as_singleton: Dict[str, bool] = {}

    # ----- registration -----
    def register_factory(
        self,
        name: str,
        factory: Callable[..., Any],
        singleton: bool = True,
    ) -> None:
        """Register a factory. If singleton, resolution is cached."""
        if not callable(factory):
            raise TypeError(f"Factory for '{name}' must be callable.")
        self._factories[name] = factory
        self._registered_as_singleton[name] = singleton
        self._singletons.pop(name, None)

    def register_instance(self, name: str, instance: Any) -> None:
        """Register an already-built instance as a singleton."""
        self._factories[name] = lambda: instance
        self._registered_as_singleton[name] = True
        self._singletons[name] = instance

    # ----- resolution -----
    def resolve(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self._factories:
            raise KeyError(f"Service '{name}' is not registered.")
        if self._registered_as_singleton.get(name, True):
            if name not in self._singletons:
                self._singletons[name] = self._factories[name](*args, **kwargs)
            return self._singletons[name]
        return self._factories[name](*args, **kwargs)

    def has(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> list[str]:
        return list(self._factories.keys())

    def clear(self) -> None:
        self._factories.clear()
        self._singletons.clear()
        self._registered_as_singleton.clear()
