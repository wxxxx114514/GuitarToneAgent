r"""指法引擎：给一组音级，算出【可弹、音高正确、整段移动最小】的按法

用法（库）:
    from fingering import parse_chord, chord_pcs, voicings, plan_sequence, scale_shapes
自测:
    tone.bat run fingering.py

设计要点（每条都有实测理由）:
  · 音高必须【精确】：出声的音级集合 == 和弦需要的集合。多一个音就是往频谱里加料，
    而 DI 的频谱是用来解 EQ 的（内容不匹配时 60% 的误差是假的）。低音必须是根音。
  · 六个可移动和弦型（E 型 / A 型 × 强力 / 大三 / 小三）【按音程构造】，不是硬编码品数 ——
    硬编码在 drop 调弦上就是错的：drop D 的强力和弦是 6/5/4 弦【同品】，
    实测硬编码版把 E5 顶到 5 弦 7 品（高一个八度），还把 6 弦整段浪费掉。
  · 整段用 DP 最小化【左手移动】（把位窗口中心之差），另加很小的低把位偏好。
  · 单音音阶：优先空弦，其次低把位、少换弦。
"""
import itertools

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
DEG = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

OPEN_STD = {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}

MAJ_DIA = [("maj", 0), ("min", 2), ("min", 4), ("maj", 5), ("maj", 7), ("min", 9), ("dim", 11)]
MIN_DIA = [("min", 0), ("dim", 2), ("maj", 3), ("min", 5), ("min", 7), ("maj", 8), ("maj", 10)]

# 支持的性质 -> 【按音程构造】的型：[(相对根音弦的弦号偏移, 相对根音品数的音程)]
QUAL_INTERVALS = {
    "pow": [(-1, 7), (-2, 12)],
    "maj": [(-1, 7), (-2, 12), (-3, 16)],
    "min": [(-1, 7), (-2, 12), (-3, 15)],
}
UNSUPPORTED_HINTS = ("7", "9", "11", "13", "6", "sus", "add", "alt", "/", "+",
                     "\u00f8", "\u00ba", "no3", "omit")


def pc_of(name):
    """音名（认升号/降号；双升 C## 也认）-> pitch class；认不出来返回 None"""
    if not isinstance(name, str) or not name.strip():
        return None
    s = name.strip()
    if s[0].upper() not in DEG:
        return None
    i = DEG[s[0].upper()]
    k = 1
    while k < len(s) and s[k] in "#b":
        i += 1 if s[k] == "#" else -1
        k += 1
    return i % 12


def _split(label):
    """和弦名 -> (根音字符串, 后缀)；认不出根音返回 (None, None)"""
    s = str(label).strip()
    if not s or s[0].upper() not in DEG:
        return None, None
    k = 1
    while k < len(s) and s[k] in "#b":
        k += 1
    return s[:k], s[k:]


