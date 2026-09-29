"""【参考工具】合成闷音强力和弦 DI —— 仅供参考，权重低

   ⚠️ 定位（重要）：
      ✗ 不作为定 EQ 的依据
      ✓ 流程验证 / 交叉参考 / 粗筛

   为什么不能当依据（实测）：
      低频占比   合成 7.0%   vs   真实录音 97.1%
      闭环会拿 EQ 去补偿这个差异 → 那个补偿是在修合成器，不是修音色
      换成真实 DI 时，预设就偏了

   为什么偏亮：Karplus-Strong 的激励是白噪声（频谱平坦），低通只做 2 次；
              而衰减对所有谐波一视同仁 —— 真实闷音是手掌压弦，高次泛音
              从起音就被抑制。把低通提到 120 次才到 25.8%，但那是凑参数。

   用法:  python gen_palm_di.py [歌曲目录]   （读 spec.json 的调性/和弦）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from songlib import song_dir, file_args, P

SR = 48000
NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
def base_freq(name):
    """音名 -> 该音在低八度的频率（E -> 82.407, B -> 123.471 ...）"""
    i = NAMES.index(name)
    midi = 40 + i          # E2 = MIDI 40
    return 440.0 * 2**((midi-69)/12.0)

D = song_dir()
sp = P(D, "spec")
roots = []
argv = file_args()
if len(argv) > 0:
    roots = [float(v) for v in argv[0].split(",")]
elif sp.exists():
    spec = json.load(open(sp, encoding="utf-8"))
    names = []
    for c in spec.get("chords", [])[:2]:
        n = "".join(ch for ch in c if ch in "ABCDEFG#")
        if n and n not in names: names.append(n)
    for n in names:
        roots += [base_freq(n), base_freq(n)*2]
if not roots:
    print("推不出根音。请在 spec.json 里填 chords，或命令行给频率：")
    print('  python gen_palm_di.py "82.4,123.5,164.8,246.9"    （或 --song=<目录> 指定歌曲）')
    sys.exit(2)

print("歌曲目录: %s" % D)
print("根音: %s" % ", ".join("%.1f" % f for f in roots))

rng = np.random.default_rng(20250928)
def note(freq, dur, decay, amp=1.0, bright=2, pick=0.12):
    N = max(4, int(round(SR/freq)))
    buf = rng.uniform(-1,1,N).astype(np.float64)
    for _ in range(bright): buf = 0.5*(buf + np.roll(buf,1))
    n = int(dur*SR); out = np.zeros(n); idx = 0
    for i in range(n):
        nx = (idx+1) % N; out[i] = buf[idx]
        buf[idx] = decay*(0.5*buf[idx] + 0.5*buf[nx]); idx = nx
    a = int(0.004*SR)
    out[:a] += pick*rng.uniform(-1,1,a)*np.linspace(1,0,a)
    f = int(0.01*SR); out[-f:] *= np.linspace(1,0,f)
    return amp*out

def chord(root, dur, decay, amp=1.0):
    m = int(dur*SR); o = np.zeros(m)
    for fq, a in [(root,1.0),(root*2**(7/12),0.85),(root*2.0,0.5)]:
        xx = note(fq, dur, decay, amp=a); o[:len(xx)] += xx[:m]
    return amp*o

def chug(root, hits, interval, decay, dur=0.30):
    total = int((hits*interval + dur + 0.15)*SR); o = np.zeros(total)
    for k in range(hits):
        c = chord(root, dur, decay, amp=(1.0 if k%3==0 else 0.78))
        s = int(k*interval*SR); o[s:s+len(c)] += c[:max(0,len(o)-s)]
    return o

sil = lambda t: np.zeros(int(t*SR))
DECAY_LOW = 0.885; F0 = 82.407
parts = [sil(0.5)]; marks = {}; t = 0.5
for f in roots:
    decay = DECAY_LOW ** (F0/f)
    seg = chug(f, hits=12, interval=0.25, decay=decay)
    a, b = t, t+len(seg)/SR
    marks["%.1fHz" % f] = [a, b]
    parts += [seg, sil(0.5)]; t = b+0.5
    print("  %7.1f Hz   %.2f - %.2f s" % (f, a, b))

sig = np.concatenate(parts); pk = np.abs(sig).max()
sig = sig/pk*(10**(-12/20))
out = P(D, "di") / "palm_di.wav"
out.parent.mkdir(parents=True, exist_ok=True)
sf.write(str(out), sig.astype(np.float32), SR, subtype="PCM_24")
json.dump({"silence":[0,0.5], **marks}, open(str(P(D,"di")/"palm_di_marks.json"),"w"), indent=2)
print()
print("已写 %s  (%.2f s, 峰值 %.1f dBFS)" % (out, len(sig)/SR, 20*np.log10(np.abs(sig).max())))
