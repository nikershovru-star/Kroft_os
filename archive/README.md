# Archive

`KnowledgeOS-v5/` — legacy codebase, migrated into `KROFT_OS/` via Variant A merge
(commit `84417b9` "merge: import KnowledgeOS-v5 codebase with full history").

- **Full git history preserved** in `KROFT_OS` — see `git log legacy/master` /
  the merged commits. No history was lost.
- This `archive/` folder is a **reference copy** only. Do not modify.
- The original `KnowledgeOS-v5/` remains in place at the sibling path
  (`../KnowledgeOS-v5/`) because the OS blocked the `mv` rename; it is
  git-ignored in the unified repo (`/KnowledgeOS-v5/` in `.gitignore`).
  Delete the original manually once you have confirmed the merged repo is complete.

## Why archive, not delete
Operational safety: the unified `KROFT_OS/` repo now owns docs + code + history.
The legacy folder is kept read-only for forensic reference until the user
explicitly removes it.