def parse_chord(label, key_pc=None, mode="maj"):
    """和弦名 -> (根音 pc, 性质, 说明)

    性质【只从名字读】；只有名字里没有三度信息（后缀 "5"）时才用调式先验：
      · 后缀 ""  -> 大三（★ 没有后缀就是大三，不许被调式先验改成小三：
                     实测 key=A 小调 + chords=[A,D,E] 曾把 D 变成 Dm）
      · 后缀 "5" -> 没有三度信息 -> 先看调式音级；推不出来就当强力和弦
      · dim / aug / 7 / 9 / sus / add / 斜杠 … -> 我们弹不出精确音高，
        退回强力和弦**并说明**（不静默；说明文本会打到屏幕上）
    """
    root_s, body = _split(label)
    if root_s is None:
        return None, None, "认不出根音"        # ★ 必须返回三元组：调用方是 r, q, note = parse_chord(...)
    root = pc_of(root_s)
    if root is None:
        return None, None, "认不出根音"
    b = body.strip()
    blo = b.lower()
    if blo.startswith("dim") or "\u00ba" in blo or "\u00f8" in blo:
        return root, "pow", "dim 和弦没有可用的三音型 -> 按强力和弦弹（会缺 b3 与 b5）"
    if blo.startswith("aug") or blo.startswith("+"):
        return root, "pow", "aug 和弦没有可用的三音型 -> 按强力和弦弹（会缺 3 与 #5）"
    if any(h in blo for h in UNSUPPORTED_HINTS):
        return root, "pow", "后缀「%s」我们弹不出精确音高 -> 按强力和弦弹" % b
    if blo.startswith("maj") or b[:1] == "M":
        return root, "maj", ""                 # 含 "CM" 这种写法（大写 M = 大三）
    if blo.startswith("m"):
        return root, "min", ""
    if b == "":
        return root, "maj", ""
    if b == "5":
        # ★ 「5」就是【强力和弦】= 谱面已经告诉你不要三度，不许用调式先验补一个出来
        #   （实测 pop metal 的四个 X5 被补成 Em/G/Am/Bm）。要不要三度由曲风先验决定。
        return root, "pow", ""
    return root, "pow", "认不出的后缀（%s）-> 按强力和弦弹" % b


def chord_pcs(root_pc, qual):
    """和弦需要的音级集合（pow = 根音 + 五度）"""
    fifth = (root_pc + 7) % 12
    if qual == "maj":
        return {root_pc, (root_pc + 4) % 12, fifth}
    if qual == "min":
        return {root_pc, (root_pc + 3) % 12, fifth}
    return {root_pc, fifth}


def voicings(open_midi, root_pc, qual, max_fret=12):
    """该和弦、该调弦下所有可用的型 -> [(基准品, [(弦,品)...], (最低声位,最高声位), 根音弦)]

    型按【音程】构造，所以 drop 调弦自动正确（drop D 的强力和弦就是 6/5/4 同品）。
    """
    q = qual if qual in QUAL_INTERVALS else "pow"
    want = chord_pcs(root_pc, q)
    out = []
    for s0 in (6, 5):
        if s0 not in open_midi:
            continue
        base_open = open_midi[s0]
        for octv in (-12, 0, 12, 24):
            n = (36 + root_pc + octv) - base_open
            if n < 0 or n > max_fret:
                continue
            shape, ok = [(s0, n)], True
            for ds, iv in QUAL_INTERVALS[q]:
                s = s0 + ds
                if s not in open_midi:
                    ok = False; break
                f = n + iv - (open_midi[s] - base_open)
                if f < 0 or f > max_fret:
                    ok = False; break
                shape.append((s, f))
            if not ok:
                continue
            shape = sorted(shape, key=lambda z: -z[0])
            if set((open_midi[s] + f) % 12 for s, f in shape) != want:
                continue
            if min(open_midi[s] + f for s, f in shape) % 12 != root_pc:
                continue
            fr = [f for _, f in shape if f > 0]
            pos = (min(fr), max(fr)) if fr else (0, 0)
            out.append((n, shape, pos, s0))
    seen, uniq = set(), []
    for n, shape, pos, s0 in sorted(out, key=lambda z: (z[2], z[0])):
        k = tuple(shape)
        if k in seen:
            continue
        seen.add(k)
        uniq.append((n, shape, pos, s0))
    return uniq


def _ctr(pos):
    return (pos[0] + pos[1]) / 2.0


def _oct_of(v, r, open_midi):
    """这个按法的根音比基准八度（36+pc）高几个八度"""
    return (open_midi[v[3]] + v[0] - (36 + r)) / 12.0


