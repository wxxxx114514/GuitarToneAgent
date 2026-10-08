# -*- coding: utf-8 -*-
"""bass_reference.py 的运行回归

用法:  tone.bat run test_bass_reference.py
退出码: 0 = 全过；1 = 有失败

★ 为什么必须有这个门（一次真实事故）：
  批 1 的审计报告写着「旧 bass_roots.py 的 fmin=35 问题确已修」，而那个文件里**至今是 35** ——
  它测的是 songlib.f0_track，结论被推广到了另一个文件。**每个工具至少一条"真跑一遍"的门**，
  否则"已修"只存在于报告里。
"""
import sys, os, re, json, wave, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
BASE = os.path.join(os.path.dirname(ROOT), "_tmp_param", "br_gate")
SR = 44100
OLD_KEYS = ["key_from_bass", "chords_from_bass", "bass_root_windows",
            "bass_weight_s", "warning", "tuning_evidence"]


def write_bass(path, notes, dur=16.0, detune=0.0):
    """合成贝斯音：基频 + 谐波（纯正弦 pyin 容易跟丢）。notes = MIDI 列表，轮流 1 秒一个"""
    t = np.arange(int(dur * SR)) / SR
    x = np.zeros_like(t)
    step = int(1.0 * SR)
    for i in range(int(dur)):
        m = notes[i % len(notes)]
        f = 440.0 * 2 ** ((m - 69) / 12.0) * (2 ** (detune / 1200.0))
        s = slice(i * step, min((i + 1) * step, len(t)))
        tt = t[s]
        x[s] = sum((1.0 / k) * np.sin(2 * np.pi * f * k * tt) for k in range(1, 9))
    x = 0.3 * x / max(np.abs(x).max(), 1e-9)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1); fh.setsampwidth(2); fh.setframerate(SR)
        fh.writeframes((x * 32767).astype(np.int16).tobytes())


def mk(name, notes, spec=None, detune=0.0):
    d = os.path.join(BASE, name)
    os.makedirs(os.path.join(d, "stems"), exist_ok=True)
    write_bass(os.path.join(d, "stems", "bass.wav"), notes, detune=detune)
    with open(os.path.join(d, "spec.json"), "w", encoding="utf-8") as fh:
        json.dump(spec or {"key": "E", "chords": ["Em", "C", "G", "D"]}, fh, ensure_ascii=False, indent=2)
    return d


