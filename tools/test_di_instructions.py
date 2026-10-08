r"""di_instructions.py 的运行回归套件 —— 补 check_all 的盲区

用法:  tone.bat run test_di_instructions.py
退出码: 0 = 全过；1 = 有失败

为什么要有它（两次真实事故）:
  · 批 1.5：插了 4 行、多 4 个空格 -> SyntaxError。当时没跑 py_compile（现在 check_all 有了）。
  · 批 2：删死代码时把还在用的 _rq / _score 一起删了 -> 凡是 spec.json 没有 key_mode 的歌
    （**仓库里唯一那首真歌就是**）全部 exit 1 NameError。编译全过、套件全过、RC=0。
  **教训：编译通过 != 能跑。每个工具至少要有一条"真跑一遍"的门。**
"""
import sys, os, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
import tempfile
TMPBASE = os.path.join(os.path.dirname(ROOT), "_tmp_param")


TMPBASE = os.path.join(os.path.dirname(ROOT), "_tmp_param", "di_gate")


def mk(name, spec):
    """写一个夹具 spec。★ 不用 mkdtemp：本机沙箱下【子进程自己新建的目录写不进去】
    （实测 PermissionError），固定目录由外层建好后子进程能写。
    不可写时抛出【看得见的原因】，而不是让整个门以「没打出统计行」的形态失败。"""
    d = os.path.join(TMPBASE, name)
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "spec.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=2)
    except Exception as e:
        raise RuntimeError("临时目录不可写：%s（%s）—— 这个门需要包外可写的临时目录" % (d, e))
    return d

