"""验证用户录的 DI
   ★ 设计原则：全流程只用用户真实录音，不依赖任何合成基准
   ★ 奏法检查是【自参照】的：拿用户的闷音段跟他自己的开放段比
用法:  python verify_di.py [歌曲目录] [DI文件名，默认 palm_di.wav]
"""
import warnings; warnings.filterwarnings("ignore")
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import librosa
from songlib import (song_dir, file_args, P, load_mono, db, note_decay_times, utf8_stdout,
                     source_of, is_user_confirmed, num_or_none, DI_FMIN_HZ)

utf8_stdout()   # 直接跑时（不经 tone.bat）中文/符号不炸

NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

D = song_dir()
argv = file_args()
name = argv[0] if argv else "palm_di.wav"
DI = P(D, "di") / name
if not DI.exists():
    print("找不到 DI: %s" % DI); sys.exit(2)
spec = json.load(open(P(D, "spec"), encoding="utf-8-sig")) if P(D, "spec").exists() else {}
x, sr = load_mono(DI)
dur = len(x)/sr
rms = db(np.sqrt((x.astype(np.float64)**2).mean())); pk = db(np.abs(x).max())

print("=" * 62)
print("  检查你录的干声：%s" % name)
print("=" * 62)
print("  %.1f 秒   峰值 %.1f dBFS   RMS %.1f dBFS" % (dur, pk, rms))
print()

problems, suggests = [], []

# ① 电平
# ★ 手写的非数字（"7/10"）不许让这里崩 —— 读不出就当没记过，只少说一句
_vol = num_or_none(spec, "guitar_volume")
_vol_txt = ("（你琴上的音量旋钮记的是 %.1f —— 先确认它没被碰过）" % _vol) if _vol is not None else ""
if rms < -50:
    problems.append("几乎没声音（RMS %.0f dBFS）" % rms)
    suggests.append("检查：吉他插上了吗？声卡输入增益开了吗？%s" % _vol_txt)
elif pk > -0.5:
    problems.append("爆音了（峰值 %.1f dBFS）" % pk)
    suggests.append("把声卡输入增益调小，重新录%s" % _vol_txt)
else:
    print("  [OK] 电平正常")

if dur < 15:
    problems.append("太短（%.0f 秒，按指令应录 30 秒以上）" % dur)
    suggests.append("按指令把所有段都录完——尤其别漏掉【单音音阶】那一段")

# ② 自动分段（靠静音）
w = int(0.02*sr); n = len(x)//w
r = np.sqrt(np.array([(x[i*w:(i+1)*w].astype(np.float64)**2).mean() for i in range(n)]))
thr = max(np.percentile(r, 90) * 0.02, 1e-6)
silent = r < thr
segs = []; i = 0
while i < n:
    if not silent[i]:
        j = i
        while j < n and not (silent[j] and bool(np.all(silent[j:min(j+15, n)]))): j += 1
        if (j-i)*0.02 > 1.0: segs.append((i*0.02, j*0.02))
        i = j
    else:
        i += 1
print()
print("  [分段] 检测到 %d 段" % len(segs))
for k, (a, b) in enumerate(segs, 1):
    print("         第 %d 段  %5.1f - %5.1f s  (%.1f 秒)" % (k, a, b, b-a))

def desc(s0, s1):
    """★ 判奏法只能用【衰减时间】（songlib.note_decay_times，配方钉死）
       低频占比+质心已证伪：它测的是音区高低和混音 EQ，对闷音零敏感"""
    seg = x[int(s0*sr):int(s1*sr)]
    if len(seg) < 8192: return None
    _t, _d = note_decay_times(seg, sr)
    if len(_d) < 3: return None
    return (float(np.median(_d)), len(_d))