def _lowest_octave(vs, r, open_midi):
    """★ 音区【硬约束】：只留最低可用八度的候选，再在这些候选里做最小移动。
    数据（drop D 8 和弦池、1536 个位置）：软权重 4.0 时仍有 2.2% 被放到"低八度确实存在"的高八度；
    硬约束把它清成 0%，代价是平均移动 +0.44 品、单步最大值不变（都是 6.0 品）。
    ★ 剩下的（Eb/Ab 这类低八度在 6 弦空弦以下）任何策略都修不了 —— 只能记档。"""
    if not vs:
        return vs
    lo = min(_oct_of(v, r, open_midi) for v in vs)
    return [v for v in vs if _oct_of(v, r, open_midi) == lo] or vs


def plan_sequence(chords, open_midi, max_fret=12, low_bias=0.001, want_third=True):
    """整段【左手移动最小】的按法（DP）。chords = [(标签, root_pc, 性质)]

    代价 = Σ|把位窗口中心之差| + low_bias×Σ把位
    ★ low_bias 必须小到【只破平手】（1e-3）：最小移动差是 0.5 品，低把位项最多贡献约 0.05 ——
      这样 DP 严格最小移动（旧值 0.12 会挑「低 2 品但多走 1 品」的解，实测 31% 的序列不是最小）。
    ★ 不设"换弦组"惩罚：六个型都含 4、5 弦，那个惩罚恒不触发（旧代码里就是死项）。
    """
    # want_third=False（金属/失真曲风）-> 一律强力和弦：谱面是三和弦也弹成强力和弦
    eff = [(lab, r, (q if want_third else "pow")) for lab, r, q in chords]
    cand = [(lab, r, q, _lowest_octave(voicings(open_midi, r, q, max_fret), r, open_midi))
            for lab, r, q in eff]

    def _oct_pen(r, v):
        """音区惩罚：根音比基准八度（36+pc）每高一个八度算 4.0 品。
        ★ 为什么是 4.0：实测 1.5 时 drop 调弦下 9.2% 的三和弦序列会被挑到高八度
          （省 4 品移动 > 牺牲 2 个八度）—— 音区错是【内容错】，移动量只是便利性，必须压过去。
        ★ 为什么必须有：只看把位中心时，E5 会被选到 5 弦 7 品 —— 音级对，但【高一个八度】，
          而 DI 的频谱要和参考曲的节奏吉他同一个音区才有意义。"""
        s0 = v[3]
        return 4.0 * ((open_midi[s0] + v[0] - (36 + r)) / 12.0)
    best = {}
    for j, (lab, r, q, vs) in enumerate(cand):
        cur = {}
        for vi, (n, shape, pos, s0) in enumerate(vs):
            pen = low_bias * _ctr(pos) + _oct_pen(r, vs[vi])
            if j == 0 or not best.get(j - 1):
                cur[vi] = (pen, None)
            else:
                opt = None
                for vj, (cost, _) in best[j - 1].items():
                    c = cost + abs(_ctr(pos) - _ctr(cand[j - 1][3][vj][2])) + pen
                    if opt is None or c < opt[0]:
                        opt = (c, vj)
                cur[vi] = opt
        best[j] = cur or None
    picks = [None] * len(cand)
    if cand and best.get(len(cand) - 1):
        last = best[len(cand) - 1]
        vi = min(last, key=lambda k: last[k][0])
        for j in range(len(cand) - 1, -1, -1):
            picks[j] = vi
            vi = best[j][vi][1]
    out = []
    for j, (lab, r, q, vs) in enumerate(cand):
        v = vs[picks[j]] if (vs and picks[j] is not None) else None
        out.append((lab, r, q, (v[0], v[1], v[2], v[3]) if v else None, len(vs)))
    return out


