r"""调弦链的固定回归套件 —— 改过 songlib.f0_track / check_tuning.py 之后跑它

用法:  tone.bat run test_tuning.py            （或 & venv\Scripts\python.exe tools\test_tuning.py）
      tone.bat run test_tuning.py --slow     连真歌 BlackShout 一起跑（约 2 分钟）

产物: 一行一个 PASS/FAIL + 退出码（0 = 全过，1 = 有失败）

为什么要有它
    这四轮里最严重的一次回归（开放 C 和弦从 C3 100% 变成 G2 60%）是"修上一轮反例"修出来的，
    而当时没有任何东西能当场抓住它 —— 只能等下一轮审计（那要几十分钟，还得重新读包）。
    这个套件把【已经知道的期望】写死：改坏了当场就知道。
    ★ 它只覆盖已知项；未知项仍然靠独立审计（每条链一个子代理，见 skill）。

判据纪律
    · 期望值必须能在【当前代码】上复现（写进来之前先跑一遍）；
    · 复音（三和弦）的 f0 有原理性歧义（次谐波 vs 弱基频不可分），所以只记录、不判 ——
      见下面 expect=None 的几条。
"""
import sys, os, re, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import f0_track, utf8_stdout

utf8_stdout()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
def nm(m): return "%s%d" % (NAMES[m % 12], m//12 - 1)

SR = 44100
def pluck(freqs, dur=4.0, amp=0.3, nh=8, seed=0):
    """拨弦感：每个音 1/n 谐波 + 指数衰减（与审计员用的构造同族）"""
    n = int(dur*SR); t = np.arange(n)/SR; y = np.zeros(n)
    for f in freqs:
        for h in range(1, nh+1):
            y += (amp/h)*np.sin(2*np.pi*f*h*t + seed*0.7*h)*np.exp(-t*(1.2 + 0.25*h))
    return y.astype(np.float32)
def noise(dur=4.0, seed=1, amp=0.1):
    return (np.random.RandomState(seed).randn(int(dur*SR))*amp).astype(np.float32)
def hum(dur=4.0, f=50.0, amp=0.3):
    return (amp*np.sin(2*np.pi*f*np.arange(int(dur*SR))/SR)).astype(np.float32)
def bandnoise(dur=4.0, lo=25, hi=60, amp=0.15, seed=1):
    n = int(dur*SR); w = np.random.RandomState(seed).randn(n)
    W = np.fft.rfft(w); fr = np.fft.rfftfreq(n, 1/SR); W[(fr < lo) | (fr > hi)] = 0
    return (np.fft.irfft(W, n)*amp).astype(np.float32)

# (名字, 信号, 期望主音 or None=只记录, 最小帧数)
CASES = [
    ("D5 强力和弦 (D2+A2+D3)", pluck([73.42, 110.00, 146.83]), "D2", 100),
    ("E5 强力和弦 (E2+B2+E3)", pluck([82.41, 123.47, 164.81]), "E2", 100),
    ("单音 D2",                pluck([73.42]),                 "D2", 100),
    ("单音 A4 (440Hz)",        pluck([440.0]),                 "A4", 100),
    ("5 弦贝斯低 B (30.87Hz)", pluck([30.87]),                 "B0", 100),
    ("F 大三和弦 (F3+A3+C4)",  pluck([174.61, 220.00, 261.63]), "F3", 100),
    # 下面两条是复音：期望"至少报出 X 帧"（f0 歧义不判音名）—— 用 minn=1 标记这一类
    ("开放 G 和弦 (320003)",   pluck([98.00, 123.47, 146.83, 196.00, 246.94]), None, 1),
    ("开放 C 和弦",            pluck([130.81, 164.81, 196.00, 261.63, 329.63]), None, 1),
    ("白噪声",                 noise(),                        None, 0),
    ("50 Hz 工频",             hum(),                          None, 0),
    ("25-60 Hz 带限噪声",      bandnoise(),                    None, 0),
]
NOISE_MAX = 20      # "没有音"类用例允许漏进多少帧（它是筛子不是判据）

def synth_check():
    rows = []
    for label, y, expect, minn in CASES:
        t, m = f0_track(y, SR, fmin=25.0, fmax=1200.0,
                        min_playable_hz=(23.0 if "贝斯" in label else 63.0))
        if len(m) == 0:
            got, cnt = "（没有报出任何音）", 0
        else:
            v, c = np.unique(m, return_counts=True); i = int(np.argmax(c))
            got, cnt = nm(v[i]), int(c[i])
        if expect is None and minn == 0:          # "没有音"类
            # ★ 判【总帧数】而不是"最常见音的帧数"：10 个实例各漏 2 帧、分散在 10 个音名上，
            #   按最常见音判会 PASS（审计指出的 R6 形态）。
            ok = len(m) <= NOISE_MAX
            rows.append((ok, label, got, "总帧数 ≤ %d" % NOISE_MAX))
        elif expect is None:                      # 复音：只要求有输出，不判音名（歧义不可分）
            ok = len(m) > 0
            rows.append((ok, label, got, "至少报出一些帧（不判音名）"))
        else:
            ok = (got == expect) and (cnt >= minn)
            rows.append((ok, label, got, "%s 且 ≥ %d 帧" % (expect, minn)))
    return rows

FIXTURES = [
    ("tune_dropc",  ["只与 drop_c 相容", "否掉了"]),
    ("CT_half_down", ["否掉了", "并列 3 套"]),
    # ★ 判据要挑【只可能出现在结论里】的串：「C3」会出现在"低音区(≤C3)"那一行，分布怎么变都能过
    # 判据用【正则】：锁死整句措辞的话，谁改文案谁把测试改红（审计报了 5 次）
    ("prog_amin",   ["低音区检出的音高", r"主音[^\n]*C3"]),
    ("tune_std",    ["否掉了", "并列 2 套"]),
]
def fixture_check():
    rows = []
    # 审计材料在【包外】的兄弟目录（_audit_music\songs\），不在包内
    base = os.path.join(os.path.dirname(ROOT), "_audit_music", "songs")
    for name, needles in FIXTURES:
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            # ★ 夹具不在【不是跳过，是失败】：它属于验收的一部分，包一拷走就静默 SKIP 的话，
            #   这条套件会给出"全过"的假信号（审计实测：4 条全 SKIP 仍然 exit 0）。
            rows.append((False, name, "（夹具不在：%s）" % d, "必须有这个夹具")); continue
        p = subprocess.run([PY, os.path.join(HERE, "check_tuning.py"), d],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        miss = [n for n in needles if not re.search(n, out)]
        got = "OK" if not miss else "缺: " + " / ".join(miss)
        rows.append((not miss, name, got, " / ".join(needles)))
    return rows

def real_check():
    d = os.path.join(ROOT, "songs", "BlackShout")
    if not os.path.isdir(d):
        return [(None, "BlackShout", "（不在）", "跳过")]
    p = subprocess.run([PY, os.path.join(HERE, "check_tuning.py"), d],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    needles = ["低音带预检", "测不出调弦"]
    miss = [n for n in needles if n not in out]
    return [(not miss, "BlackShout（真歌）", "OK" if not miss else "缺: " + " / ".join(miss),
             " / ".join(needles))]

def main(argv):
    slow = "--slow" in argv
    rows = synth_check() + fixture_check() + (real_check() if slow else [])
    print("=" * 74)
    print("  调弦链回归套件")
    print("=" * 74)
    bad = 0
    for ok, label, got, want in rows:
        tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        if ok is False: bad += 1
        print("  %-4s %-26s 实测 %-26s 期望 %s" % (tag, label, got, want))
    print()
    print("  %d 条：%d 通过 / %d 失败 / %d 跳过%s"
          % (len(rows), sum(1 for r in rows if r[0] is True), bad,
             sum(1 for r in rows if r[0] is None), "" if slow else "（真歌用例没跑，加 --slow）"))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
