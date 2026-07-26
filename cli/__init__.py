"""KnowledgeOS v5 CLI -- product entrypoint (application layer).

The CLI may import infrastructure/kernel/services/contracts. It must NOT
import adapters directly; concrete adapters are wired only through the DI
container (see main.build_container).
"""
