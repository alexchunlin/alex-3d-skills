"""guarded_run: run a program so that a crash never reaches macOS's crash reporter (no "quit unexpectedly" dialog).

    from guarded_run import run, run_sandboxed
    r = run(argv, env=..., cwd=..., timeout=120)
    r = run_sandboxed(argv, profile_sbpl, env=..., cwd=..., timeout=120)   # the guard itself runs inside sandbox-exec
    r -> {"status": "exit" | "crashed" | "timeout" | "spawn_error", "code", "exception", "stdout", "stderr", "seconds"}

The child is started with posix_spawn and its task exception ports (bad access, bad instruction, arithmetic, breakpoint,
guard, crash) point at a Mach port this process owns. A hardware fault arrives here first: the child is killed with
SIGKILL (which never produces a crash report) before the kernel would forward it to ReportCrash. An abort() (EXC_CRASH)
is answered KERN_SUCCESS, which ends delivery there. Crashpad uses the same mechanism to keep its clients' crashes
away from the system reporter.

Why: the user saw Bambu Studio crash pop-ups when an agent ran its CLI with hand-built profiles; 10 crash reports from
2026-10-24, all SIGSEGV inside Slic3r::CLI::run (FINDINGS "v2 post-freeze"). stdlib only (ctypes).
"""
import ctypes, ctypes.util, os, signal, subprocess, sys, tempfile, threading, time

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "/usr/lib/libSystem.B.dylib", use_errno=True)

KERN_SUCCESS = 0
MACH_PORT_RIGHT_RECEIVE = 1
MACH_MSG_TYPE_MAKE_SEND = 20
MACH_MSG_TYPE_MOVE_SEND_ONCE = 18
MACH_RCV_MSG = 0x2
MACH_SEND_MSG = 0x1
MACH_RCV_TIMEOUT = 0x100
MACH_RCV_TIMED_OUT = 0x10004003
# EXCEPTION_DEFAULT (identity ports): the only behavior tested to keep an abort() away from ReportCrash; EXCEPTION_STATE
# contains faults but an abort still wrote a report. Setting it on a platform binary (/bin, /usr, sandbox-exec) is an
# EXC_GUARD SET_EXCEPTION_BEHAVIOR kill of the spawner on macOS 27.0.1, so run() refuses those paths.
EXCEPTION_DEFAULT = 1
MACH_EXCEPTION_CODES = 0x80000000
PLATFORM_DIRS = ("/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/usr/libexec/", "/System/")
EXC_NAMES = {1: "EXC_BAD_ACCESS", 2: "EXC_BAD_INSTRUCTION", 3: "EXC_ARITHMETIC", 5: "EXC_SOFTWARE", 6: "EXC_BREAKPOINT",
             10: "EXC_CRASH", 11: "EXC_RESOURCE", 12: "EXC_GUARD"}
FATAL = (1, 2, 3, 6, 12)
MASK = sum(1 << e for e in (1, 2, 3, 6, 10, 12))
THREAD_STATE_NONE = 5 if os.uname().machine == "arm64" else 13


class _Hdr(ctypes.Structure):
    _fields_ = [("bits", ctypes.c_uint32), ("size", ctypes.c_uint32), ("remote", ctypes.c_uint32),
                ("local", ctypes.c_uint32), ("voucher", ctypes.c_uint32), ("id", ctypes.c_int32)]


class _Reply(ctypes.Structure):
    _fields_ = [("hdr", _Hdr), ("ndr", ctypes.c_uint8 * 8), ("ret", ctypes.c_int32)]


def _task_self():
    return ctypes.c_uint32.in_dll(_libc, "mach_task_self_").value


def _new_port():
    port = ctypes.c_uint32(0)
    t = _task_self()
    kr = _libc.mach_port_allocate(t, MACH_PORT_RIGHT_RECEIVE, ctypes.byref(port))
    if kr:
        raise OSError("mach_port_allocate: %d" % kr)
    kr = _libc.mach_port_insert_right(t, port.value, port.value, MACH_MSG_TYPE_MAKE_SEND)
    if kr:
        raise OSError("mach_port_insert_right: %d" % kr)
    return port.value