def run(d):
    env = dict(os.environ, SONG_DIR=d, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, os.path.join(HERE, "bass_reference.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return (p.stdout or "") + (p.stderr or ""), p.returncode, json.load(open(os.path.join(d, "spec.json"), encoding="utf-8-sig"))


def main():
    rows = []
    # AC1：低音 A0 = 27.5 Hz（drop-A；fmin=35 时会钳位成 C# 99.9%）、B0 = 30.87、E1 = 41.2
    for name, midi, want in (("a0", 21, "A"), ("b0", 23, "B"), ("e1", 28, "E")):
        try:
            d = mk(name, [midi])
        except Exception as e:
            rows.append((False, name, "夹具不可写：%s" % e)); continue
        out, rc, spec = run(d)
        br = spec.get("bass_ref") or {}
        why = ""
        if br.get("top_pc") != want:
            why = "top_pc=%s（应为 %s）" % (br.get("top_pc"), want)
        elif midi in (21, 23) and int(br.get("clamped_frames") or 0) != 0:
            why = "钳位帧 %s（应为 0）" % br.get("clamped_frames")
        elif re.search(r"主音[ 　]*[A-G][#b]?", out) or "-> 主音" in out:
            # ★ 只禁【坏用法】（把 argmax 叫「主音 X」）；工具里那句免责说明本身会用这个词
            why = "屏幕把 argmax 叫成「主音 <音名>」"
        rows.append((not why, name, why or "top_pc=%s 钳位=%s，无「主音」字样" % (br.get("top_pc"), br.get("clamped_frames"))))
    # AC2：平坦分布 -> weak，且屏写数字一致
    d = None
    try:
        d = mk("flat", [28, 29, 33, 36])          # E F A C# 轮流
    except Exception as e:
        rows.append((False, "flat", str(e)))
    if d:
        out, rc, spec = run(d)
        br = spec.get("bass_ref") or {}
        scr = (br.get("screen") or {})
        shown = ("%.1f%%" % br.get("top_pc_pct", -1)) in out
        ok = (scr.get("status") == "weak") and ("证据强度：weak" in out) and shown
        rows.append((ok, "flat", "status=%s·屏上有该数字=%s" % (scr.get("status"), shown)))
    # ★ 审计反例 3：全零贝斯轨不许写出「最常出现的音级 C（占 0.0%）」
    d = None
    try:
        d = mk("silent", [28])
        import wave as _w
        with _w.open(os.path.join(d, "stems", "bass.wav"), "wb") as fh:   # 覆盖成全零
            fh.setnchannels(1); fh.setsampwidth(2); fh.setframerate(SR)
            fh.writeframes(b"\x00" * (SR * 2 * 4))
    except Exception as e:
        rows.append((False, "silent", str(e)))
    if d:
        out, rc, spec = run(d)
        br = spec.get("bass_ref") or {}
        ok = (br.get("top_pc") is None) and ("bass_note_pct" not in spec) and ("没有音级分布可报" in out)
        rows.append((ok, "silent", "top_pc=None 且不写 bass_note_pct" if ok
                     else "top_pc=%r / bass_note_pct=%s" % (br.get("top_pc"), "bass_note_pct" in spec)))
    # ★★ 端到端（生产者 -> 消费者）：键名一漂移（screen -> screening / status -> st），
    #    消费者会取到空 dict -> status=None -> 永远 weak、永远不报冲突，**而没有任何测试会红**。
    #    这条用例把两个工具接起来跑，断言传过去的是"有 status 的 ok 证据"。
    d = None
    try:
        d = mk("e2e", [28], spec={"key": "E", "key_mode": "min", "chords": ["Em", "C", "G", "D"]})
    except Exception as e:
        rows.append((False, "e2e", str(e)))
    if d:
        out1, rc1, spec = run(d)                       # 生产者
        br = spec.get("bass_ref") or {}
        env = dict(os.environ, SONG_DIR=d, PYTHONIOENCODING="utf-8")
        p = subprocess.run([PY, os.path.join(HERE, "di_instructions.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        out2 = (p.stdout or "") + (p.stderr or "")
        lines = [l for l in out2.splitlines() if "[贝斯]" in l]
        joined = " ".join(lines)
        # ★ 判据要锚在【消费者真的走了 ok 路径】上：ok 路径打的是"一致/不在音阶里"（含"不构成独立证据"），
        #   weak 路径打的是"参考证据不足（status=…）"。键名一漂移，status 变 None -> 走 weak -> 这里必红。
        ok = (br.get("screen", {}).get("status") == "ok"
              and "不构成独立证据" in joined
              and "证据不足" not in joined
              and "status=None" not in joined)
        rows.append((ok, "e2e", ("生产者 status=ok -> 消费者读到 ok：" + joined[:60]) if ok
                     else "生产者 status=%r / 消费者行=%r" % (br.get("screen", {}).get("status"), joined[:80])))
    # AC3：旧字段必须被 pop（含历史遗留那三个）
    seed = {"key": "E", "chords": ["Em"], "key_from_bass": "G", "chords_from_bass": ["F5", "G5"],
            "bass_root_windows": {"F": 2}, "bass_weight_s": {"B": 13.6},
            "warning": "bass/guitar key disagreement", "tuning_evidence": {"note": "建在物理不可能的音上"}}
    d = None
    try:
        d = mk("cleanup", [28], spec=seed)
    except Exception as e:
        rows.append((False, "cleanup", str(e)))
    if d:
        out, rc, spec = run(d)
        left = [k for k in OLD_KEYS if k in spec]
        rows.append((not left, "cleanup", "残留：%s" % left if left else "6 个旧键全部清掉"))
    print("=" * 72)
    print("  bass_reference 运行回归")
    print("=" * 72)
    nbad = 0
    for ok, name, detail in rows:
        if not ok: nbad += 1
        print("  %-4s %-10s %s" % ("PASS" if ok else "FAIL", name, detail))
    print()
    print("  %d 条：%d 通过 / %d 失败" % (len(rows), len(rows) - nbad, nbad))
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())