def minimal_movement(chords, open_midi, max_fret=12, want_third=True):
    """暴力最优（目标 = 移动 + 音区项），只给自测对拍用：候选少时才跑得动

    ★ 口径必须和 plan_sequence 一致（含音区项）——审计员提醒过：拿另一套候选/口径比 DP，
      会把"目标不同"误报成"DP 不是最优"。
    """
    eff = [(lab, r, (q if want_third else "pow")) for lab, r, q in chords]
    cand = [_lowest_octave(voicings(open_midi, r, q, max_fret), r, open_midi) for _, r, q in eff]
    if any(not c for c in cand):
        return None
    best = None
    for combo in itertools.product(*cand):
        mv = sum(abs(_ctr(combo[i][2]) - _ctr(combo[i - 1][2])) for i in range(1, len(combo)))
        octp = sum(4.0 * ((open_midi[c[3]] + c[0] - (36 + eff[i][1])) / 12.0)
                   for i, c in enumerate(combo))
        tot = mv + octp
        if best is None or tot < best:
            best = tot
    return best


def scale_shapes(notes, open_midi, max_fret=12):
    """单音音阶的按法：优先空弦，其次低把位、少换弦

    ★ 旧版没有低把位项，平手时 min() 取字典序第一根（最粗）弦 ——
      实测 24 条音阶里 18 条一个空弦都没有、全部到 ≥10 品（C 小调首音被放到 6 弦 8 品）。
    """
    out, prev = [], None
    for m in notes:
        opts = [(s, m - o) for s, o in open_midi.items() if 0 <= m - o <= max_fret]
        if not opts:
            out.append(None); prev = None; continue
        def cost(sf):
            s, f = sf
            c = 0.5 * f
            if f == 0:
                c -= 2.0
            if prev is not None:
                ps, pf = prev
                c += abs(f - pf) * 0.5
                if s != ps:
                    c += 0.8
            return c
        pick = min(opts, key=cost)
        out.append(pick); prev = pick
    return out