def _free_port(p):
    _libc.mach_port_mod_refs(_task_self(), p, MACH_PORT_RIGHT_RECEIVE, -1)


def _spawn(argv, env, cwd, port, out_fd, err_fd):
    attr = ctypes.c_void_p()
    fa = ctypes.c_void_p()
    _libc.posix_spawnattr_init(ctypes.byref(attr))
    _libc.posix_spawn_file_actions_init(ctypes.byref(fa))
    try:
        rc = _libc.posix_spawnattr_setexceptionports_np(ctypes.byref(attr), ctypes.c_uint32(MASK), ctypes.c_uint32(port),
                                                         ctypes.c_int(EXCEPTION_DEFAULT | MACH_EXCEPTION_CODES), ctypes.c_int(THREAD_STATE_NONE))
        if rc:
            raise OSError(rc, "posix_spawnattr_setexceptionports_np")
        devnull = os.open(os.devnull, os.O_RDONLY)
        for src, dst in ((devnull, 0), (out_fd, 1), (err_fd, 2)):
            _libc.posix_spawn_file_actions_adddup2(ctypes.byref(fa), src, dst)
        if cwd:
            _libc.posix_spawn_file_actions_addchdir_np(ctypes.byref(fa), os.fsencode(cwd))
        cargv = (ctypes.c_char_p * (len(argv) + 1))(*[os.fsencode(a) for a in argv], None)
        envl = ["%s=%s" % kv for kv in env.items()]
        cenv = (ctypes.c_char_p * (len(envl) + 1))(*[os.fsencode(e) for e in envl], None)
        pid = ctypes.c_int(0)
        rc = _libc.posix_spawn(ctypes.byref(pid), os.fsencode(argv[0]), ctypes.byref(fa), ctypes.byref(attr), cargv, cenv)
        os.close(devnull)
        if rc:
            raise OSError(rc, "posix_spawn %s: %s" % (argv[0], os.strerror(rc)))
        return pid.value
    finally:
        _libc.posix_spawn_file_actions_destroy(ctypes.byref(fa))
        _libc.posix_spawnattr_destroy(ctypes.byref(attr))


