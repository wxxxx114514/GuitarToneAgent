r"""verify_di.py 的运行回归 —— 补 check_all 的最后一个盲区

用法:  tone.bat run test_verify_di.py
退出码: 0 = 全过；1 = 有失败

为什么要有它（一次真实事故）:
  technique 的契约从 palm_pct/mid_pct/open_pct 换成 technique.pct 之后，
  verify_di.py 还在读旧字段名 -> 读到 0 -> 打印「spec.json 里没有奏法占比」（假话）、
  静默关掉奏法自参照、退出码仍是 0。check_all 里四个套件没有 verify_di 的门，所以一路绿。
  —— 这正是本项目自己那条「每个工具至少要有一条【真跑一遍】的门」漏在 verify_di 上。
"""
import sys, os, json, wave, subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
BASE = os.path.join(os.path.dirname(ROOT), "_tmp_param", "vd_gate")
SR = 44100


def write_di(path, right_zero=False, alt_silent=False, total_s=None, quiet=False):
    """合成一段 22 秒的 DI：两段快衰减（闷音） + 两段慢衰减（开放），段间 1.2 秒静音"""
    segs = []
    for decay, rep in ((14.0, 4), (1.5, 4)):
        for _ in range(rep):
            t = np.arange(int(0.5 * SR)) / SR
            # quiet=True：极轻（RMS 会低于 -50 dBFS -> 触发 verify_di 的低电平分支）
            amp = 0.0006 if quiet else 0.3
            segs.append(amp * np.exp(-decay * t) * np.sin(2 * np.pi * 110 * t))
        segs.append(np.zeros(int(1.2 * SR)))
    x = np.concatenate(segs)
    if total_s is not None:                      # 需要更长时把花纹铺满
        reps = int(np.ceil(total_s * SR / len(x)))
        x = np.tile(x, reps)[:int(total_s * SR)]
    with wave.open(str(path), "wb") as f:
        if alt_silent:      # ★ 反例 3：每个 20 秒段都有一侧是静音（前半只有 L、后半只有 R）
            #   注意：两侧都要先放内容，再各自抹掉一半 —— 我第一版把第二声道初始化成 0，
            #   于是 alt_silent 成了空操作（门用例因此失败）。
            # ★ 静音边界必须和 channel_check 的 20 秒分段【网格对齐】，否则每段两边都还有内容，
            #   场景根本复现不出来（我第一版把边界放在中点 22.5 秒，就是这么失败的）。
            #   60 秒 = 三段：段 0 只有 L、段 1 只有 R、段 2 只有 L。
            f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
            st = np.stack([x.copy(), x.copy()], 1)
            A = int(20 * SR)
            st[A:2 * A, 0] = 0.0        # 段 1：L 静音
            st[:A, 1] = 0.0             # 段 0：R 静音
            st[2 * A:, 1] = 0.0         # 段 2：R 静音
            f.writeframes((st * 32767).astype(np.int16).tobytes())
        elif right_zero:    # ★ 反例 1：单声道 DI 导出成"立体声"、右声道全 0
            f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
            st = np.stack([x, np.zeros_like(x)], 1)
            f.writeframes((st * 32767).astype(np.int16).tobytes())
        else:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
            f.writeframes((x * 32767).astype(np.int16).tobytes())


