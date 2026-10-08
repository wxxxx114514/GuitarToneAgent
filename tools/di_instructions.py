"""按参考曲的分析结果，生成【给小白看的】录音指令
   不出现任何乐理词汇——只给：第几弦、第几品、手掌怎么放、弹多久
用法:  python di_instructions.py [歌曲目录]
读:    spec.json（key / chords / technique）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from songlib import (song_dir, P, utf8_stdout, chord_segments, source_of,
                     is_user_confirmed, CHORD_BUDGET_S, num_or_none)
from fingering import parse_chord, plan_sequence, scale_shapes, pc_of

utf8_stdout()   # 直接 python xxx.py 跑时（不经 tone.bat）中文和符号不炸：Windows 控制台默认 GBK

NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
CH_NAME = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
# 各种调弦的空弦 MIDI（6 弦到 1 弦）
TUNINGS = {
    "standard": {6: 40, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64},   # E A D G B E
    "drop_d":   {6: 38, 5: 45, 4: 50, 3: 55, 2: 59, 1: 64},   # D A D G B E
    "half_down":{6: 39, 5: 44, 4: 49, 3: 54, 2: 58, 1: 63},   # Eb
    "drop_c":   {6: 36, 5: 43, 4: 48, 3: 53, 2: 57, 1: 62},   # C G C F A D
}
OPEN = TUNINGS["standard"]

SCALE_MAJ = [0, 2, 4, 5, 7, 9, 11, 12]   # 自然大调 + 高八度主音
SCALE_MIN = [0, 2, 3, 5, 7, 8, 10, 12]   # 自然小调 —— 大调音阶段喂小调歌会喂进错音级

def note_of(chord):
    """从和弦名取根音 -> 音名（认降号：Bb -> A#）；认不出来 None"""
    s = (chord or "").strip()
    if not s: return None
    k = 2 if (len(s) > 1 and s[1] in "#b") else 1
    pc = pc_of(s[:k])
    return CH_NAME[pc] if pc is not None else None

def scale_notes(root_name, mode="maj", open_midi=None):
    """定调音阶 -> [(midi, (弦, 品)), ...]，从主音往上走一个八度

    ★ 按法交给 fingering.scale_shapes：**优先空弦**（技能要求：单音段固定开放弦），
      其次整段移动最小 —— 原来是每个音各自找"最低品"，音与音之间在弦上乱跳。
      失效条件：调弦的音域盖不住这个八度时，个别音会没有按法（那一条直接不打印）。
    """
    iv = SCALE_MIN if mode == "min" else SCALE_MAJ
    base = pc_of(root_name)
    if base is None:
        base = 4                                    # 认不出来 -> E（调用方会打告警）
    m0 = 36 + base
    while m0 + max(iv) < min(open_midi.values()) + 12 and m0 < 60:
        m0 += 12
    notes = [m0 + i for i in iv]
    sh = scale_shapes(notes, open_midi)
    return [(m, p) for m, p in zip(notes, sh) if p]


D = song_dir()
sp = P(D, "spec")
def _spec_enc():
    """原文件带 BOM 就用 utf-8-sig 写回 —— 用户手存的 spec.json 常带，丢掉会让他的编辑器认不出"""
    try:
        return "utf-8-sig" if open(sp, "rb").read(3) == b"\xef\xbb\xbf" else "utf-8"
    except Exception:
        return "utf-8"
if not sp.exists():
    print("缺 spec.json，先跑 chords.py 和 technique.py"); sys.exit(2)
spec = json.load(open(sp, encoding="utf-8-sig"))

TUNE = spec.get("tuning", "standard")
OPEN = TUNINGS.get(TUNE, TUNINGS["standard"])
# ★ 调弦是【输入】：只有 tuning_source == "user" 才算确认过。
#   没确认时必须把"这是假设值"打在屏幕上 —— 否则用户按一整套错指法录完，才发现调弦是猜的。
#   （未识别的名字也不许静默按标准算：说清它不认识、且正在按什么算。）
TXT = {"standard": "标准 EADGBE", "drop_d": "Drop D (DADGBE)",
       "half_down": "降半音", "drop_c": "Drop C"}
_src = spec.get("tuning_source")
if TUNE not in TUNINGS:
    print("[调弦] !! spec 里的 tuning = %r 不认识（支持 %s）" % (TUNE, " / ".join(TUNINGS)))
    print("       本次【按标准 EADGBE 算指法】—— 这是假设，去问用户")
elif _src != "user":
    print("[调弦] %s   ⚠️【假设值：未经用户确认】" % TXT.get(TUNE, TUNE))
    print("       spec 里没有 tuning_source=user —— 让用户念一下他琴上的调弦，")
    print("       再用 tone.bat run check_tuning.py --set=<他说的那套> 记下来，然后重跑本脚本")
