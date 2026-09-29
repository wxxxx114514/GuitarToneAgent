"""按参考曲的分析结果，生成【给小白看的】录音指令
   不出现任何乐理词汇——只给：第几弦、第几品、手掌怎么放、弹多久
用法:  python di_instructions.py [歌曲目录]
读:    spec.json（key / chords / technique）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from songlib import song_dir, P

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

def name2midi(n):
    """音名 -> MIDI（第 2 八度。C2 = 36, E2 = 40, B2 = 47）"""
    return 36 + CH_NAME.index(n)

def shape(midi, max_fret=12):
    """找一个最省力的弹法 -> (弦, 品)"""
    best = None
    for s in [6, 5, 4, 3, 2, 1]:
        f = midi - OPEN[s]
        if 0 <= f <= max_fret:
            # 优先低把位
            if best is None or f < best[1]:
                best = (s, f)
    return best

D = song_dir()
sp = P(D, "spec")
if not sp.exists():
    print("缺 spec.json，先跑 chords.py 和 technique.py"); sys.exit(2)
spec = json.load(open(sp, encoding="utf-8"))

TUNE = spec.get("tuning", "standard")
OPEN = TUNINGS.get(TUNE, TUNINGS["standard"])
print("[调弦] %s" % {"standard":"标准 EADGBE", "drop_d":"Drop D (DADGBE)",
                     "half_down":"降半音", "drop_c":"Drop C"}.get(TUNE, TUNE))

key = spec.get("key", "E")
chords = spec.get("chords", [])
tech = spec.get("technique", {})
palm = tech.get("palm_pct", 60)
mid  = tech.get("mid_pct", 25)
opn  = tech.get("open_pct", 15)

# 从和弦名取根音字母
roots = []
for c in chords[:2]:
    n = "".join(ch for ch in c if ch in "ABCDEFG#")
    if n and n not in roots: roots.append(n)
if not roots: roots = [key]

def sec(pct, total=26.0):
    return max(3.0, round(total * pct / 100.0))

t1, t2, t3 = sec(palm), sec(mid), sec(opn)

ORD = {6:"最粗的那根", 5:"第 2 粗的", 4:"第 3 根", 3:"第 4 根", 2:"第 5 根", 1:"最细的那根"}
def pos(s, f):
    if f == 0: return "%s弦（第 %d 弦），什么都不按" % (ORD[s], s)
    return "%s弦（第 %d 弦）第 %d 品" % (ORD[s], s, f)
def shape_candidates(root):
    """返回所有可行的强力和弦按法，每个是 (把位, 描述行列表)
       Drop D 类：6 弦根音 -> 6/5/4 同品；5 弦根音 -> 5/4/3 的 x+2 形
       标准调弦：6 弦 N + 5 弦 N+2"""
    m = name2midi(root)
    s6, s5, s4, s3 = OPEN[6], OPEN[5], OPEN[4], OPEN[3]
    cands = []
    if TUNE in ("drop_d", "drop_c"):
        n = m - s6
        if 0 <= n <= 12:
            cands.append((n, ["第 6、5、4 弦【全部按第 %d 品】" % n,
                              "（一根手指横着压住这三根弦）"
                              if n > 0 else "（这三根弦都是空弦，左手不用按）"]))
        k = m - s5
        if 0 <= k <= 12:
            cands.append((k, [pos(5, k), pos(4, k+2), pos(3, k+2)]))
    else:
        n = m - s6
        if 0 <= n <= 12:
            cands.append((n, [pos(6, n), pos(5, n+2), pos(4, n+2)]))
    # 按把位从低到高排，返回最低的
    cands.sort(key=lambda z: z[0])
    return cands

def show(root):
    c = shape_candidates(root)
    return c[0][1] if c else ["（这个根音在当前调弦下推不出按法）"]

print()
print("=" * 62)
print("   请录一段干声（吉他直接插声卡，中间不要接任何效果器）")
print("=" * 62)
print()
print("总共约 %.0f 秒，分三段。" % (t1+t2+t3))
print("★ 每段之间【完全停手 1 秒】——手离开琴弦，让声音彻底消失")
print("  （系统靠这个静音自动分段，用来检查你每段弹对了没有）")
print()
print("-" * 62)
print("第 1 段   闷音    约 %.0f 秒" % t1)
print("-" * 62)
print("  第一个（弹这个最多）：")
for p in show(roots[0]): print("      . " + p)
if len(roots) > 1:
    print("  第二个（隔一会儿换过去）：")
    for p in show(roots[1]): print("      . " + p)
print()
print("  右手：手掌外侧【轻轻压在琴桥前面】，让声音变成短促的")
print("        \"哒哒哒\"，不是\"当当当\"")
print("        中速连续下拨，大约每秒 4 下")
print()
print("-" * 62)
print("第 2 段   还是闷音，换个位置    约 %.0f 秒" % t2)
print("-" * 62)
alt = [c for c in roots[2:4]] or ["G", "A"]
print("  左手换到：")
for root in alt:
    print("      %s5：" % root)
    for p in show(root): print("        . " + p)
print("  右手跟第 1 段一样，继续闷音连拨")
print()
print("-" * 62)
print("第 3 段   放开手    约 %.0f 秒" % t3)
print("-" * 62)
print("  左手按第 1 段的第一个位置，右手【放开手掌】")
print("  让和弦自然响完，每 2 秒弹一次，弹 3-4 次")
print()
print("=" * 62)
print("  音准不用管，音量也不用管——脚本会自动调整")
print("  录完保存成 wav，放进：%s" % (P(D, "di")))
print("  文件名改成 palm_di.wav")
print("=" * 62)
print()
print("[给 AI 看的] 这一步的依据：")
print("  调性 %s，主要和弦 %s" % (key, ", ".join(chords[:2])))
print("  奏法占比: 闷音 %.0f%% / 中间 %.0f%% / 开放 %.0f%%" % (palm, mid, opn))
print("  这三段的比例就是照着上面配的（内容对齐，见 Skill §7.3）")