def mk(name, spec, right_zero=False, alt_silent=False, total_s=None, quiet=False):
    d = os.path.join(BASE, name)
    try:
        os.makedirs(os.path.join(d, "di"), exist_ok=True)
        with open(os.path.join(d, "spec.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=2)
        write_di(os.path.join(d, "di", "palm_di.wav"), right_zero=right_zero, alt_silent=alt_silent,
                 total_s=total_s, quiet=quiet)
    except Exception as e:
        raise RuntimeError("临时目录不可写：%s（%s）" % (d, e))
    return d


def run(song_dir):
    env = dict(os.environ, SONG_DIR=song_dir, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, os.path.join(HERE, "verify_di.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


BASE_SPEC = {"key": "A", "chords": ["Am", "F", "C", "G"], "tuning": "standard"}

CASES = [
    # 新契约：必须【走到有数据的分支】，不许说「没有奏法占比」
    ("new_pct", dict(BASE_SPEC, technique={"pct": {"palm": 69.2, "mid": 30.8, "open": 0.0}},
                     technique_source="user"),
     None, ["69", "30"], ["没有奏法占比"]),
    # 旧格式：仍然要能跑（并标明是旧口径）
    ("legacy_pct", dict(BASE_SPEC, technique={"palm_pct": 60.0, "mid_pct": 30.0, "open_pct": 10.0}),
     None, ["60"], []),
    # 真的没有：这句才是对的
    # ★ 退出码不看：verify_di 在合成 DI 上报"问题"是正常结果（它返回的是"有没有问题"，不是"跑没跑成功"）
    ("no_pct", dict(BASE_SPEC), None, ["没有奏法占比"], []),
    # 反例 1：一侧静音的"立体声"不许 traceback
    ("dead_channel", dict(BASE_SPEC, technique={"pct": {"palm": 60.0, "mid": 30.0, "open": 10.0}},
                                                technique_source="user"), None,
     # ★ 完整句 + 互斥：错误话术「（每段都有一侧是静音）」含有裸子串"有一侧是静音"，
     #   所以必须断言完整句、并且禁止另一条的整句（审计的变异测试证明裸子串抓不到回归）
     ["有一侧是静音 —— 按单声道处理"], ["一个可比的段都没有", "Traceback"]),
    # 反例 3：每段都有一侧静音 -> 一次可比测量都没有，不许拿哨兵值下"不止一个音源"
    ("no_segments", dict(BASE_SPEC), None, ["一个可比的段都没有"],
     ["按单声道处理", "不止一个音源", "Traceback"]),
    # ★ 成对互斥（审计：must 锚在【无条件标题行】上等于没断言）：
    #   有声明的必须念出来；坏值 / 缺字段的必须【不念】。
    ("good_volume_quiet", dict(BASE_SPEC, guitar_volume=7.0, guitar_volume_source="user"), None,
     ["你琴上的音量旋钮记的是 7.0"], ["Traceback"]),
    ("bad_volume", dict(BASE_SPEC, guitar_volume="7/10", guitar_volume_source="user"), None,
     [], ["Traceback", "你琴上的音量旋钮记的是"]),
    ("no_volume", dict(BASE_SPEC), None, [], ["Traceback", "你琴上的音量旋钮记的是"]),
]


def check_channel():
    """声道判据的【库级】用例（比走 verify_di 更精确，也更快）

    ★ 这两条是被真素材逼出来的：BlackShout 的 bass.wav 第 0 段 RMS = −111.1 dBFS，
      chroma 是在噪声上算的 -> 旧判据（无电平门、chroma 下限 0.99）把它判成「不止一个音源」，
      而逐段数据显示它 11/12 段比吉他轨更「同内容」。真凶是电平，不是乐器。
    """
    import soundfile as sf
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from songlib import channel_check
    rows = []

    def stereo(name, quiet_head, two_sources):
        d = os.path.join(BASE, name); os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "ch.wav")
        # ★ 必须用【拨弦序列】而不是单一衰减音：exp(-3t) 在 t=20 s 时已经是 1e-27，
        #   45 秒里只有头两秒有声 —— 我第一版就是这么做夹具的，"压低头 20 秒"实际把整轨压成了静音。
        step = int(0.5 * SR)
        tt = np.arange(step) / SR
        train = np.concatenate([0.3 * np.exp(-3 * tt) * np.sin(2 * np.pi * (110 if i % 2 == 0 else 165) * tt)
                                for i in range(int(45 / 0.5) + 1)])[:int(45 * SR)]
        a = train.copy()
        b = (0.3 * np.exp(-3 * tt)[0] * train * 0 + np.sin(2 * np.pi * 330 * tt).repeat(int(45 / 0.5) + 1)[:int(45 * SR)] * 0
             + train[::-1].copy()) if two_sources else train.copy()   # 两音源：R 用不同内容（倒放 + 不同音高）
        if two_sources:
            b = 0.3 * np.exp(-3 * tt).repeat(int(45 / 0.5) + 1)[:int(45 * SR)] * np.sin(2 * np.pi * 233 * tt).repeat(int(45 / 0.5) + 1)[:int(45 * SR)]
        if quiet_head:
            # ★ 必须是【非零的】极轻段（≈ −63 dBFS）才能测到电平门：
            #   我第一版用 1e-5 -> 3e-6×32767 = 0.098 -> int16 取整成【精确零】，
            #   于是走的是 std()<1e-9 那条老分支，电平门根本没被触发（门用例因此红着）。
            k = int(20 * SR)
            a[:k] *= 1e-3; b[:k] *= 1e-3
        st = np.stack([a, b], 1)
        with wave.open(p, "wb") as f:
            f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
            f.writeframes((st * 32767).astype(np.int16).tobytes())
        x, sr = sf.read(p, always_2d=True, dtype="float32")
        dec, ev = channel_check(x, sr)
        return dec, ev

    dec, ev = stereo("ch_quiet_head", True, False)
    ok = (dec == "mono") and ev.get("n_skipped_level", 0) >= 1
    rows.append((ok, "ch_quiet_head", "mono（跳过 %s 段低电平）" % ev.get("n_skipped_level")
                 if ok else "判成 %s（应为 mono）" % dec))
    dec2, ev2 = stereo("ch_two_sources", False, True)
    ok2 = (dec2 == "ask")
    rows.append((ok2, "ch_two_sources", "ask（余弦 %s / 包络 %s dB）" % (ev2.get("chroma_cos_min"), ev2.get("env_diff_rms_db"))
                 if ok2 else "判成 %s（应为 ask）" % dec2))
    return rows


def main():
    rows = []
    for name, spec, want_rc, must, mustnot in CASES:
        try:
            d = mk(name, spec, right_zero=(name == "dead_channel"), alt_silent=(name == "no_segments"),
                   total_s=(60.0 if name == "no_segments" else None),
                   quiet=(name == "good_volume_quiet"))
        except RuntimeError as e:
            rows.append((False, name, str(e)))
            continue
        out, rc = run(d)
        why = ""
        if want_rc is not None and rc != want_rc:
            why = "退出码 %d（期望 %d）" % (rc, want_rc)
        else:
            # ★ 判据锚在【[奏法] 那一行】上，不是整屏子串（T3④：否则别处出现同样的数字也算过）
            _lines = [l for l in out.splitlines() if "[奏法]" in l]
            _tech = " ".join(_lines) if _lines else ""
            miss = [m for m in must if (m not in _tech and m not in out)]
            bad = [m for m in mustnot if m in out]
            if miss or bad:
                why = ("缺: " + " / ".join(miss) if miss else "") + ("  不该有: " + " / ".join(bad) if bad else "")
        rows.append((not why, name, why or "exit %d，[奏法] 行的内容与判据一致" % rc))
    rows = rows + check_channel()   # ★ 声道判据的库级用例（电平门 / 真两音源）
    print("=" * 72)
    print("  verify_di 运行回归")
    print("=" * 72)
    nbad = 0
    for ok, name, detail in rows:
        if not ok: nbad += 1
        print("  %-4s %-14s %s" % ("PASS" if ok else "FAIL", name, detail))
    print()
    print("  %d 条：%d 通过 / %d 失败" % (len(rows), len(rows) - nbad, nbad))
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())
