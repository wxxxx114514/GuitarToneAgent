"""频谱误差指标套件（内容相同前提）
   修正：1) 对齐搜索范围允许 ±；2) 先做响度归一化再比较
"""
import numpy as np, librosa

def rms_norm(x, target_db=-20.0):
    r = np.sqrt((x.astype(np.float64)**2).mean())
    if r < 1e-12: return x
    return (x * (10**(target_db/20)/r)).astype(np.float32)

def align_pair(ref, x, sr, max_lag_ms=60):
    """在 ±max_lag_ms 范围内用互相关对齐，返回 (对齐后的 cand, lag)"""
    ml = int(max_lag_ms/1000*sr)
    n = min(len(ref), len(x))
    a = ref[:n].astype(np.float64)
    an = np.sqrt((a**2).sum())
    def take(lag):
        if lag >= 0:
            seg = x[lag:lag+n]
        else:
            seg = np.concatenate([np.zeros(-lag, np.float32), x[:max(0, n+lag)]])
        if len(seg) < n:
            seg = np.concatenate([seg, np.zeros(n-len(seg), np.float32)])
        return seg[:n]
    best, bc = 0, -1e9
    for lag in range(-ml, ml+1):
        s = take(lag).astype(np.float64)
        sn = np.sqrt((s**2).sum())
        if sn < 1e-12: continue
        c = float(np.dot(a, s))/(an*sn)
        if c > bc: bc, best = c, lag
    return take(best).astype(np.float32), best, bc

def spectral_metrics(ref, cand, sr, n_fft=2048, hop=512, n_mels=128, n_mfcc=20, normalize=True):
    if normalize:
        ref = rms_norm(ref); cand = rms_norm(cand)
    X = librosa.stft(ref.astype(np.float32), n_fft=n_fft, hop_length=hop, win_length=n_fft)
    Y = librosa.stft(cand.astype(np.float32), n_fft=n_fft, hop_length=hop, win_length=n_fft)
    Ax, Ay = np.abs(X), np.abs(Y)
    T = min(Ax.shape[1], Ay.shape[1]); Ax, Ay = Ax[:, :T], Ay[:, :T]
    Lx = 20*np.log10(Ax + 1e-8); Ly = 20*np.log10(Ay + 1e-8)
    energy = (Ax**2).sum(0)
    mask = energy > energy.max()*10**(-40/10)
    if mask.sum() < 10: mask = np.ones(T, bool)
    out = {}
    out["LSD"] = float(np.sqrt(np.mean((Lx[:, mask]-Ly[:, mask])**2)))
    Mx = librosa.feature.melspectrogram(S=Ax**2, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=n_mels)
    My = librosa.feature.melspectrogram(S=Ay**2, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=n_mels)
    Lmx, Lmy = np.log(Mx+1e-8), np.log(My+1e-8)
    out["LogMelMSE"] = float(np.mean((Lmx[:, mask]-Lmy[:, mask])**2))
    Cx = librosa.feature.mfcc(S=librosa.power_to_db(Mx), n_mfcc=n_mfcc)
    Cy = librosa.feature.mfcc(S=librosa.power_to_db(My), n_mfcc=n_mfcc)
    d = Cx[:, mask]-Cy[:, mask]
    out["MCD"] = float(np.mean((10/np.log(10))*np.sqrt(2*np.sum(d[1:]**2, axis=0))))
    out["SC"] = float(np.linalg.norm(Ax-Ay,"fro")/(np.linalg.norm(Ax,"fro")+1e-8))
    tot = 0.0
    for nf in (512, 1024, 2048, 4096):
        Xs = np.abs(librosa.stft(ref.astype(np.float32), n_fft=nf, hop_length=nf//4, win_length=nf))
        Ys = np.abs(librosa.stft(cand.astype(np.float32), n_fft=nf, hop_length=nf//4, win_length=nf))
        t2 = min(Xs.shape[1], Ys.shape[1]); Xs, Ys = Xs[:, :t2], Ys[:, :t2]
        tot += np.linalg.norm(Xs-Ys,"fro")/(np.linalg.norm(Xs,"fro")+1e-8)
        tot += np.mean(np.abs(np.log(Xs+1e-8)-np.log(Ys+1e-8)))
    out["MultiRes"] = float(tot)
    return out