else:
    print("[调弦] %s（用户确认过）" % TXT.get(TUNE, TUNE))

# ★ 早退时不许留下【上一版】的 di_plan：它是计划，不是历史 —— 这次没生成成功就该作废
if "di_plan" in spec:
    # ★ 必须真写盘：只改内存的话，早退（比如和弦名非法）时文件里留着【上一版】的计划，
    #   下游读到的是过期的东西 —— 实测改成非法和弦再跑，文件里 di_plan 仍是旧的。
    spec.pop("di_plan")
    try:
        _tmp0 = str(sp) + ".tmp"
        json.dump(spec, open(_tmp0, "w", encoding=_spec_enc()), ensure_ascii=False, indent=2)
        os.replace(_tmp0, sp)
    except Exception:
        pass
# ── ③ 琴上的音量旋钮：记录项（不写标定工具 —— 电平差被 meas_prep 的峰值归一化按设计扔掉，
#    剩下的频响差是这把琴电位器的性质、不是歌的性质；而且录完之后旋钮与声卡增益不可分）。
#    它的唯一读者是 verify_di 的电平报错。
_setv = None
for _a in sys.argv[1:]:
    if _a.startswith("--set-volume="):
        _raw = _a.split("=", 1)[1]
        try:
            _setv = float(_raw) + 0.0   # T3③：-0.0 归一成 0.0
        except Exception:
            print("!! --set-volume 要一个数（你给的是 %r）—— 范围 0-10" % _raw); sys.exit(2)
        if not (0.0 <= _setv <= 10.0):
            # ★ 解析成功但越界也要拒：否则会落盘一个坏值，之后 verify_di 照着念「旋钮在 15.0」
            print("!! --set-volume=%.1f 超出范围（琴上的音量旋钮是 0-10）—— 没有写盘" % _setv); sys.exit(2)
