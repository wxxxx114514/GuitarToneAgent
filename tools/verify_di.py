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
from songlib import song_dir, file_args, P, load_mono, db, technique_descriptor

NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
TUNINGS = {
    "standard":  {6:40, 5:45, 4:50, 3:55, 2:59, 1:64},
    "drop_d":    {6:38, 5:45, 4:50, 3:55, 2:59, 1:64},
    "half_down": {6:39, 5:44, 4:49, 3:54, 2:58, 1:63},
    "drop_c":    {6:36, 5:43, 4:48, 3:53, 2:57, 1:62},
}

D = song_dir()
argv = file_args()
name = argv[0] if argv else "palm_di.wav"
DI = P(D, "di") / name
if not DI.exists():
    print("找不到 DI: %s" % DI); sys.exit(2)
spec = json.load(open(P(D, "spec"), encoding="utf-8")) if P(D, "spec").exists() else {}
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
if rms < -50:
    problems.append("几乎没声音（RMS %.0f dBFS）" % rms)
    suggests.append("检查：吉他插上了吗？声卡输入增益开了吗？")
elif pk > -0.5:
    problems.append("爆音了（峰值 %.1f dBFS）" % pk)
    suggests.append("把声卡输入增益调小，重新录")
else:
    print("  [OK] 电平正常")

if dur < 15:
    problems.append("太短（%.0f 秒，需要 25 秒左右）" % dur)
    suggests.append("按指令把三段都录完")

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
    """★ 调用 songlib 里钉死的描述子，不要在这里重新实现"""
    seg = x[int(s0*sr):int(s1*sr)]
    if len(seg) < 8192: return None
    a, b = technique_descriptor(seg, sr)
    return None if (a != a) else (a, b)   # a != a 即 NaN
# ③ 音高 / 调弦
f0, _, _ = librosa.pyin(x, fmin=60, fmax=400, sr=sr, frame_length=4096, hop_length=512)
ok = ~np.isnan(f0)
if ok.sum() >= 10:
    m = np.round(69 + 12*np.log2(f0[ok]/440.0)).astype(int)
    ww = np.zeros(12)
    for mm in m: ww[mm % 12] += 1
    ww /= ww.sum()
    print()
    print("  [音高] " + "  ".join("%s %.0f%%" % (NAMES[k], 100*ww[k]) for k in np.argsort(-ww)[:4]))
    want = spec.get("key", "E")
    if NAMES[int(np.argmax(ww))] == want:
        print("         主音 %s，跟这首歌一致 OK" % want)
    else:
        problems.append("主音是 %s，但应为 %s" % (NAMES[int(np.argmax(ww))], want))

    tune = spec.get("tuning", "standard")
    chords = spec.get("chords_from_bass") or [want + "5"]
    root = "".join(c for c in chords[0] if c in "ABCDEFG#")
    exp = 36 + NAMES.index(root)
    got = int(np.argmax(ww))
    print("  [调弦] spec 记的是 %s，期望根音 %s" % (tune, root))
    if got != exp % 12:
        hit = False
        for tn, op in TUNINGS.items():
            if tn == tune: continue
            nf = exp - TUNINGS[tune][6]
            if (op[6] + nf) % 12 == got:
                problems.append("听起来用的是【%s】而不是 %s" % (tn, tune))
                suggests.append("把 spec.json 的 tuning 改成 %s，再跑 di_instructions.py 重新出指法" % tn)
                hit = True; break
        if not hit:
            problems.append("测到的主音 %s 跟期望的 %s 对不上" % (NAMES[got], root))

# ④ 奏法：自参照
print()
print("  [奏法] 自参照检查（拿你的闷音段跟你的开放段比）")
ds = [(k, a, b, desc(a, b)) for k, (a, b) in enumerate(segs)]
ds = [(k,a,b,d) for k,a,b,d in ds if d]
if len(ds) >= 2:
    for k, a, b, d in ds:
        print("         第 %d 段  低频占比 %5.1f%%   重心 %5.0f Hz" % (k+1, d[0], d[1]))
    first = ds[0][3][0]; last = ds[-1][3][0]
    diff = first - last
    print("         第 1 段 − 最后一段 = %+.1f 个百分点" % diff)
    if diff >= 8:
        print("         -> 闷音段明显更厚 OK")
    elif diff >= 3:
        print("         -> 有区别但不够明显（建议手掌再压紧一点）")
    else:
        problems.append("闷音段跟开放段几乎没区别（%+.1f 个百分点）" % diff)
        suggests.append("第 1 段要真的闷住：手掌外侧压在琴桥前面的弦上，")
        suggests.append("声音应该是短促的 哒哒哒，不是延音很长的 当当当")
        suggests.append("如果本来就不会闷音，可以把第 1 段改成普通拨弦，")
        suggests.append("但要告诉我 —— 那样目标就得跟着改，不能照闷音曲线调")
else:
    print("         段数不足（%d 段），无法自参照" % len(ds))
    suggests.append("确保每段之间完全停手 1 秒，让系统能自动分段")

print()
print("=" * 62)
if not problems:
    print("  通过。")
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
