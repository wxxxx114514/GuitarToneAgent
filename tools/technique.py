"""奏法分析：测出参考曲里各奏法的占比
   两个描述子（§7.1）：低频段(100-450Hz)占比 + 频谱重心
用法:  python technique.py [歌曲目录]
输出:  更新 <歌曲目录>/spec.json 的 technique 字段
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from songlib import song_dir, P, require, load_mono, db, technique_descriptor_frames, DESC_RECIPE

D = song_dir()
g = require(P(D, "guitar"), "吉他轨")
x, sr = load_mono(g)
print("歌曲目录: %s   吉他轨 %.1f s" % (D, len(x)/sr))

# ★ 用 songlib 里钉死的配方（不要在这里重新实现）
t_arr, lof_arr, cen_arr = technique_descriptor_frames(x, sr)
frames = list(zip(t_arr, lof_arr, cen_arr))
if not frames:
    print("没有有效帧"); sys.exit(1)
t = np.array([a for a,_,_ in frames])
lof = np.array([b for _,b,_ in frames])
cen = np.array([c for _,_,c in frames])
print("有效帧 %d 个" % len(frames))
print()
print("=== 描述子分布 ===")
print("  低频段(100-450Hz)占比:  中位 %.1f%%   p10 %.1f   p90 %.1f" % (np.median(lof), np.percentile(lof,10), np.percentile(lof,90)))
print("  频谱重心:               中位 %.0f Hz  p10 %.0f   p90 %.0f" % (np.median(cen), np.percentile(cen,10), np.percentile(cen,90)))
print()
print("=== 参考基准（实测，用于分类）===")
print("  闷音     低频占比 28.8%    重心 1621 Hz")
print("  开放弦   低频占比 11.4%    重心 2000 Hz")

# 分类：用低频占比 + 重心
#   闷音 = 低频占比高 且 重心低
#   开放 = 低频占比低
LAB = []
for b, c in zip(lof, cen):
    if b > 22 and c < 1800: LAB.append("闷音")
    elif b < 15 and c > 1800: LAB.append("开放")
    else: LAB.append("中间")
from collections import Counter
cnt = Counter(LAB)
n = len(LAB)
print()
print("=== 奏法占比 ===")
for k in ["闷音","中间","开放"]:
    v = cnt.get(k, 0)
    print("  %-4s %5d 帧 (%4.1f%%)  %s" % (k, v, 100*v/n, "#"*int(60*v/n)))

# 时间轴（每 20 秒一段）
print()
print("=== 分段占比（每 20 秒）===")
for t0 in range(0, int(len(x)/sr)-20, 20):
    m = (t >= t0) & (t < t0+20)
    if m.sum() < 5: continue
    c2 = Counter([LAB[i] for i in np.where(m)[0]])
    s2 = sum(c2.values())
    print("  %4d-%4d s   闷音 %4.0f%%   中间 %4.0f%%   开放 %4.0f%%"
          % (t0, t0+20, 100*c2.get("闷音",0)/s2, 100*c2.get("中间",0)/s2, 100*c2.get("开放",0)/s2))

# 写回 spec

# ★ 锚点由当前实现测得 —— 数字必须挂在实现版本上，不能是裸的百分数
print()
print("=== 锚点（由 songlib.technique_descriptor() 于 %s 测得）===" % DESC_RECIPE["recipe_version"])
for k in ["闷音", "中间", "开放"]:
    idx = [i for i, L in enumerate(LAB) if L == k]
    if not idx: continue
    fl = np.median(lof[idx]); cl = np.median(cen[idx])
    print("  %-4s n=%4d   低频占比 %5.1f%%   质心 %5.0f Hz" % (k, len(idx), fl, cl))
print()
print("  分类阈值: 低频>22% 且 质心<1800 -> 闷音；低频<15% 且 质心>1800 -> 开放")
print("  (阈值也是锚点的一部分，换实现要一起重新标定)")

sp = P(D, "spec")
spec = json.load(open(sp, encoding="utf-8")) if sp.exists() else {}
spec["technique"] = {
    "palm_pct": round(100*cnt.get("闷音",0)/n, 1),
    "mid_pct":  round(100*cnt.get("中间",0)/n, 1),
    "open_pct": round(100*cnt.get("开放",0)/n, 1),
    "lowmid_median_pct": round(float(np.median(lof)), 1),
    "centroid_median_hz": round(float(np.median(cen))),
}
json.dump(spec, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print()
print("已更新 %s" % sp)
print()
print(">>> 下一步：按这个占比让用户录 DI（见 Skill §9.1 路径 A）")
