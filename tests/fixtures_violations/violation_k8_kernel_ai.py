# tests/fixtures_violations/violation_k8_kernel_ai.py
# Намеренное нарушение K8/F4: kernel импортирует akb/research/llm.
import akb  # K8/F4 violation
