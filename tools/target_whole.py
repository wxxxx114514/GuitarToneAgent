"""全曲目标曲线（从分离后的吉他轨）
用法:  python target_whole.py [歌曲目录]        或设 $env:SONG_DIR
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import song_dir, P, require, load_mono, envelope, FC, BANDS, db, CH_LAST

D = song_dir()

# ── --drop=a-b：用【其中一段】算目标（默认全曲）──────────────────────────
#   ★ 为什么需要它：评审给的可行动判据是「把这段剔掉，目标动多少 dB」——
#     动 0.09 dB 就远小于可行动空间 0.62，说明【那段不重要、别问用户】。
#     而没有这个参数时，就算用户答了「用 20 秒之后」，代码里也没有任何东西能消费它。
#   ★ 默认值是什么都不做 —— 去掉哪一段本来就不重要，不该由工具偷偷决定。
DROP = None
for _a in sys.argv[1:]:
    if _a.startswith("--drop="):
        try:
            _s, _e = _a.split("=", 1)[1].split("-")
            DROP = (float(_s), float(_e))
        except Exception:
            print("!! --drop 要给 起-止 秒（例如 --drop=0-20）"); sys.exit(2)
g = require(P(D, "guitar"), "吉他轨")
x, sr = load_mono(g)
print("歌曲目录: %s" % D)
print("吉他轨  : %s  %.1f s  %d Hz" % (g.name, len(x)/sr, sr))

# ★ 声道决策落盘：只有【两把琴】时才要用户指定用哪一把（target_channel = L/R）；
#   同一把琴双轨时取平均是对的。判据与证据都记下来，别让它只活在屏幕上。
_ch = CH_LAST.get(str(g)) or {}
if _ch:
    import json as _json
    _sp = P(D, "spec")
    if _sp.exists():
        _spec = _json.load(open(_sp, encoding="utf-8-sig"))
        _spec["target_channel"] = "mono" if _ch.get("decision") == "mono" else "ask"
        _spec["channel_check"] = _ch
        _tmp = str(_sp) + ".tmp"
        _json.dump(_spec, open(_tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(_tmp, _sp)
        print("声道决策: %s（chroma 余弦最低 %s / 包络差中位 %s dB）"
              % (_spec["target_channel"], _ch.get("chroma_cos_min"), _ch.get("env_diff_rms_db")))

cur = envelope(x, sr)
out = P(D, "target")
np.save(out, np.vstack([np.array(FC), cur]))

print()
print("=== 全曲目标曲线（13 频段，相对）===")
for k, fc in enumerate(FC):
    print("  %6d Hz  %+6.2f" % (fc, cur[k]))
print()
print("已保存 %s" % out)

# 分段一致性自检
# ★ 这个数【不是复数音色探测器】—— 评审用真素材证过（同一份 DI 过两个真预设、差 1.56 dB，
#   各铺 6 段 20 秒拼成一首歌：逐段只有 0.78，而真·单音色的 BlackShout 是 0.84，
#   【两种音色的歌反而更"一致"】）。机理：段偏差 = 段 vs 全曲均值，换音色的那 f 比例段
#   偏差只有 (1-f)·D，把音色差折半了。内容起伏（0.84~2.5）本来就比音色差（0.86~1.56）大。
#   所以这里只【如实报告】：给每段加电平列 + 一行"这里没吉他"的参考，不下判断。
print()
print("=== 段间一致性（每 20 秒）· 只报告，不下判断 ===")
seg = 20
_units = [(t0, x[int(t0*sr):int((t0+seg)*sr)]) for t0 in range(0, max(int(len(x)/sr) - seg, 1), seg)]
devs, _rms = [], []
for t0, y in _units:
    d = envelope(y, sr) - cur
    devs.append((t0, float(np.sqrt((d**2).mean()))))
    _rms.append(float(np.sqrt((y.astype(np.float64)**2).mean())))
_med_rms = float(np.median(_rms)) if _rms else 0.0
for (t0, r), rms in zip(devs, _rms):
    tag = ""
    if _med_rms > 0 and db(rms) < db(_med_rms) - 30.0:
        tag = "   <- 本段基本没吉他（比中位低 %.0f dB）：这个偏差不代表音色" % (db(_med_rms) - db(rms))
    print("  %4d-%4d s   %5.2f dB   RMS %6.1f dBFS%s" % (t0, t0 + seg, r, db(rms), tag))
if devs:
    arr = np.array([r for _, r in devs])
    print("  中位 %.2f dB  p90 %.2f dB  最大 %.2f dB（%d s）· %d 段"
          % (np.median(arr), np.percentile(arr, 90), arr.max(), devs[int(np.argmax(arr))][0], len(arr)))
    _left = len(x) / sr - (devs[-1][0] + seg)
    if _left > 0.5:
        print("  ★ 末段只剩 %.1f 秒（不足 %d 秒），没有计入 —— 不是漏了" % (_left, seg))
    print("  参考：20 秒【数字静音】在这个量上也有 %.2f dB（= 目标向量自身的范数），"
          % float(np.sqrt((cur**2).mean())))
    print("        所以单独一个大数说明不了任何事 —— 要看它是不是「这里没吉他」")

# ★ 可行动判据（用【可行动空间】当单位，不当阈值 —— 没有自由参数）：
#   「把最异常的那段剔掉，目标动多少？」远小于 0.62 dB 就是"这段不重要，别去打扰用户"。
if len(devs):
    _w = int(np.argmax([r for _, r in devs])); _t0 = devs[_w][0]
    _keep = np.concatenate([x[:int(_t0*sr)], x[int((_t0+seg)*sr):]]) if _t0 > 0 else x[int((_t0+seg)*sr):]
    if len(_keep) > sr:
        _d = envelope(_keep, sr) - cur
        _m = float(np.sqrt((_d**2).mean()))
        print("  剔掉最异常那一段（%d-%d s）后，目标移动 %.2f dB（最大 %.2f）—— %s"
              % (_t0, _t0 + seg, _m, float(np.abs(_d).max()),
                 "远小于可行动空间 0.62 dB -> 这段不重要，不用问用户" if _m < 0.62
                 else "已超过可行动空间 0.62 dB -> 值得看一眼那一段（要改就用 --drop= 明示）"))

# ── --drop 生效：用指定的一段重算目标并覆盖（事实落盘，不落判据）────────
if DROP:
    a, b = DROP
    _y = x[int(a*sr):int(b*sr)]
    if len(_y) < sr:
        print("!! --drop=%.0f-%.0f 太短（不足 1 秒）" % (a, b)); sys.exit(2)
    _new = envelope(_y, sr)
    np.save(out, np.vstack([np.array(FC), _new]))
    _sp = P(D, "spec")
    if _sp.exists():
        import json as _json
        _s = _json.load(open(_sp, encoding="utf-8-sig"))
        _s["target_scope"] = "%.0f-%.0f" % (a, b)   # ★ 落【事实】：实际用了哪一段
        _tmp = str(_sp) + ".tmp"
        _json.dump(_s, open(_tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(_tmp, _sp)
    print()
    print("已按 --drop=%.0f-%.0f 重算目标并覆盖 %s（spec.target_scope 已记）" % (a, b, out))
    for k, fc in enumerate(FC):
        print("  %6d Hz  %+6.2f" % (fc, _new[k]))
