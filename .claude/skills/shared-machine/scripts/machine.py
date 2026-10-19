#!/usr/bin/env python3
"""Check the machine's CPU, memory and GPU, and keep a shared board of what
each agent session is running, so sessions on one machine can avoid piling
heavy work on top of each other.

Standard library only. The board is a folder of small JSON files; nothing
here blocks anything. It reports, and the agent decides (or asks the user).

    machine.py status                         what is free, and who is running what
    machine.py jobs                           a suggested -j for a build
    machine.py check --cpu 8 --gpu-bench      would this fit? prints "ok" or the reasons
    machine.py run --what build -- ninja -j5  run a command with a claim on the board
    machine.py claim --what render --hours 3  claim for work you start yourself
    machine.py release <id>                   remove a claim
    machine.py say "message"                  leave a note for other sessions
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

DEFAULTS = {
    # Cores left for the person at the machine and everything else.
    # None means max(2, cores // 4).
    "keep_free_cores": None,
    # Priority for heavy commands started through `run` (0 = normal, 19 = lowest).
    "nice": 10,
    # Upper limit for this machine's total GPU memory use, in MiB. None = no limit.
    "vram_limit_mib": None,
    # How many claims marked --gpu-bench may run at once.
    "gpu_bench_max": 1,
    # How long a note from `say` stays on the board.
    "note_hours": 24,
}


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "shared-machine", "config.json")


def load_config():
    cfg = dict(DEFAULTS)
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, ValueError) as e:
            print(f"note: could not read {path}: {e}; using defaults", file=sys.stderr)
    return cfg


def board_dir():
    d = os.environ.get("SHARED_MACHINE_BOARD")
    if not d:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime and os.path.isdir(runtime):
            d = os.path.join(runtime, "shared-machine")
        else:
            d = os.path.join(tempfile.gettempdir(), f"shared-machine-{os.getuid()}")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


# --- reading the machine ---------------------------------------------------

def core_count():
    try:
        return len(os.sched_getaffinity(0))  # cores this process may use (Linux)
    except AttributeError:
        return os.cpu_count() or 1


def cpu_info():
    cores = core_count()
    try:
        load1, load5, _ = os.getloadavg()
    except OSError:
        load1 = load5 = None
    return {"cores": cores, "load1": load1, "load5": load5}


def mem_info():
    """Total and available memory in MiB, from /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            kv = {}
            for line in f:
                key, _, rest = line.partition(":")
                kv[key] = int(rest.split()[0])  # kB
        return {"total_mib": kv["MemTotal"] // 1024, "available_mib": kv["MemAvailable"] // 1024}
    except (OSError, KeyError, ValueError, IndexError):
        return None


def gpu_info():
    """NVIDIA GPUs through nvidia-smi, if it is installed. Otherwise None."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True).stdout
        apps = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    gpus = []
    for line in out.strip().splitlines():
        idx, name, used, total, util = [x.strip() for x in line.split(",")]
        gpus.append({"index": int(idx), "name": name, "used_mib": int(used),
                     "total_mib": int(total), "util_pct": int(util)})
    procs = []
    for line in apps.strip().splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 3 and parts[0].isdigit():
            procs.append({"pid": int(parts[0]), "name": os.path.basename(parts[1]),
                          "used_mib": int(parts[2]) if parts[2].isdigit() else None})
    return {"gpus": gpus, "processes": procs}


# --- the board -------------------------------------------------------------

def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_entry(entry):
    path = os.path.join(board_dir(), entry["id"] + ".json")
    fd, tmp = tempfile.mkstemp(dir=board_dir(), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def read_board(clean=True):
    """Live entries. Entries whose process is gone or whose time is up are removed."""
    now = time.time()
    live = []
    d = board_dir()
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        try:
            with open(path, encoding="utf-8") as f:
                e = json.load(f)
        except (OSError, ValueError):
            continue
        expired = e.get("until") and e["until"] < now
        dead = e.get("pid") and not pid_alive(e["pid"])
        if expired or dead:
            if clean:
                try:
                    os.remove(path)
                except OSError:
                    pass
            continue
        live.append(e)
    return live


def new_entry(kind, args):
    return {
        "id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        "kind": kind,
        "session": args.session or os.environ.get("SHARED_MACHINE_SESSION") or os.path.basename(os.getcwd()),
        "what": getattr(args, "what", None),
        "cpu": getattr(args, "cpu", None),
        "mem_mib": getattr(args, "mem", None),
        "vram_mib": getattr(args, "vram", None),
        "gpu_bench": bool(getattr(args, "gpu_bench", False)),
        "note": getattr(args, "note", None),
        "cwd": os.getcwd(),
        "since": time.time(),
        "until": None,
        "pid": None,
    }


def keep_free(cfg, cores):
    k = cfg.get("keep_free_cores")
    return max(2, cores // 4) if k is None else int(k)


def suggest_jobs(cfg, board, cores):
    claimed = sum(e.get("cpu") or 0 for e in board if e["kind"] == "claim")
    return max(1, cores - keep_free(cfg, cores) - claimed)


def warnings_for(cfg, board, gpu, want=None):
    """Plain-language reasons to wait or ask. Nothing is enforced."""
    out = []
    benches = [e for e in board if e["kind"] == "claim" and e.get("gpu_bench")]
    if want and want.get("gpu_bench") and len(benches) >= int(cfg.get("gpu_bench_max") or 1):
        out.append(f"{len(benches)} GPU benchmark(s) already on the board (limit {cfg.get('gpu_bench_max')}); "
                   "numbers would disturb each other")
    limit = cfg.get("vram_limit_mib")
    if limit and gpu and gpu["gpus"]:
        used = sum(g["used_mib"] for g in gpu["gpus"])
        add = (want or {}).get("vram_mib") or 0
        if used + add > limit:
            out.append(f"GPU memory would be {used + add} MiB, over the set limit of {limit} MiB")
    if want and want.get("cpu"):
        cores = core_count()
        room = suggest_jobs(cfg, board, cores)
        if want["cpu"] > room:
            out.append(f"asking for {want['cpu']} cores, about {room} are free for heavy work")
    return out


# --- commands ---------------------------------------------------------------

def fmt_age(t):
    m = int((time.time() - t) // 60)
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def cmd_status(args, cfg):
    cpu, mem, gpu, board = cpu_info(), mem_info(), gpu_info(), read_board()
    if args.json:
        print(json.dumps({"cpu": cpu, "mem": mem, "gpu": gpu, "board": board,
                          "suggested_jobs": suggest_jobs(cfg, board, cpu["cores"]),
                          "warnings": warnings_for(cfg, board, gpu)}, ensure_ascii=False, indent=1))
        return 0
    load = f", load {cpu['load1']:.1f} (1 min) / {cpu['load5']:.1f} (5 min)" if cpu["load1"] is not None else ""
    print(f"CPU: {cpu['cores']} cores{load}; suggested -j {suggest_jobs(cfg, board, cpu['cores'])}")
    if mem:
        print(f"Memory: {mem['available_mib']} MiB free of {mem['total_mib']} MiB")
    if gpu is None:
        print("GPU: no nvidia-smi")
    else:
        for g in gpu["gpus"]:
            print(f"GPU {g['index']}: {g['name']}, {g['used_mib']}/{g['total_mib']} MiB, {g['util_pct']}% busy")
        for p in gpu["processes"]:
            print(f"  pid {p['pid']} {p['name']}: {p['used_mib']} MiB")
    claims = [e for e in board if e["kind"] == "claim"]
    notes = [e for e in board if e["kind"] == "note"]
    print(f"Board ({board_dir()}): {len(claims)} claim(s), {len(notes)} note(s)")
    for e in claims:
        parts = [f"{e['cpu']} cores" if e.get("cpu") else None,
                 f"{e['mem_mib']} MiB RAM" if e.get("mem_mib") else None,
                 f"{e['vram_mib']} MiB VRAM" if e.get("vram_mib") else None,
                 "GPU benchmark" if e.get("gpu_bench") else None]
        use = ", ".join(p for p in parts if p) or "no amounts given"
        print(f"  [{e['id']}] {e['session']}: {e['what']} ({use}), {fmt_age(e['since'])} ago")
    for e in notes:
        print(f"  note from {e['session']}, {fmt_age(e['since'])} ago: {e['note']}")
    for w in warnings_for(cfg, board, gpu):
        print(f"Warning: {w}")
    return 0


def cmd_jobs(args, cfg):
    print(suggest_jobs(cfg, read_board(), core_count()))
    return 0


def report_conflicts(cfg, entry):
    ws = warnings_for(cfg, read_board(), gpu_info() if (entry["vram_mib"] or entry["gpu_bench"]) else None, entry)
    for w in ws:
        print(f"shared-machine: {w}", file=sys.stderr)
    return ws


def cmd_run(args, cfg):
    if not args.command:
        print("give the command after --", file=sys.stderr)
        return 2
    entry = new_entry("claim", args)
    entry["what"] = entry["what"] or " ".join(args.command)[:80]
    report_conflicts(cfg, entry)
    entry["pid"] = os.getpid()
    path = write_entry(entry)
    nice = cfg.get("nice") if args.nice is None else args.nice
    cmd = list(args.command)
    if nice and shutil.which("nice"):
        cmd = ["nice", "-n", str(int(nice))] + cmd
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 130
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def cmd_check(args, cfg):
    entry = new_entry("claim", args)
    ws = warnings_for(cfg, read_board(), gpu_info(), entry)
    print("\n".join(ws) if ws else "ok")
    return 0


def cmd_claim(args, cfg):
    entry = new_entry("claim", args)
    entry["until"] = time.time() + args.hours * 3600
    if args.pid:
        entry["pid"] = args.pid
    report_conflicts(cfg, entry)
    write_entry(entry)
    print(entry["id"])
    return 0


def cmd_release(args, cfg):
    path = os.path.join(board_dir(), args.id + ".json")
    if not os.path.exists(path):
        print(f"no claim {args.id}", file=sys.stderr)
        return 1
    os.remove(path)
    return 0


def cmd_say(args, cfg):
    entry = new_entry("note", args)
    entry["note"] = " ".join(args.message)
    entry["until"] = time.time() + float(cfg.get("note_hours") or 24) * 3600
    write_entry(entry)
    print(entry["id"])
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", help="name shown on the board (default: $SHARED_MACHINE_SESSION or the folder name)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="what is free, and who is running what")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("jobs", help="print a suggested -j for a build")
    s.set_defaults(func=cmd_jobs)

    def amounts(s):
        s.add_argument("--what", help="short description, e.g. 'build', 'render', 'benchmark'")
        s.add_argument("--cpu", type=int, help="cores it will use")
        s.add_argument("--mem", type=int, help="RAM in MiB it will use")
        s.add_argument("--vram", type=int, help="GPU memory in MiB it will use")
        s.add_argument("--gpu-bench", action="store_true", help="a GPU benchmark (others disturb its numbers)")

    s = sub.add_parser("run", help="run a command with a claim on the board, at lower priority")
    amounts(s)
    s.add_argument("--nice", type=int, help="priority for the command (default from config, 10)")
    s.add_argument("command", nargs=argparse.REMAINDER)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("check", help="would this fit? prints 'ok' or the reasons to wait or ask")
    amounts(s)
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("claim", help="claim for work you start yourself; prints the claim id")
    amounts(s)
    s.add_argument("--hours", type=float, default=2, help="the claim ends after this long (default 2)")
    s.add_argument("--pid", type=int, help="the claim ends when this process ends")
    s.set_defaults(func=cmd_claim)

    s = sub.add_parser("release", help="remove a claim")
    s.add_argument("id")
    s.set_defaults(func=cmd_release)

    s = sub.add_parser("say", help="leave a note for other sessions")
    s.add_argument("message", nargs="+")
    s.set_defaults(func=cmd_say)

    args = p.parse_args(argv)
    if getattr(args, "command", None) and args.command[:1] == ["--"]:
        args.command = args.command[1:]
    return args.func(args, load_config())


if __name__ == "__main__":
    sys.exit(main())