if _setv is not None:
    spec["guitar_volume"] = _setv
    spec["guitar_volume_source"] = "user"
    _tmp = str(sp) + ".tmp"
    json.dump(spec, open(_tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(_tmp, sp)
    print("[旋钮] 已记：你琴上的音量旋钮在 %.1f（0-10）—— 录 DI 全程别动它" % _setv)
else:
    _gv = num_or_none(spec, "guitar_volume")
    if spec.get("guitar_volume") is not None and _gv is None:
        print("[旋钮] spec 里的 guitar_volume=%r 不是一个数 —— 已忽略（重新记：--set-volume=7）"
              % spec.get("guitar_volume"))
    elif _gv is not None:
        print("[旋钮] spec 记的是 %.1f（来源 %s）—— 录之前确认它没被碰过"
              % (_gv, source_of(spec, "guitar_volume")))
    else:
        print("[旋钮] spec 里没有你琴上音量旋钮的位置 —— 念一个数字记下来："
              "tone.bat run di_instructions.py --set-volume=7")
        print("       放在【你平时弹这首歌的位置】就行（不是开到最大 —— 预设是拿这段 DI 解的，"
              "只在你实际会用的位置成立）")
key = spec.get("key", "E")
chords = spec.get("chords", [])
tech = spec.get("technique", {}) or {}
# ★ 占比只读【一个口径】：technique.pct（时长占比）。
#   旧格式（palm_pct/mid_pct/open_pct，按音符个数）只作兜底，并且必须标出来 ——
#   两种口径在真歌上差 21.4 点，混着用会静默改变 DI 的内容。
PCT = dict(tech.get("pct") or {})
TE_LEGACY = False
if not PCT:
    PCT = {"palm": tech.get("palm_pct", 0), "mid": tech.get("mid_pct", 0), "open": tech.get("open_pct", 0)}
    TE_LEGACY = any(PCT.values())
TE_SRC = source_of(spec, "technique")
NO_TECH = sum(float(v or 0) for v in PCT.values()) <= 0
if NO_TECH:
    PCT = {"mid": 100.0}           # 未知 -> 按【正常拨弦】，不假设闷音
if TE_LEGACY:
    print("[奏法] spec 里的占比是【旧格式】（按音符个数）—— 重跑 technique.py 换成按时间的口径")
if not is_user_confirmed(spec, "technique"):
    print("[奏法] 占比来源：%s【未经用户确认】—— 要改：tone.bat run technique.py --main=palm|mid|open"
          % ("旧格式" if TE_LEGACY else TE_SRC))

ORD = {6:"最粗的那根", 5:"第 2 粗的", 4:"第 3 根", 3:"第 4 根", 2:"第 5 根", 1:"最细的那根"}
def pos(s, f):
    if f == 0: return "%s弦（第 %d 弦），什么都不按" % (ORD[s], s)
    return "%s弦（第 %d 弦）第 %d 品" % (ORD[s], s, f)
# 单音音阶（按这首歌的调式）—— 只弹和弦的话频谱只被根音+五度激励，测出来是偏的
key_note = note_of(key)
MODE = spec.get("key_mode", "unknown")
# ★ key_mode 的来源必须打出来：它常常是 chords.py 用【和弦三度】推的，而那三度不可靠
if MODE in ("min", "maj"):
    _msrc = source_of(spec, "key_mode")
    print("[调式] spec 记的是 %s（来源 %s）%s"
          % (MODE, _msrc, "" if is_user_confirmed(spec, "key_mode") else "  ⚠️【假设值：未经用户确认】"))
if MODE not in ("min", "maj"):
    # ★ 调式没标注时【不许静默按大调】：小调歌会被喂进 2 个不属于它的音级
    #   （实测：A 小调歌 Am/F/C/G 被喂成 A 大调 A B C# D E F# G# A）。
    #   能算：拿 spec 的和弦表去比两个调式音阶，命中根音多的那个。
    #   失效条件：和弦表为空、或整首歌是调式混合/五声 —— 那时选不出来，就如实说"未知"。
    # ★ 判据用【和弦的三度】，不是只数根音：只数根音时，"Am–F" 这种两和弦小调 vamp
    #   大调命中 1、小调命中 2（差 1）会被判成"分不出"→ 退回大调 → 喂进 C#/F#/G#（审计实测）。
    #   和弦名里的 m / maj / dim 就是现成的三度信息，用它区分度立刻拉开（Am–F：大调 0、小调 2）。
    MAJ_DIA = {0: "maj", 2: "min", 4: "min", 5: "maj", 7: "maj", 9: "min", 11: "dim"}
    MIN_DIA = {0: "min", 2: "dim", 3: "maj", 5: "min", 7: "min", 8: "maj", 10: "maj"}

    def _rq(lbl):
        """★ 调式推断必须用【和和弦表同一个】解析器：旧的两个解析器对同一标签答案不同
        （_root_qual 把无后缀当大三、fingering 那套当强力和弦）—— 审计就是这么发现的。
        ★ 它和 _score 都【在用】（:126 / :146 / :150）—— 我上一次当死代码删掉，
          结果凡是没有 key_mode 的 spec（真歌就是）全部 exit 1 NameError。"""
        p = parse_chord(lbl)
        return (p[0], p[1]) if p else (None, None)

    def _score(dia, items):
        """命中数：没有三度信息（pow/None）的只看根音在不在音阶里，有的连三度一起对"""
        n = 0
        for rr, qq in items:
            if qq in (None, "pow"):
                n += 1 if ((rr - r0) % 12) in dia else 0
            else:
                n += 1 if dia.get((rr - r0) % 12) == qq else 0
        return n



    def _off_list(dia):
        """不属于这个调式三和弦的和弦（用来暴露调式音乐/借用和弦）"""
        out = []
        for c in chords[:20]:
            r, q = _rq(c)
            if r is None: continue
            d = (r - r0) % 12
            if (q in (None, "pow") and d not in dia) or (q not in (None, "pow") and dia.get(d) != q):
                out.append(c)
        return out

    def _decide(use_maj, how):
        global MODE
        MODE = "maj" if use_maj else "min"
        dia = MAJ_DIA if use_maj else MIN_DIA
        print("[调式] spec 没标 key_mode —— %s【%s】" % (how, {"maj": "自然大调", "min": "自然小调"}[MODE]))
        off = _off_list(dia)
        if off:
            print("       ⚠️ 有 %d 个和弦不属于这个调式的三和弦（%s）—— 可能是调式音乐" % (len(off), " / ".join(off[:4])))
            print("          （Mixolydian / Dorian 这类）或借用了和弦：音阶段可能有一个音级是错的，最保险是先问用户")
        return dia

    if key_note in NAMES:
        r0 = NAMES.index(key_note)
        pairs = [p for p in (_rq(c) for c in chords[:20]) if p[0] is not None]
        # ★ 「没有三度」= pow 或 None 都算：parse_chord 对 X5 现在返回 "pow"（不是 None），
        #   只判 None 会让这条分支永远不执行 —— X5-only 的歌就被默认成自然大调（实测 3 个音级错）。
        tert = [(r, q) for r, q in pairs if q not in (None, "pow")]      # 带三度的那些：真证据
        sm, sn = _score(MAJ_DIA, pairs), _score(MIN_DIA, pairs)
        smt, snt = _score(MAJ_DIA, tert), _score(MIN_DIA, tert)
        if pairs and abs(sm - sn) >= 2:
            _decide(sm > sn, "按和弦表推断为（大调命中 %d/%d，小调命中 %d/%d）" % (sm, len(pairs), sn, len(pairs)))
            print("       要更准就先跑 chords.py（它会写 key_mode），或让用户确认这首歌的大小调")
        elif tert and smt != snt:
            # ★ 先用【带三度的和弦】下结论：只要有一个三度和弦，它就是真证据，
            #   不能被「半数以上是强力和弦」盖掉（实测 [A5,E5,D] 大调 3 / 小调 2，先验却判了小调）。
            _decide(smt > snt, "按带三度的 %d 个和弦判（大调 %d，小调 %d）" % (len(tert), smt, snt))
        elif not tert and pairs:
            # 有和弦、但一个三度都没有（全是 X5）：三度判据无从下手，按曲风先验取【自然小调】并说清。
            _decide(False, "和弦表里 %d 个全是强力和弦（没有三度），判不出大小调 -> 按金属/摇滚的先验取" % len(pairs))
            print("       ⚠️ 若这首其实是大调，音阶段会有 3 个音级是错的 —— 最保险是问用户一句")
        elif not pairs:
            # ★ 空表 / 标签全解析不出来：**没有数据就下结论是另一回事**。
            #   先验的适用条件是「有 X5 证据」，不是「没有证据」—— 这里必须如实说没有数据。
            #   （实测：空和弦表被打成「0 个全是强力和弦」这种自相矛盾的假话，还默认取了小调。）
            print("[调式] spec 没标 key_mode，和弦表也是空的（或标签都解析不出来）—— 没有数据可判。")
            print("       本次按【自然大调】算；若这首歌是小调，音阶段会喂进 3 个错音级。先跑 chords.py 或问用户")
        else:
            print("[调式] spec 没标 key_mode，和弦表也【分不出】大小调（大调 %d 小调 %d）—— 按自然大调算"
                  % (sm, sn))
            off = _off_list(MAJ_DIA)
            if off:
                print("       ⚠️ 有 %d 个和弦不属于自然大调的三和弦（%s）" % (len(off), " / ".join(off[:4])))
            print("       ⚠️ 若这首歌是小调/调式音乐，音阶段会喂进它没有的音级 —— 先跑 chords.py 或问用户")
    else:
        print("[调式] spec 没标 key_mode，也没法从 key=%r 推 —— 本次按【自然大调】算，先跑 chords.py" % key)

# ── 和弦表：用 spec 的【全部】和弦（旧实现只取 roots[2:4]，4 个和弦的歌只弹 2 个）
#    性质优先从名字读（Am -> 小三）；没有三度信息的标签（A5）就按调式音级推。
#    三度要不要按曲风先验：失真/金属默认【不要】（强力和弦），清音/流行要。
GCLEAN = ("clean", "jazz", "pop", "ballad", "funk", "country", "blues", "acoustic",
          "清音", "民谣", "流行", "爵士", "不插电")
# ★ 金属类关键词【优先】：genre="pop metal" 同时含 pop 与 metal，不能因为含 pop 就要三度
GMETAL = ("metal", "metalcore", "hardcore", "punk", "djent", "death", "black", "thrash",
          "doom", "grind", "screamo", "core", "金属", "核", "硬核")
GENRE = str(spec.get("genre") or "").lower()
WANT_THIRD = (any(g in GENRE for g in GCLEAN) and not any(g in GENRE for g in GMETAL))
key_pc = pc_of(key)
if not chords:
    print("[和弦] !! spec 里没有和弦表 —— 生成不了和弦段。先跑 chords.py。")
    sys.exit(2)
CH, BAD, DEGRADED = [], [], []
for c in chords[:20]:   # 和 chords.py 写进 spec 的上限一致（旧值 12 会静默丢尾）
    _r, _q, _note = parse_chord(c, key_pc=key_pc, mode=(MODE if MODE in ("maj", "min") else "maj"))
    if _r is None:
        BAD.append(c); continue
    if _note:
        DEGRADED.append("%s：%s" % (c, _note))
    if all(x[0] != c for x in CH):
        CH.append((c, _r, _q))
if BAD:
    print("[和弦] !! 这些和弦名认不出来: %s" % ", ".join(map(str, BAD)))
    print("       和弦名 = 根音（可带 #/b）+ 可选性质（m / maj / 5 / dim / aug）；改 spec.json 再跑。")
    sys.exit(2)
PLAN = plan_sequence(CH, OPEN, want_third=WANT_THIRD)
# ★ A2：解析时降级过的和弦必须【打出来】—— 旧实现把 Cdim/C7/Csus4/斜杠和弦全静默变强力和弦，
#   屏幕上却仍印原名，用户以为弹的是那个和弦。
MISS = [x[0] for x in PLAN if x[3] is None]
if MISS:
    print("[和弦] !! 这些和弦在 %s 调弦下、12 品以内推不出按法: %s" % (TUNE, ", ".join(MISS)))
    print("       先问用户是不是换了调弦，别硬凑。")
    sys.exit(2)
if DEGRADED:
    # ★ 不许静默：降级过的和弦必须逐个打出来（旧实现把 Cdim/C7/Csus4/斜杠和弦全静默变强力和弦）
    print("[和弦] !! %d 个和弦弹不出精确音高，已按强力和弦弹（频谱会缺音级）：" % len(DEGRADED))
    for _d in DEGRADED:
        print("       · " + _d)
# ── ④b：用户给过的音高材料（chords_known.roots）—— 只用来【校验】推断的和弦表 ──
#   契约：{"roots": ["E","F",...]}，每一项必须是【音名】（A-G 开头，后面最多一个 #/b）。
#   ★ 四条硬规矩：① 形状不对【跳过】不许 KeyError；② 一个音名都解析不出来也【跳过】——
#     否则空集合会让每条和弦都判"不在你的材料里"，看起来像一次真验证（实测 roots=["H","Zz"] 就是这么错的）；
#     ③ 认不出的条目数要打出来；④ 校验结果落 di_plan，包括 skipped。
import re as _re
CK = spec.get("chords_known")
CK_ROOTS = CK.get("roots") if isinstance(CK, dict) else None
_ck_good = None
NOT_IN = []
CK_SKIP_WHY = ""

def _is_note_name(x):
    # ★ 只收 pc_of【真正认】的写法：## / bb。不收 x —— 声明支持 x 而解析器把它当 G，
    #   那是静默误读（比直接拒掉更危险）。见 03-陷阱清单。
    return bool(_re.match(r"^[A-Ga-g](#{1,2}|b{1,2})?$", str(x).strip()))

if not isinstance(CK, dict):
    CK_SKIP_WHY = "没有 chords_known"
elif "roots" not in CK:
    CK_SKIP_WHY = "chords_known 里没有 roots 字段"
elif not isinstance(CK_ROOTS, list):
    CK_SKIP_WHY = "chords_known.roots 不是列表（要的是 [音名, ...]）"
elif len(CK_ROOTS) == 0:
    CK_SKIP_WHY = "chords_known.roots 是空的"
else:
    _bad = [x for x in CK_ROOTS if not _is_note_name(x)]
    _ck_good = [str(x).strip() for x in CK_ROOTS if _is_note_name(x)]
    if _bad:
        print("[和弦] 你给的 roots 里有 %d 个不是音名（%s）—— 已忽略它们"
              % (len(_bad), " / ".join(map(str, _bad[:4]))))
    if not _ck_good:
        CK_SKIP_WHY = "你给的 %d 个 roots 一个音名都没认出来" % len(CK_ROOTS)
if CK_SKIP_WHY:
    print("[和弦] 用户材料不可用（%s）—— 本项校验跳过，不当成通过" % CK_SKIP_WHY)
else:
    _upcs = set(x for x in (pc_of(r) for r in _ck_good) if x is not None)
    NOT_IN = [lab for lab, rr, qq in CH if rr not in _upcs]
    if NOT_IN:
        print("[和弦] ⚠️ 推断的和弦表里有 %d 个根音【不在你给的材料里】：%s" % (len(NOT_IN), " / ".join(NOT_IN[:8])))
        print("       只报不删（也许你只列了你会弹的形）；但残差异常时先看这一条 —— 见 Skill §7.3 内容匹配")
    else:
        print("[和弦] 用户给过的 %d 个根音与推断表一致" % len(_ck_good))
# ── P4-B：贝斯参考 vs 本次 DI 的音阶 / 推断和弦表（★ 只出证伪）──────────────
#   不对称是有意的：贝斯弹的就是吉他和弦的根音，所以「一致」是构造出来的、不是证据
#   （项目先例：吉他与贝斯同度齐奏时音频上无法分离，命中过半即判据失效）。
#   ★ 消费者必须尊重生产者的 screen.status：weak 或 clamped>0 时【不许报冲突】——
#     否则同一批会同时出货一个「声明证据不足」的工具和一个「拿它当证据」的工具。
#   ★ 三种"用不了"必须分开说（评审反例 1/3）：字段缺失 / 跑了但为空 / 值不是音名 ——
#     混成一句「没有贝斯参考（先跑 bass_reference.py）」在第二种情况下是假话。
_BR = spec.get("bass_ref")
BASS_CHECK = {"skipped": True, "reason": "", "status": None}
if not isinstance(_BR, dict):
    print("[贝斯] 没有贝斯参考（先跑 bass_reference.py）—— 本项交叉校验跳过，不当成通过")
    BASS_CHECK["reason"] = "no_bass_ref"
elif _BR.get("top_pc") is None:
    print("[贝斯] 贝斯参考为空（跑过了，但一个有效帧都没有）—— 本项跳过，不当成通过")
    BASS_CHECK["reason"] = "empty_bass_ref"
else:
    _scr = _BR.get("screen") or {}
    _st = _scr.get("status")
    # ★ 用 num_or_none 读（本项目规矩：手写字段不许让消费者的行为变成 traceback）
    _cl_raw = _BR.get("clamped_frames")
    _cl = int(num_or_none(_BR, "clamped_frames") or 0)
    # ★ 不对称是有意的（评审问过）：【缺失】当 0（schema 里本来就没这个字段 -> 不是信息），
    #   【坏值】当未知（有人写过信息但坏了 -> 不能当"没有"）。二者混为一谈会让坏数据静默通过。
    _cl_bad = (_cl_raw is not None and num_or_none(_BR, "clamped_frames") is None)
    if _st != "ok" or _cl > 0 or _cl_bad:
        print("[贝斯] 参考证据不足（status=%s；%s）—— 本项不报冲突"
              % (_st, "；".join(_scr.get("reasons") or [])
                 or ("clamped_frames=%r 读不出来" % _cl_raw if _cl_bad else "钳位 %d 帧" % _cl)))
        BASS_CHECK.update({"reason": "weak_evidence", "status": _st,
                           "top_pc": _BR.get("top_pc"), "top_pc_pct": _BR.get("top_pc_pct")})
    else:
        _top = _BR["top_pc"]
        _tpc = pc_of(_top)
        # ★ 认不出来的音名要【跳过】，不许拿它去比 —— 同一个文件往上就是先例（:317 的 roots=["H","Zz"]），
        #   None 与任何集合比较都是 False -> 会打出「⚠️ 不在本次音阶里」这种带警告符号的硬结论。
        if _tpc is None:
            print("[贝斯] bass_ref.top_pc=%r 不是音名 —— 本项跳过，不当成通过" % (_top,))
            BASS_CHECK = {"skipped": True, "reason": "bad_top_pc", "top_pc": _top}
        else:
            _kpc = pc_of(key) or 4
            _scale_pcs = set((_kpc + m) % 12 for m in (SCALE_MIN if MODE == "min" else SCALE_MAJ))
            _root_pcs = set(rr for _, rr, _q in CH)
            BASS_CHECK = {"skipped": False, "status": _st, "top_pc": _top,
                          "top_pc_pct": _BR.get("top_pc_pct"), "in_scale": _tpc in _scale_pcs,
                          "in_chord_roots": _tpc in _root_pcs, "reason": ""}
            if _tpc not in _scale_pcs:
                print("[贝斯] ⚠️ 贝斯最常出现的音级 %s（%.0f%%）**不在本次音阶里**（%s %s）——"
                      % (_top, _BR.get("top_pc_pct") or 0, key, MODE))
                print("       整条音阶由调性决定，key 错 = 整份 DI 错。先查 key（权威是 chords.py 从吉他推的），"
                      "再看是贝斯持续音/串音。")
            elif _tpc not in _root_pcs:
                print("[贝斯] 注意：贝斯最常出现的音级 %s 不在推断的和弦根音里（可能只是持续音/属音）" % _top)
            else:
                print("[贝斯] 贝斯最强音级 %s 与本次音阶/和弦根音一致"
                      "（★ 同度齐奏时这条【不构成独立证据】—— 贝斯弹的就是和弦根音）" % _top)
    print("[和弦] %s  三度：%s（曲风 %r）"
      % (" / ".join("%s%s" % (lab, "" if q == "pow" else "") for lab, r, q in CH),
         "要" if WANT_THIRD else "不要（强力和弦）", GENRE or "未标注"))

NOTES = scale_notes(key_note or "E", MODE, OPEN)
# ★ 段落与秒数由 songlib.chord_segments 统一算 —— technique.py 的回显调的是同一个函数。
#   上次的教训：回显手写「8 秒」，实际归一化后 5 秒；两处各写一份必然对不上。
#   ★ 最多两种奏法（用户路径与测量路径结构相同）：第 4 段（对比段）两条路径一起去掉 ——
#     否则「用户 2 种 / 测量 3 种」是两套结构，verify_di 也得跟着分叉。
CH_SEGS = chord_segments(PCT)
DOM, T_DOM = CH_SEGS[0]
SEC, T_SEC = (CH_SEGS[1] if len(CH_SEGS) > 1 else (None, 0.0))
T_TXT = {"palm": "闷音", "mid": "正常拨弦", "open": "放开手"}
RH_TXT = {
    "palm": ["右手：手掌外侧【轻轻压在琴桥前面】，让声音变成短促的",
             '      "哒哒哒"，不是"当当当"',
             "      中速连续下拨，大约每秒 4 下"],
    "mid":  ["右手：正常拨弦，手掌【不要】压弦，声音是正常长度的",
             "      中速下拨，大约每秒 4 下"],
    "open": ["右手：正常拨弦，让每个音自然响完，不要压弦",
             "      中速下拨，大约每秒 4 下"],
}
# 单音段【默认必录】：定调自然大调音阶，固定一遍，不随织体判定变（应录尽录）
REP = 1
TS = max(6.0, round(len(NOTES) * 1.2))


SEGS = []                                   # (类型, 奏法, 时长)
SEGS.append(("main", DOM, T_DOM))
if SEC: SEGS.append(("alt", SEC, T_SEC))
# ★ A4：音阶段固定用【正常拨弦】，不继承主奏法：闷音的音 100-250 ms 就死了，
#   测到的是瞬态不是音高 —— 那一段唯一的作用（补音高覆盖）会被废掉（reference/06 §7.7）。
SEGS.append(("scale", "mid", TS))
_total = sum(x[2] for x in SEGS)

print()
print("=" * 62)
print("   请录一段干声（吉他直接插声卡，中间不要接任何效果器）")
print("=" * 62)
print()
print("总共约 %.0f 秒，分 %d 段。" % (_total, len(SEGS)))
print("★ 每段之间【完全停手 1 秒】——手离开琴弦，让声音彻底消失")
print("  （系统靠这个静音自动分段，用来检查你每段弹对了没有）")
print()
for _n, (_kind, _tech, _dur) in enumerate(SEGS, 1):
    print("-" * 62)
    if _kind == "main":
        print("第 %d 段   %s    约 %.0f 秒" % (_n, T_TXT[_tech], _dur))
        print("-" * 62)
        print("  按这个顺序弹（每条都挑过：整段左手移动最小）%s：" % ("，带三度" if WANT_THIRD else "，强力和弦（没有三度）"))
        for _i, (_lab, _r, _q, _v, _nv) in enumerate(PLAN, 1):
            print("      %d. %s   %s" % (_i, _lab, "  ".join(pos(_s, _f) for _s, _f in _v[1])))
        print()
        for _l in RH_TXT[_tech]: print("  " + _l)
    elif _kind == "alt":
        print("第 %d 段   %s，换个位置    约 %.0f 秒" % (_n, T_TXT[_tech], _dur))
        print("-" * 62)
        print("  位置【和第 1 段一样】（内容必须和参考曲对齐，只换奏法）：")
        for _i, (_lab, _r, _q, _v, _nv) in enumerate(PLAN, 1):
            print("      %d. %s   %s" % (_i, _lab, "  ".join(pos(_s, _f) for _s, _f in _v[1])))
        print()
        for _l in RH_TXT[_tech]: print("  " + _l)
    elif _kind == "scale":
        print("第 %d 段   一个一个音弹（不要扫弦）    约 %.0f 秒" % (_n, _dur))
        print("-" * 62)
        print("  每次只让【一根弦】响，别扫到别的弦")
        print("  按下面的顺序，一个音一个音地弹，每个音响约 1 秒再换下一个：")
        for _i, (_m, (_s, _f)) in enumerate(NOTES, 1):
            print("      %d. %s" % (_i, pos(_s, _f)))
        _dom_is_mid = (DOM == "mid")
        print("  右手：%s" % ("跟第 1 段一样（正常拨弦）" if _dom_is_mid
                              else "★【正常拨弦】—— 和第 1 段不同：第 1 段是%s，闷着的音太短，测不到音高" % T_TXT[DOM]))
        print("  弹 %d 遍（弹错了不用重录，接着往下弹）" % REP)
    else:
        print("第 %d 段   %s（对比段）    约 %.0f 秒" % (_n, T_TXT[_tech], _dur))
        print("-" * 62)
        print("  左手按第 1 段的第 1 个位置（%s）" % "  ".join(pos(_s, _f) for _s, _f in PLAN[0][3][1]))
        for _l in RH_TXT[_tech]: print("  " + _l)
        print("  每 2 秒弹一次，弹 3-4 次")
    print()
print("=" * 62)
print("  音准不用管，音量也不用管——脚本会自动调整")
print("  录完保存成 wav，放进：%s" % (P(D, "di")))
print("  文件名改成 palm_di.wav")
print("=" * 62)
print()
print("[给 AI 看的] 这一步的依据：")
print("  调性 %s，主要和弦 %s" % (key, ", ".join(chords[:2])))
print("  奏法占比（按时间）: 闷音 %.0f%% / 正常 %.0f%% / 放开 %.0f%%   来源 %s"
      % (PCT.get("palm", 0), PCT.get("mid", 0), PCT.get("open", 0),
         ("旧格式" if TE_LEGACY else TE_SRC) + ("（用户确认）" if is_user_confirmed(spec, "technique") else "【未经确认】")))
print("  段落的秒数照着这个占比配（内容对齐，见 Skill §7.3）；最多两种奏法 + 固定的单音段")
print("  第 3 段是定调【%s】的%s音阶单音，补音高覆盖——"
      % (key_note or "E", {"min": "自然小调", "maj": "自然大调"}.get(MODE, "自然大调（调式未标注）")))
if not key_note:
    # ★ spec 的 key 认不出来时，页脚打印的是【实际用的基音】而不是那个字符串 ——
    #   否则屏幕会写「定调【H】的音阶」，而实际弹的是 E 起的音阶（审计实测）。
    print("  ⚠️ spec 的 key=%r 认不出来 —— 上面这个音阶是从 E 起的；先改 spec 的 key" % key)
print("  只弹和弦的话，频谱只被根音和五度激励，量出来的曲线是偏的")
print("  和弦段覆盖 %d 个和弦（spec 里 %d 个）" % (len(PLAN), len(chords)))

# ── 把这次的计划写回 spec.json（di_plan）─────────────────────────────────
# ★ 为什么必须落盘：下游 verify_di / analyze_round 之前只能"猜"用户录的是什么
#   （所以只能做很弱的检查）。有了 di_plan，就能按【计划】核对：这段该是闷音、
#   该是这几个音、这个和弦该是这个按法 —— 而不是拿一条 histogram 反推。
try:
    _plan = {
        "generated_by": "di_instructions.py",
        "tuning": TUNE, "tuning_source": _src, "key": key, "key_pc": key_pc,
        "mode": MODE, "genre": GENRE, "want_third": bool(WANT_THIRD),
        "segments": [{"kind": k, "technique": t, "seconds": d} for k, t, d in SEGS],
        # ★ 只有一种奏法时，verify_di 的奏法自参照会跳过（它需要 2 种）——
        #   这是【正确跳过】不是漏检，但必须落在计划里，否则看起来像忘了检查。
        "one_technique": (SEC is None),
        # ④：用户材料 vs 推断表的校验结果 —— 落在计划里，别只在屏幕上飘一句
        "chord_check": {"user_roots": _ck_good,
                        "skipped": bool(CK_SKIP_WHY),
                        "skip_reason": CK_SKIP_WHY,
                        "not_in_user_roots": NOT_IN},
        "key_source": source_of(spec, "key"), "key_mode_source": source_of(spec, "key_mode"),
        "bass_check": BASS_CHECK,
        "technique_source": TE_SRC, "technique_pct": PCT,
        "segments_note": ("只有一种奏法 -> verify_di 的奏法自参照会跳过（需要 2 种占 10% 以上的奏法）"
                          if SEC is None else ""),
        "chords": [{"label": lab, "root_pc": r,
                    "requested_quality": q,                       # 名字/谱面给的
                    "requested_label_suffix": str(lab)[1:].lstrip("#b"),   # 名字里的后缀（降级时它才是原始要求）
                    "played_quality": q if WANT_THIRD else "pow", # 实际弹的（金属不要三度）
                    "played_pcs": sorted(set((OPEN[st] + fr) % 12 for st, fr in v[1])),
                    "root_midi": OPEN[v[3]] + v[0],               # 实际弹的根音（音区是事实，不是猜测）
                    "root_octave": (OPEN[v[3]] + v[0] - 12) // 12 - 1,
                    "shape": [{"string": st, "fret": fr} for st, fr in v[1]]}
                   for lab, r, q, v, nv in PLAN],
        "scale": [{"midi": m, "string": st, "fret": fr} for m, (st, fr) in NOTES],
    }
    spec["di_plan"] = _plan
    # ★ 原子写：先写临时文件再 os.replace —— 中途失败不会把 spec.json 弄成半截
    # ★ 保留原来的 BOM：用户手存的 spec.json 常带 BOM，写回时丢掉会让他的编辑器认不出
    _tmp = str(sp) + ".tmp"
    with open(_tmp, "w", encoding=_spec_enc()) as _f:
        json.dump(spec, _f, ensure_ascii=False, indent=2)
    os.replace(_tmp, sp)
    print("  [已记] spec.json -> di_plan（本步只落盘；★ 下游 verify_di / analyze_round 目前【还没有】读它，")
    print("         接线是后面那一步的事 —— 现在别以为核对已经存在了）")
except Exception as _e:
    try:
        if os.path.exists(str(sp) + ".tmp"):
            os.remove(str(sp) + ".tmp")          # 不留残渣
    except Exception:
        pass
    print("  !! di_plan 写回失败（%s）—— 检查 spec.json 是否可写" % _e)
