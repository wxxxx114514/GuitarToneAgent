r"""交付前的一条命令检查：全部工具能编译 + 两个回归套件全过

用法:  tone.bat run check_all.py
退出码: 0 = 全过；1 = 有失败（**失败就不许交付／不许进下一批**）

为什么要有它：批 1.5 的最后一次编辑给 di_instructions.py 插了 4 行、多缩进 4 个空格，
那一次我【没跑 py_compile】—— 交付出去的包第 ③ 步直接 SyntaxError，一个输出都没有，
是我自己的复验数字（编辑前跑的）掩盖了它。工具链的每一环都要有一条能当场红的命令。
"""
import sys, os, json, subprocess, py_compile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
TOOLS = sorted(f for f in os.listdir(HERE) if f.endswith(".py"))

STAMP = os.path.join(os.path.dirname(ROOT), "_tmp_param", "last_gate.json")


def _load_stamp():
    try:
        return json.load(open(STAMP, encoding="utf-8"))
    except Exception:
        return {}


def _save_stamp():
    try:
        os.makedirs(os.path.dirname(STAMP), exist_ok=True)
        json.dump({f: os.path.getmtime(os.path.join(HERE, f)) for f in TOOLS},
                  open(STAMP, "w", encoding="utf-8"))
    except Exception:
        pass


_prev = _load_stamp()
_changed = [f for f in TOOLS
            if f not in _prev or _prev[f] != os.path.getmtime(os.path.join(HERE, f))]
if _changed:
    # ★ 这条提示是为一个真实习惯漏洞加的：改完工具【没跑门】就汇报 —— 三次事故
    #   （批 1.5 的 SyntaxError、批 2 的 _rq/_score、第三次删掉 palm/mid/opn 的赋值）
    #   都是"编译过、门能抓、但我没跑"。看到这行就说明：上次全绿之后又动过文件。
    print("  自上次全绿以来改过 %d 个文件：%s" % (len(_changed), " ".join(_changed[:6])))

bad = []
for f in TOOLS:
    try:
        py_compile.compile(os.path.join(HERE, f), doraise=True)
    except py_compile.PyCompileError as e:
        bad.append((f, str(e).strip().splitlines()[-1]))
print("=" * 70)
print("  编译 %d 个脚本" % len(TOOLS))
print("=" * 70)
for f, err in bad:
    print("  FAIL %-28s %s" % (f, err))
if not bad:
    print("  全部通过")

suites = ["test_tuning.py", "test_start_preset.py", "fingering.py", "test_di_instructions.py",
          "test_verify_di.py", "test_bass_reference.py", "test_target_whole.py"]
# ★ 每个工具至少一条"真跑一遍"的门：编译过 != 能跑（批 2 的 NameError 就是这么漏的）
for s in suites:
    p = os.path.join(HERE, s)
    if not os.path.exists(p):
        print("  SKIP %s（不存在）" % s); continue
    # ★ 必须给子进程 UTF-8：否则它在 GBK 控制台下把中文写成 GBK，这里按 utf-8 解就全是乱码，
    #   "N 条：..." 那一行抓不到（门还是绿的，只是看不见数字）
    _env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, p], capture_output=True, text=True, encoding="utf-8", errors="replace", env=_env)
    tail = [l for l in (r.stdout or "").splitlines() if ("条：" in l or "通过 /" in l)]
    print("  %-4s %-24s %s" % ("PASS" if r.returncode == 0 else "FAIL", s,
                               tail[-1].strip() if tail else "（没打出统计行）"))
    if r.returncode != 0:
        bad.append((s, "退出码 %d" % r.returncode))

print()
if not bad:
    _save_stamp()
print("  %s" % ("全部通过 —— 可以交付" if not bad else "有 %d 项失败 —— 不许交付／不许进下一批" % len(bad)))
sys.exit(1 if bad else 0)
