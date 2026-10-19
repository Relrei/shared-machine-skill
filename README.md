# shared-machine-skill

A skill for CLI coding agents that share one machine with the person at it and with each other. Before heavy work, the agent checks free CPU, memory and GPU, runs the work at lower priority with a note on a shared board, and tells the other sessions what it is about to run.

Made for CLI agents such as Claude Code and OpenCode. **Claude Code is recommended** for the messaging part: it can list the other Claude Code sessions on the same machine and send them messages directly. Other agents use notes on the shared board, which works between any agents.

Cloud sessions run on other machines, so this does not apply to them.

## Why

This comes out of one person running several agent sessions on one desktop while working at it.

- A build on every core made the desktop lag for the person using it, so builds ran at lower priority with a few cores left free.
- GPU benchmarks ran one at a time, so that their numbers would not disturb each other.
- Sessions did not know what the others were running.

The rules were first written for one agent as a rules file. This turns them into a skill with a small script, so any session can check the machine and see what the others run.

The ground rules come from the same setup as [decision-log-skill](https://github.com/Relrei/decision-log-skill): guards that blocked agents led them to look for another way through. So the board only informs. When something does not fit, the agent waits or asks the user.

## What's in here

| Path | What it is |
|---|---|
| `.claude/skills/shared-machine/SKILL.md` | The skill: when to check, how to start heavy work, how to tell other sessions. |
| `.claude/skills/shared-machine/scripts/machine.py` | `status`, `check`, `jobs`, `run`, `claim`, `release`, `say`. Python 3, standard library only. |
| `snippets/AGENTS.md` | A compact version for agents that read a rules file but not skills. |

## Install

The machine is shared by every project, so install the skill for your user, not per project:

- **Claude Code:** copy `.claude/skills/shared-machine/` to `~/.claude/skills/shared-machine/`.
- **OpenCode:** the same folder works (OpenCode also reads `~/.claude/skills/`).
- **Agents without skills:** paste `snippets/AGENTS.md` into your rules file and set the script path.

Optional: put limits in `~/.config/shared-machine/config.json` (see the skill for the keys), for example a VRAM ceiling.

## Try it

```bash
S=.claude/skills/shared-machine/scripts/machine.py
python3 $S status                                   # cores, memory, GPU, the board
python3 $S check --cpu 8 --gpu-bench                # "ok", or reasons to wait
python3 $S run --what "build" --cpu 9 -- make -j9   # claim, nice, run, release
python3 $S say "rendering until 21:00, GPU busy"    # a note for other sessions
```

Linux is the main target: memory comes from `/proc/meminfo`, the GPU from `nvidia-smi` (NVIDIA only). Without them, those lines are left out and the rest works.

## Make it yours

The limits fit one desktop. On a machine with many cores, lowering priority may already be enough; on a laptop you may want more cores kept free. Change the config and the skill as you use it.

## License

MIT