# ③ 音高 / 调弦
f0, _, _ = librosa.pyin(x, fmin=DI_FMIN_HZ, fmax=400, sr=sr, frame_length=4096, hop_length=512)
ok = ~np.isnan(f0)
if ok.sum() >= 10:
    m = np.round(69 + 12*np.log2(f0[ok]/440.0)).astype(int)
    ww = np.zeros(12)
    for mm in m: ww[mm % 12] += 1
    ww /= ww.sum()
    print()
    print("  [音高] " + "  ".join("%s %.0f%%" % (NAMES[k], 100*ww[k]) for k in np.argsort(-ww)[:4]))
    want = spec.get("key", "E")
    mode = spec.get("key_mode", "unknown")
    # ★ 判据从"占比最高的音级 == key"改成【与这首歌的调式音阶比】：
    #   旧写法对强调五度/三度的 riff 会误报（五度音级经常压过主音），
    #   而它抓不到的两类错（调式错、单个根音错半音）恰好是最贵的。
    #   现在是：把 DI 的音级分成"在调式内 / 在调式外"，报出调外占比。
    SCALE = {"min": [0, 2, 3, 5, 7, 8, 10], "maj": [0, 2, 4, 5, 7, 9, 11]}
    if want in NAMES and mode in SCALE:
        root = NAMES.index(want)
        inset = set((root + i) % 12 for i in SCALE[mode])
        out_pct = 100.0*sum(ww[k] for k in range(12) if k not in inset)
        top = NAMES[int(np.argmax(ww))]
        print("         主音 %s（调式 %s）；调外音级占 %.0f%%" % (top, mode, out_pct))
        # ★ 阈值 10%（原来写 30%）：实测"整条 DI 弹成另一个调式"时调外音级只占 15% ——
        #   因为时长被 riff 段占大头，而强力和弦的音级在两个调式里都算调内。
        #   失效条件：DI 里有大量经过音/装饰音时，调外占比会虚高；那时看主音那一行，别只看这个数。
        if out_pct > 10.0:
            problems.append("调外音级占 %.0f%%（调性 %s %s）—— DI 弹的东西跟这首歌不在一个调上"
                            % (out_pct, want, mode))
        elif top != want and ww[NAMES.index(want)] < 0.05:
            suggests.append("占比最高的音级是 %s 而不是主音 %s —— 多半只是这段 riff 强调五度/三度，"
                            "不一定是错；要判死请让用户听一遍" % (top, want))
        else:
            print("         OK（调外音级 %.0f%% ≤ 10%%）" % out_pct)
    else:
        # 没有 key / key_mode 时退回旧口径，但只作提示、不当问题
        top = NAMES[int(np.argmax(ww))]
        print("         主音 %s（spec 没记 key/key_mode，无法判调式）" % top)
        if top != want:
            suggests.append("占比最高的音级是 %s，spec 记的 key 是 %s —— 让用户听一遍再定" % (top, want))

    # ★ 这里【不做】"听起来是另一套调弦"的推断，也不引导改 spec。
    #   旧代码拿 60-400 Hz 的 12 音级直方图 + 模 12 巧合去猜另一套调弦，命中就报
    #   "听起来用的是【X】而不是 Y" 并让人改 spec.json —— 三条都违反现在的政策：
    #     ① 调弦是【输入】（用户确认），诊断只归 check_tuning.py；
    #     ② 那条诊断连最低音/低音区都没看（只看音级直方图），实测会把标准调弦弹得出的
    #        G#5 强力和弦判成 drop_d；③ nf 没有防负品守卫（根音低于 6 弦空弦时"同一把位"无意义）。
    #   现在只做一件只读的事：提醒 tuning 有没有经用户确认。
    tune = spec.get("tuning")
    if not tune or spec.get("tuning_source") != "user":
        print("  [调弦] spec 记的是 %s（来源：%s）"
              % (tune or "（没有这个字段）", spec.get("tuning_source") or "未标注"))
        suggests.append("调弦这一项没有经用户确认 —— 让用户念一下他琴上的调弦，"
                        "再用 tone.bat run check_tuning.py --set=<他说的那套> 记下来")
    else:
        print("  [调弦] %s（用户确认过）" % tune)

# ④ 奏法：自参照 —— 【只在参考曲确实有对比奏法时才有意义】
# 闷音不是默认。参考曲没有闷音时，这一项必须跳过，不能当成缺陷去催用户重录。
print()
_tech = spec.get("technique", {}) or {}
# ★ 占比只读【一个口径】：technique.pct（契约 v2）。旧格式只作兜底并标出来 ——
#   这一处曾经漏改：字段名换了以后它读到 0，于是打了「spec.json 里没有奏法占比」这句假话，
#   还把奏法自参照【静默关掉】、退出码仍是 0（没有任何东西会红）。这是 check_all 里没有 verify_di 的门漏出来的。
_PCT = dict(_tech.get("pct") or {})
_TLEG = False
if not _PCT:
    _PCT = {"palm": _tech.get("palm_pct", 0), "mid": _tech.get("mid_pct", 0), "open": _tech.get("open_pct", 0)}
    _TLEG = any(float(x or 0) for x in _PCT.values())