def run(song_dir):
    env = dict(os.environ, SONG_DIR=song_dir, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, os.path.join(HERE, "di_instructions.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# 四套调弦的空弦 MIDI（必须和 di_instructions.py 的 TUNINGS 一致；用错了就会误报"计划不自洽")
TUNINGS = {
    "standard":  {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64},
    "drop_d":    {6: 38, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64},
    "half_down": {6: 39, 5: 44, 4: 49, 3: 54, 2: 58, 1: 63},
    "drop_c":    {6: 36, 5: 43, 4: 48, 3: 53, 2: 57, 1: 62},
}
OPEN = TUNINGS["standard"]


def check_plan(song_dir, out):
    """★ 审计的变异测试证明：只断言"跑得完"抓不到三件事 ——
    所有和弦印成同一个按法 / 完全不写 di_plan / 丢 BOM。这里补上最便宜的三条断言。"""
    bad = []
    sp = os.path.join(song_dir, "spec.json")
    spec = json.load(open(sp, encoding="utf-8-sig"))
    plan = spec.get("di_plan")
    if not plan:
        return ["spec.json 里没有 di_plan"]
    OPEN = TUNINGS.get(plan.get("tuning"), None)     # ★ 必须按【这首歌的调弦】验，否则误报
    if OPEN is None:
        return ["di_plan 的 tuning=%r 不在门认识的调弦里" % plan.get("tuning")]
    for ch in plan.get("chords", []):
        pcs = set((OPEN[int(s["string"])] + int(s["fret"])) % 12 for s in ch["shape"])
        if set(ch["played_pcs"]) != pcs:
            bad.append("%s 的 played_pcs 与 shape 实算不符" % ch["label"])
        if "root_midi" in ch and min(OPEN[int(s["string"])] + int(s["fret"]) for s in ch["shape"]) % 12 != ch["root_pc"]:
            bad.append("%s 的低音不是根音" % ch["label"])
    # ★ 屏幕上的按法必须和计划里的【逐条对上】—— 审计的变异测试证明：
    #   把"所有和弦都印成同一个按法"注入进去时，只断言"跑得完"的门仍然全绿。
    for ch in plan.get("chords", []):
        for sh in ch["shape"]:
            st, fr = int(sh["string"]), int(sh["fret"])
            want = ("（第 %d 弦）第 %d 品" % (st, fr)) if fr > 0 else ("（第 %d 弦），什么都不按" % st)
            if want not in out:
                bad.append("%s 的按法 %s 没出现在屏幕上（屏幕和计划不一致）" % (ch["label"], want))
                break
    segs = plan.get("segments") or []
    if not segs:
        bad.append("di_plan 没有 segments")
    else:
        # 段数与秒数要和屏幕上的对得上
        for sgs in segs:
            if ("约 %.0f 秒" % sgs["seconds"]) not in out:
                bad.append("段「%s」的秒数 %s 没出现在屏幕上" % (sgs["kind"], sgs["seconds"]))
    return bad


BASE = {"key": "A", "chords": ["Am", "F", "C", "G"], "tuning": "standard",
        "technique": {"palm": 60, "mid": 30, "open": 10}}

CASES = [
    # (夹具名, spec, 期望退出码, 输出里必须有的串)
    ("no_key_mode", BASE, 0, ["[和弦]", "第 1 段", "自然小调"]),
    ("no_key_mode_noinfer", dict(BASE, key_mode="min"), 0, ["[和弦]"]),
    # ★ 有 key_mode 时【不该】再去推断调式（旧判据只断言两个套话串，等于没判）
    ("with_key_mode", dict(BASE, key_mode="min"), 0, ["[和弦]", "第 1 段"]),
    ("x5_only", dict(BASE, chords=["A5", "E5"]), 0, ["全是强力和弦", "自然小调"]),
    ("bad_chord", dict(BASE, chords=["Am", "Q7"]), 2, ["认不出来"]),
    ("empty_chords", dict(BASE, chords=[]), 2, ["没有和弦表"]),
    ("degraded", dict(BASE, chords=["C", "Cdim", "G7"], genre="clean"), 0,
     ["弹不出精确音高", "dim 和弦"]),
    ("flat_chord", dict(BASE, chords=["Bb5", "E5"]), 0, ["第 1 段"]),   # 按法/音高交给 check_plan 判
    ("dropc", dict(BASE, tuning="drop_c", chords=["E5", "G5"]), 0, ["[和弦]"]),
    # 反例 3：形状合法但音名全认不出来 -> 必须【跳过】，不许编出"每条都不在"的假验证
    ("roots_garbage", dict(BASE, chords_known={"roots": ["H", "Zz"]}), 0, ["一个音名都没认出来", "本项校验跳过"]),
    # T3①：空列表的形状是对的，话术不许说"形状不认识"
    ("roots_empty", dict(BASE, chords_known={"roots": []}), 0, ["是空的"]),
    # T3②：双升/双降 pc_of 明确支持，校验器不许比解析器更严
    # 和弦表选成用户材料覆盖得到的，这样"与推断表一致"才能证明【四个音名都解析出来了】
    # （若被正则拒掉，会走"一个音名都没认出来 -> 跳过"，这行就不会出现）
    # ★ 用【正确拼法 G##】(=A) 而不是 x —— 之前那条绿灯正是靠 Gx 被误读成 G 才通过的（假证据）
    # ── AC6：P4-B（贝斯参考 vs 本次音阶/和弦表）四态 ──────────────────
    #   ① 冲突且证据 ok -> 必须报；② 一致 -> 必须带「不构成独立证据」，不许写「验证通过」；
    #   ③ 缺字段 -> 跳过且说「不当成通过」；④ weak + 冲突素材 -> **必须不报冲突**（尊重生产者的 status）
    ("bass_conflict", dict(BASE, key="E", key_mode="min",
                           bass_ref={"top_pc": "C#", "top_pc_pct": 55.0, "clamped_frames": 0,
                                     "screen": {"status": "ok", "reasons": []}}), 0,
     ["不在本次音阶里"], ["Traceback"]),
    # ★ 和弦表要用含 E 根音的（BASE 那份是 Am/F/C/G，E 不在根音里 -> 会走"注意…持续音"那条）
    ("bass_consistent", dict(BASE, key="E", key_mode="min", chords=["Em", "C", "G", "D"],
                             bass_ref={"top_pc": "E", "top_pc_pct": 55.0, "clamped_frames": 0,
                                       "screen": {"status": "ok", "reasons": []}}), 0,
     ["不构成独立证据"], ["验证通过"]),
    ("bass_missing", dict(BASE, key="E", key_mode="min"), 0, ["不当成通过"], []),
    ("bass_weak", dict(BASE, key="E", key_mode="min",
                       bass_ref={"top_pc": "C#", "top_pc_pct": 31.2, "clamped_frames": 25,
                                 "screen": {"status": "weak", "reasons": ["只占 31.2% < 40%"]}}), 0,
     ["本项不报冲突"], ["不在本次音阶里"]),
    # ★ 审计第 1 轮的三条反例（新代码里的 T2）各配一条门用例
    ("bass_bad_top_pc", dict(BASE, key="E", key_mode="min",
                             bass_ref={"top_pc": "H", "top_pc_pct": 55.0, "clamped_frames": 0,
                                       "screen": {"status": "ok", "reasons": []}}), 0,
     ["不是音名", "不当成通过"], ["不在本次音阶里"]),
    ("bass_empty_ref", dict(BASE, key="E", key_mode="min",
                            bass_ref={"top_pc": None, "top_pc_pct": 0.0, "clamped_frames": 0,
                                      "screen": {"status": "weak", "reasons": ["有效帧 0"]}}), 0,
     ["跑过了，但一个有效帧都没有"], ["先跑 bass_reference.py"]),
    ("bass_clamped_str", dict(BASE, key="E", key_mode="min",
                              bass_ref={"top_pc": "C#", "top_pc_pct": 55.0, "clamped_frames": "12 帧",
                                        "screen": {"status": "ok"}}), 0,
     ["参考证据不足"], ["Traceback"]),    ("roots_double_acc", dict(BASE, chords=["Am", "F", "E", "D"],
                              chords_known={"roots": ["C##", "Bbb", "G##", "E", "F", "A"]}), 0,
     ["与推断表一致"]),
]


EXTRA = [
    # (名字, 额外参数, 期望退出码, 输出必须有的串)
    ("volume_15", ["--set-volume=15"], 2, ["超出范围"]),
    ("volume_abc", ["--set-volume=abc"], 2, ["要一个数"]),
    ("volume_7", ["--set-volume=7"], 0, ["已记"]),
]


def check_extra():
    """命令行参数的正/负用例（反例 2：范围必须真的生效）"""
    rows = []
    for name, extra, want_rc, must in EXTRA:
        try:
            d = mk(name, dict(BASE))
        except RuntimeError as e:
            rows.append((False, name, str(e))); continue
        env = dict(os.environ, SONG_DIR=d, PYTHONIOENCODING="utf-8")
        p = subprocess.run([PY, os.path.join(HERE, "di_instructions.py")] + extra,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        out = (p.stdout or "") + (p.stderr or "")
        why = ""
        if p.returncode != want_rc:
            why = "退出码 %d（期望 %d）" % (p.returncode, want_rc)
        else:
            miss = [m for m in must if m not in out]
            bad = []           # check_extra 的命令行用例没有 mustnot 这一栏
            if miss or bad:
                why = ("缺: " + " / ".join(miss) if miss else "") + ("  不该有: " + " / ".join(bad) if bad else "")
        rows.append((not why, name, why or "exit %d，话术对" % p.returncode))
    return rows


def main():
    rows = []
    for name, spec, want_rc, needles, *rest in CASES:
        mustnot = rest[0] if rest else []
        try:
            d = mk(name, spec)
        except RuntimeError as e:
            rows.append((False, name, str(e)))
            continue
        out, rc = run(d)
        ok = (rc == want_rc) and all(n in out for n in needles)
        why = ""
        if rc != want_rc:
            why = "退出码 %d（期望 %d）" % (rc, want_rc)
        else:
            miss = [n for n in needles if n not in out]
            bad = [n for n in mustnot if n in out]
            if miss:
                why = "缺: " + " / ".join(miss)
        if ok and want_rc == 0:
            pb = check_plan(d, out)
            if pb:
                ok, why = False, "di_plan 自洽性: " + " / ".join(pb[:3])
        rows.append((ok, name, why or ("exit %d，输出与 di_plan 都自洽" % rc)))
    # 真歌的 spec（仓库里唯一那首）—— 它的形态正是"没有 key_mode"
    real = os.path.join(ROOT, "songs", "BlackShout", "spec.json")
    if os.path.exists(real):
        d = mk("real_blackshout", json.load(open(real, encoding="utf-8-sig")))
        out, rc = run(d)
        rows.append((rc == 0 and "第 1 段" in out, "BlackShout（真歌 spec 拷贝）",
                     "exit %d" % rc if rc != 0 else "exit 0"))
    else:
        rows.append((False, "BlackShout（真歌 spec）", "找不到 " + real))
    print("=" * 72)
    print("  di_instructions 运行回归")
    print("=" * 72)
    bad = 0
    for ok, name, detail in rows:
        if not ok:
            bad += 1
        print("  %-4s %-26s %s" % ("PASS" if ok else "FAIL", name, detail))
    print()
    ex = check_extra()
    for ok, name, detail in ex:
        if not ok: bad += 1
        print("  %-4s %-26s %s" % ("PASS" if ok else "FAIL", name, detail))
    rows = rows + ex
    print()
    print("  %d 条：%d 通过 / %d 失败" % (len(rows), len(rows) - bad, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
