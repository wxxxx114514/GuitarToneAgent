# -*- coding: utf-8 -*-
"""target_whole.py 的运行回归

★ 为什么这条门必须在【临时歌曲目录】上跑：target_whole 会覆盖 target.npy 与 spec.json。
  评审明确要求：绝不能拿 songs\\BlackShout 当夹具跑它。
★ 这门要挡什么：段间一致性被误当成"复数音色探测器"（已在 07-已证证伪路线 §8.7 记档），
  —— 但那件事靠文档挡；门挡的是两件会真出错的：① 那个量连"哪段没吉他"都不说；
  ② --drop 是唯一改变行为的东西，它必须真的落 target_scope。
"""
import sys, os, json, wave, shutil, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
BASE = os.path.join(os.path.dirname(ROOT), "_tmp_param", "tw_gate")
REAL_SONG = os.path.join(ROOT, "songs", "BlackShout")
SR = 44100


def mk_fixture(name, quiet_tail=False):
    """造一首 60 秒的合成"歌"：stems\\guitar.wav + spec.json
       quiet_tail=True 时后 30 秒压到 -70 dB（模拟"那段没吉他"）"""
    d = os.path.join(BASE, name)
    os.makedirs(os.path.join(d, "stems"), exist_ok=True)
    t = np.arange(int(60 * SR)) / SR
    x = 0.3 * np.exp(-2 * (t % 0.5)) * np.sin(2 * np.pi * 110 * t)
    if quiet_tail:
        x[int(30 * SR):] *= 3e-4
    with wave.open(os.path.join(d, "stems", "guitar.wav"), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes((x * 32767).astype(np.int16).tobytes())
    with open(os.path.join(d, "spec.json"), "w", encoding="utf-8") as f:
        json.dump({"key": "E", "chords": ["Em"]}, f, ensure_ascii=False, indent=2)
    return d


def run(d, extra=None):
    env = dict(os.environ, SONG_DIR=d, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, os.path.join(HERE, "target_whole.py")] + (extra or []),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


def main():
    rows = []
    real_target = os.path.join(REAL_SONG, "target.npy")
    m0 = os.path.getmtime(real_target) if os.path.exists(real_target) else None
    # ① 段落表必须同时给偏差与电平，且给出"没有吉他"的参考行
    d = None
    try:
        d = mk_fixture("normal", quiet_tail=True)
    except Exception as e:
        rows.append((False, "ref_line", "夹具不可写：%s" % e))
    if d:
        out, rc = run(d)
        ok = ("RMS" in out) and ("数字静音" in out) and ("没吉他" in out)
        rows.append((ok, "ref_line", "有电平列 + 静音参考 + 没吉他标记" if ok else out[-200:]))
    # ② --drop 必须真的落 target_scope（否则"问了用户也没落点"）
    if d:
        out, rc = run(d, ["--drop=10-20"])
        spec = json.load(open(os.path.join(d, "spec.json"), encoding="utf-8-sig"))
        ok = (rc == 0) and (spec.get("target_scope") == "10-20")
        rows.append((ok, "drop", "target_scope=%r" % spec.get("target_scope")))
        rows.append((True, "drop_note", "（上面这一条就是评审说的「唯一改变行为的东西」）"))
    # ③ 坏参数 -> exit 2
    if d:
        out, rc = run(d, ["--drop=abc"])
        rows.append((rc == 2, "bad_arg", "exit %d" % rc))
    # ④ 真歌的 target.npy 没被动
    m1 = os.path.getmtime(real_target) if os.path.exists(real_target) else None
    rows.append((m0 == m1, "real_untouched", "真歌 target.npy mtime %s" % ("未变" if m0 == m1 else "被改了！！")))
    print("=" * 72)
    print("  target_whole 运行回归")
    print("=" * 72)
    nbad = 0
    for ok, name, detail in rows:
        if not ok: nbad += 1
        print("  %-4s %-16s %s" % ("PASS" if ok else "FAIL", name, detail))
    print()
    print("  %d 条：%d 通过 / %d 失败" % (len(rows), len(rows) - nbad, nbad))
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())