_pm = float(_PCT.get("palm", 0) or 0)
_md = float(_PCT.get("mid", 0) or 0)
_op = float(_PCT.get("open", 0) or 0)
_TE_SRC = source_of(spec, "technique")
if _TLEG:
    print("  [奏法] 注意：spec 里的占比是【旧格式】（按音符个数）—— 重跑 technique.py 换成按时间的口径")
if _pm + _md + _op <= 0:
    print("  [奏法] spec.json 里没有奏法占比 —— 本项跳过（先跑 technique.py）")
elif sum(1 for _v in (_pm, _md, _op) if _v >= 10) < 2:
    print("  [奏法] 参考曲只有 %d 种奏法占 10%% 以上（闷音 %.0f%% / 中间 %.0f%% / 开放 %.0f%%），" % (
        sum(1 for _v in (_pm, _md, _op) if _v >= 10), _pm, _md, _op))
    print("         没有足够对比 —— 本项不适用，跳过")
else:
    print("  [奏法] 自参照检查（参考曲：闷音 %.0f%% / 中间 %.0f%% / 开放 %.0f%%，来源 %s%s）"
          % (_pm, _md, _op, "旧格式" if _TLEG else _TE_SRC,
             "" if is_user_confirmed(spec, "technique") else "【未经用户确认】"))
    ds = [(k, a, b, desc(a, b)) for k, (a, b) in enumerate(segs)]
    ds = [(k,a,b,d) for k,a,b,d in ds if d]
    if len(ds) >= 2:
        for k, a, b, d in ds:
            print("         第 %d 段  衰减中位 %.3f s   音符数 %d" % (k+1, d[0], d[1]))
        _ci = -1 if sum(1 for _v in (_pm, _md, _op) if _v >= 10) >= 3 else 1
        if _ci >= len(ds): _ci = -1
        _d0, _dc = ds[0][3][0], ds[_ci][3][0]
        _dif = _d0 - _dc
        print("         第 1 段（主奏法）%.3f s  −  第 %d 段（对比段）%.3f s  =  %+.3f s"
              % (_d0, ds[_ci][0]+1, _dc, _dif))
        if _dif <= -0.05:
            print("         -> 主奏法段衰减明显更快 OK")
        elif _dif <= 0.03:
            print("         -> 两段衰减接近 —— 参考曲本身对比就不强，继续即可")
        else:
            problems.append("第 1 段（主奏法）衰减比对比段还慢 %+.3f s" % _dif)
            suggests.append("先确认一遍：参考曲里真的有闷音吗？（spec 里记的是 %.0f%%）" % _pm)
            suggests.append("  有 -> 第 1 段要真的闷住：手掌外侧压在琴桥前面的弦上，")
            suggests.append("        声音是短促的 哒哒哒，不是延音很长的 当当当")
            suggests.append("  没有 -> **去问用户**「这首歌有闷音吗」，他说有再跑 "
                            "technique.py --main=palm --alt=mid --alt-sec=秒（新口径）；")
            suggests.append("          改完重跑 di_instructions.py —— 【不要硬去闷】，也不许自己替用户下结论")
            suggests.append("          （奏法和调弦一样是【输入】：这条链的实测覆盖率只有 17%）")
    else:
        print("         段数不足（%d 段），无法自参照" % len(ds))
        suggests.append("确保每段之间完全停手 1 秒，让系统能自动分段")

print()
print("=" * 62)
if not problems:
    print("  通过。")
    # ★ suggests 以前只在失败分支打印 —— 于是"通过路径上产生的提醒"（例如调性对不上、
    #   调弦没经用户确认）会被静默丢掉：一个音级完全不对的 DI 也能打出「通过。」然后进 meas_prep。
    if suggests:
        print("  但有 %d 条提醒（不拦你，但别忽略）:" % len(suggests))
        for s in suggests: print("    " + s)
    print("  下一步：  $PkgRoot\\tone.bat run meas_prep.py")
else:
    print("  需要重录：")
    for i, p in enumerate(problems, 1): print("    %d) %s" % (i, p))
    print()
    print("  怎么改：")
    for s in suggests: print("    · %s" % s)
    print()
    print("  ★ 如果问题跟调弦/指法有关，重新生成指令：")
    print("      $PkgRoot\\tone.bat run di_instructions.py")
print("=" * 62)
sys.exit(0 if not problems else 1)