def selftest():
    """自测：音高精确性（按【明确的性质】逐个验，不许拿强力和弦冒充）+ 对拍最小移动量"""
    bad, n = [], 0
    cases = [("A", "maj", {9, 1, 4}), ("Am", "min", {9, 0, 4}), ("C", "maj", {0, 4, 7}),
             ("Cm", "min", {0, 3, 7}), ("F", "maj", {5, 9, 0}), ("Fm", "min", {5, 8, 0}),
             ("G", "maj", {7, 11, 2}), ("E", "maj", {4, 8, 11}), ("D", "maj", {2, 6, 9}),
             ("A5", "pow", {9, 4}), ("E5", "pow", {4, 11}), ("Bb5", "pow", {10, 5})]
    print("=" * 78)
    print("  指法引擎自测")
    print("=" * 78)
    for lab, want_q, want_pcs in cases:
        r, q, note = parse_chord(lab, key_pc=9, mode="min")
        n += 1
        if r is None:
            bad.append("%s 解析失败" % lab); continue
        if q != want_q:
            bad.append("%s 性质解析成 %s，应是 %s" % (lab, q, want_q)); continue
        vs = voicings(OPEN_STD, r, q)
        if not vs:
            bad.append("%s 找不到按法" % lab); continue
        got = set((OPEN_STD[s] + f) % 12 for s, f in vs[0][1])
        if got != want_pcs:
            bad.append("%s 出声音级 %s != 需要 %s" % (lab, sorted(got), sorted(want_pcs)))
        if min(OPEN_STD[s] + f for s, f in vs[0][1]) % 12 != r:
            bad.append("%s 低音不是根音" % lab)
    for lab, want in [("A", "maj"), ("D", "maj"), ("E", "maj"), ("Am", "min")]:
        r, q, _ = parse_chord(lab, key_pc=9, mode="min")
        n += 1
        if q != want:
            bad.append("无后缀解析：%s -> %s（应 %s）" % (lab, q, want))
    # N1 回归锁：认不出根音也必须返回三元组（旧版返回裸 None -> 调用方解包崩，exit 2 永远到不了）
    n += 1
    for bad_lab in ("Q7", "N.C.", "", "?", "3", None):
        p = parse_chord(bad_lab)
        if not (isinstance(p, tuple) and len(p) == 3):
            bad.append("parse_chord(%r) 没返回三元组：%r" % (bad_lab, p))
    # N3 回归锁：drop D 下 E5/D5/G5 必须落在低八度（6 弦）
    n += 1
    dropd = {6: 38, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64}
    ch3 = []
    for lab in ("E5", "D5", "G5"):
        _r, _q, _n = parse_chord(lab)
        ch3.append((lab, _r, _q))
    sq = plan_sequence(ch3, dropd)
    if any(v[3] is None for v in sq) or any(v[3][3] != 6 for v in sq):
        bad.append("drop D 的 E5/D5/G5 没落在 6 弦族（N3 回归）：%s" % [v[3][3] if v[3] else None for v in sq])
    dropc = {6: 36, 5: 43, 4: 48, 3: 53, 2: 57, 1: 62}
    n += 1
    vs = voicings(dropc, 4, "pow")
    if not vs or not any(set(s for s, _ in v[1]) >= {6, 5, 4} and len(set(f for _, f in v[1])) == 1 for v in vs):
        bad.append("drop C 的 E5 没有 6/5/4 同品的按法（回归）")
    for tag, labs, mode, key in [("Am-F-C-G", ["Am", "F", "C", "G"], "min", 9),
                                 ("E5-C5-G5-D5", ["E5", "C5", "G5", "D5"], "min", 9),
                                 ("C-G-Am-F", ["C", "G", "Am", "F"], "maj", 0)]:
        ch = []
        for l in labs:
            r, q, _ = parse_chord(l, key_pc=key, mode=mode)
            ch.append((l, r, q))
        seq = plan_sequence(ch, OPEN_STD)
        n += 1
        if any(v[3] is None for v in seq):
            bad.append("%s 有和弦推不出按法" % tag); continue
        mv = sum(abs(_ctr(seq[i][3][2]) - _ctr(seq[i - 1][3][2])) for i in range(1, len(seq)))
        octp = sum(4.0 * ((OPEN_STD[v[3][3]] + v[3][0] - (36 + v[1])) / 12.0) for v in seq)
        mm = minimal_movement(ch, OPEN_STD)
        flag = ""
        if mm is None or abs((mv + octp) - mm) > 1e-9:
            flag = "  ← 与暴力最优不一致！（暴力给 %.3f，我 %.3f）" % (mm, mv + octp)
            bad.append("%s 目标值 %.3f != 暴力最优 %.3f" % (tag, mv + octp, mm))
        print("  %-14s 把位 %s  移动 %.1f 品%s" % (
            tag, " -> ".join("%.0f" % _ctr(v[3][2]) for v in seq), mv, flag))
        print("                 %s" % "  ".join(
            "%s: %s" % (v[0], " ".join("%d弦%d品" % (s, f) for s, f in v[3][1])) for v in seq))
    print()
    for tag, key_pc, mode in [("A 小调", 9, "min"), ("C 大调", 0, "maj"), ("E 小调", 4, "min")]:
        iv2 = [0, 2, 3, 5, 7, 8, 10, 12] if mode == "min" else [0, 2, 4, 5, 7, 9, 11, 12]
        notes = [36 + key_pc + i for i in iv2]
        sh = scale_shapes(notes, OPEN_STD)
        n += 1
        opens = sum(1 for p in sh if p and p[1] == 0)
        mx = max([p[1] for p in sh if p] or [0])
        if opens == 0:
            bad.append("%s 音阶一个空弦都没有" % tag)
        if mx > 7:
            bad.append("%s 音阶最高到 %d 品（>7）" % (tag, mx))
        print("  %-8s 空弦 %d 个，最高 %d 品   %s" % (
            tag, opens, mx, "  ".join("%d弦%d品" % p if p else "-" for p in sh)))
    print()
    if bad:
        print("  失败 %d 条:" % len(bad))
        for b in bad:
            print("    · " + b)
    else:
        print("  全部通过")
    print()
    print("  %d 条：%d 通过 / %d 失败" % (n, n - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