def run(argv, env=None, cwd=None, timeout=300.0):
    """Run argv guarded (see the module doc)."""
    exe = os.path.realpath(argv[0])
    if exe.startswith(PLATFORM_DIRS):
        return dict(status="spawn_error", code=None, exception=None, argv=argv, stdout="", seconds=0.0,
                    stderr="guarded_run: %s is a platform binary; macOS kills a spawner that sets its exception ports" % exe)
    env = dict(os.environ if env is None else env)
    port = _new_port()
    out = tempfile.TemporaryFile()
    err = tempfile.TemporaryFile()
    t0 = time.time()
    res = {"status": None, "code": None, "exception": None, "argv": argv}
    try:
        pid = _spawn(argv, env, cwd, port, out.fileno(), err.fileno())
    except OSError as e:
        _free_port(port)
        return dict(res, status="spawn_error", stderr=str(e), stdout="", seconds=0.0)
    buf = ctypes.create_string_buffer(4096)
    killed = None
    while True:
        wp, st = os.waitpid(pid, os.WNOHANG)
        if wp == pid:
            break
        kr = _libc.mach_msg(buf, MACH_RCV_MSG | MACH_RCV_TIMEOUT, 0, len(buf), port, 50, 0)
        if kr == KERN_SUCCESS:
            hdr = _Hdr.from_buffer(buf)
            # mach_exception_raise request (id 2405): header 24, body 4, thread and task port descriptors 2 x 12,
            # NDR 8: exception at 60
            exc = ctypes.c_int32.from_buffer(buf, 60).value
            res["exception"] = EXC_NAMES.get(exc, "exception %d" % exc)
            if exc in FATAL and killed is None:
                os.kill(pid, signal.SIGKILL)       # no reply: the faulting thread waits; SIGKILL leaves no crash report
                killed = "crashed"
            else:                                  # EXC_CRASH (abort): handled here, so not forwarded to ReportCrash
                rep = _Reply()
                rep.hdr.bits = MACH_MSG_TYPE_MOVE_SEND_ONCE
                rep.hdr.size = ctypes.sizeof(_Reply)
                rep.hdr.remote = hdr.remote
                rep.hdr.id = hdr.id + 100
                rep.ndr[:] = [0, 0, 0, 0, 1, 0, 0, 0]
                rep.ret = KERN_SUCCESS
                _libc.mach_msg(ctypes.byref(rep), MACH_SEND_MSG, ctypes.sizeof(_Reply), 0, 0, 0, 0)
                if exc == 10:
                    killed = killed or "crashed"
        elif kr != MACH_RCV_TIMED_OUT:
            time.sleep(0.05)
        if killed is None and time.time() - t0 > timeout:
            os.kill(pid, signal.SIGKILL)
            killed = "timeout"
    _free_port(port)
    out.seek(0)
    err.seek(0)
    res.update(stdout=out.read().decode("utf-8", "replace"), stderr=err.read().decode("utf-8", "replace"), seconds=round(time.time() - t0, 1))
    if os.WIFSIGNALED(st):
        res["status"] = killed or "crashed"
        res["code"] = -os.WTERMSIG(st)
    else:
        res["status"] = killed or "exit"
        res["code"] = os.WEXITSTATUS(st)
    return res


def run_sandboxed(argv, profile, env=None, cwd=None, timeout=300.0):
    """Run argv guarded inside `sandbox-exec -p profile`. The guard runs in the sandbox with the child: a guard outside
    it that receives a sandboxed child's exception (with its task port) is killed by the kernel (SIGKILL, tested on
    macOS 27.0.1)."""
    import json
    env = dict(os.environ if env is None else env)
    cmd = ["/usr/bin/sandbox-exec", "-p", profile, sys.executable, "-B", "-I", os.path.abspath(__file__), "--json",
           "--timeout", str(timeout)] + (["--cwd", cwd] if cwd else []) + ["--"] + list(argv)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "code": None, "exception": None, "stdout": "", "stderr": "guard did not return", "argv": argv,
                "seconds": round(time.time() - t0, 1)}
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("GUARDED_RESULT "):
            return json.loads(line[len("GUARDED_RESULT "):])
    return {"status": "spawn_error", "code": p.returncode, "exception": None, "stdout": p.stdout[-4000:], "argv": argv,
            "stderr": "sandbox-exec or the guard failed (exit %s): %s" % (p.returncode, p.stderr[-2000:]), "seconds": round(time.time() - t0, 1)}


def crash_reports_since(t, names):
    """Crash reports (.ips) written after time t whose file name starts with one of names: proof a guard leaked."""
    d = os.path.expanduser("~/Library/Logs/DiagnosticReports")
    try:
        return sorted(f for f in os.listdir(d) if any(f.startswith(n) for n in names) and os.path.getmtime(os.path.join(d, f)) >= t - 1)
    except OSError:
        return []


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--json":                    # inner half of run_sandboxed
        import json
        k = a.index("--")
        opt = dict(zip(a[1:k:2], a[2:k:2]))
        r = run(a[k + 1:], cwd=opt.get("--cwd"), timeout=float(opt.get("--timeout", 300)))
        r["stdout"], r["stderr"] = r["stdout"][-20000:], r["stderr"][-20000:]
        print("GUARDED_RESULT " + json.dumps(r))
    else:
        r = run(a, timeout=60)
        print({k: v for k, v in r.items() if k not in ("stdout", "stderr")})
