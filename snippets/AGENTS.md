# Shared machine (compact rules)

For agents that read a rules file but not skills. Paste this into `AGENTS.md` (or `CLAUDE.md`) and set the path to `machine.py`.

Script: `~/shared-machine-skill/.claude/skills/shared-machine/scripts/machine.py` (below: `machine.py`).

- Before heavy work (builds, renders, benchmarks, large model loads), run `machine.py status`, then `machine.py check --cpu N` (and `--mem`, `--vram`, `--gpu-bench`). If it does not print `ok`, wait or ask the user; do not squeeze the work through another way.
- Start heavy commands as `machine.py run --what "..." --cpu N -- <command>`: it puts a claim on the shared board, runs at lower priority and removes the claim at the end. `machine.py jobs` suggests a `-j`.
- Tell other sessions with `machine.py say "..."`. Claude Code sessions can also message each other directly.
- Do not stop or reprioritise processes you did not start. The person at the machine comes first. Silence from another session is not a yes.
