"""感知距离度量：用耳朵的特性代替耳朵本身

代替旧指标（13段频谱 RMS）的四个改进：
  1. 1/6 倍频程分辨率（旧的是 1/3）→ 能看见共振
  2. ERB 尺度 + 频率相关 JND 加权 → 匹配耳朵的分辨率
  3. 掩蔽门限 → 被盖住的差异不计分
  4. 平滑度惩罚 + 时间包络 → 抓"电音感"和混响/动态
"""
import numpy as np

# --- 频率相关的最小可觉差（dB），简化模型 ---
def jnd_db(f):
    """500Hz-5kHz 约 0.7dB；低频和高频变差；这是保守估计"""
    f = np.asarray(f, dtype=float)
    j = np.ones_like(f)*0.7
    lo = f < 500
    j[lo] = 0.7 + 1.6*np.log10(500/np.maximum(f[lo], 20))
    hi = f > 5000
    j[hi] = 0.7 + 1.2*np.log10(np.maximum(f[hi], 1)/5000)
    return np.clip(j, 0.7, 4.0)

# --- 绝对听阈（近似 ISO 226，dB SPL）---
def threshold_db(f):
    f = np.asarray(f, dtype=float)
    return (3.64*(f/1000)**-0.8 - 6.5*np.exp(-0.6*(f/1000-3.3)**2)
            + 1e-3*(f/1000)**4)

def bands_6th(fmin=50, fmax=16000, per_oct=6):
    r = 2**(1/per_oct)
    out, f = [], fmin
    while f < fmax:
        out.append((f, f*r)); f *= r
    return out

def avg_spectrum(x, sr, t0=0.0, t1=None):
    """1/6 倍频程平均功率谱"""
    t1 = t1 if t1 is not None else len(x)/sr
    x = x[int(t0*sr):int(t1*sr)]
    N = 16384; HOP = 8192
    acc = np.zeros(N//2+1); c = 0
    for s in range(0, max(1, len(x)-N), HOP):
        acc += np.abs(np.fft.rfft(x[s:s+N]*np.hanning(N)))**2; c += 1
    sp = acc/max(c,1); f = np.fft.rfftfreq(N, 1/sr)
    B = bands_6th()
    fc = np.array([np.sqrt(a*b) for a,b in B])
    v = np.array([10*np.log10(sp[(f>=a)&(f<b)].sum()+1e-30) for a,b in B])
    return fc, v

def envelope_stats(x, sr, hop_ms=10):
    hop = int(sr*hop_ms/1000); n = len(x)//hop
    e = np.array([np.sqrt((x[i*hop:(i+1)*hop].astype(np.float64)**2).mean()) for i in range(n)])
    edb = 20*np.log10(np.maximum(e, 1e-10))
    p95, p50, p10 = np.percentile(edb, 95), np.percentile(edb, 50), np.percentile(edb, 10)
    return {"peak_db": p95, "mid_db": p50, "floor_db": p10, "range_db": p95 - np.percentile(edb, 15)}

def perceptual_distance(ref, test, sr, verbose=False):
    """返回总差异分数 + 分项。分数单位≈JND，越小越好。"""
    fc, R = avg_spectrum(ref, sr); _, T = avg_spectrum(test, sr)
    # 电平对齐（只比形状）
    T = T - (T.mean() - R.mean())
    # --- 掩蔽门限：参考自身能量扩散后，低于它的差异不算 ---
    # 简化：用参考谱的滑动最大值 - 25 dB 作为门限
    from numpy import maximum
    k = np.ones(7)/7
    ref_smooth = np.convolve(R, k, "same")
    mask_thr = ref_smooth - 25.0
    audible = (R > mask_thr) | (T > mask_thr)
    # --- 听阈门限 ---
    thr = threshold_db(fc) - 100.0     # 换算到 dBFS 量级（粗略）
    audible &= (np.maximum(R, T) > thr)
    # --- JND 归一 ---
    d = (T - R) / jnd_db(fc)
    d_masked = np.where(audible, d, 0.0)
    rms_jnd = float(np.sqrt((d_masked**2).mean()))
    max_jnd = float(np.abs(d_masked).max())
    # --- 平滑度：测试谱的二阶差分（共振/梳状响应会很大）---
    def ripple(v):
        vv = v - np.convolve(v, np.ones(5)/5, "same")
        return float(np.sqrt((np.diff(vv, 2)**2).mean()))
    rip_t, rip_r = ripple(T), ripple(R)
    rip_pen = max(0.0, rip_t - rip_r)
    # --- 时间包络 ---
    er, et = envelope_stats(ref, sr), envelope_stats(test, sr)
    env_pen = abs(er["range_db"] - et["range_db"]) * 0.15
    total = rms_jnd + rip_pen*1.0 + env_pen
    out = dict(total=total, rms_jnd=rms_jnd, max_jnd=max_jnd,
               ripple_t=rip_t, ripple_r=rip_r, ripple_pen=rip_pen,
               range_ref=er["range_db"], range_test=et["range_db"], env_pen=env_pen,
               n_bands=len(fc), n_audible=int(audible.sum()))
    if verbose:
        print("    %8s %9s %9s %8s %8s" % ("频率","参考","测试","差dB","JND"))
        for i in range(0, len(fc), 2):
            flag = "" if audible[i] else "  (掩蔽)"
            print("    %7.0f Hz %9.1f %9.1f %+8.2f %8.2f%s" % (fc[i], R[i], T[i], T[i]-R[i], d[i], flag))
    return out
