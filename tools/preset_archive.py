"""预设归档：按【曲风】索引试过的预设 —— 供【复盘】查（见 08-工作流详解.md §9.0.6）

它是什么：**一份记录**（哪个预设、在哪首歌、什么曲风、残差多少），供人复盘与写笔记用。
★ 它【不是】起点预设的来源：起点由 synth_start.py 从设备规格表 + 经典配置组出来，
  不查归档、也不挑现成预设（见 08-工作流详解.md §9.0.5）。
agent 只能退回去抓一个它在文档里见过的预设名 —— 那就是"默认预设总是 J900"的根。

用法:
  python preset_archive.py list                     全部
  python preset_archive.py categories               有哪些曲风
  python preset_archive.py query <曲风>             该曲风下试过的，按残差升序
  python preset_archive.py add <预设名> <歌名> <残差> [曲风,曲风]

路径: 环境变量 PRESET_ARCHIVE，默认 <包根>/presets_archive.json
      （包根在沙箱里可能是只读的，那就设 PRESET_ARCHIVE 指到可写的地方）
"""
import sys, os, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PATH = os.environ.get("PRESET_ARCHIVE") or os.path.join(ROOT, "presets_archive.json")


def load():
    if not os.path.exists(PATH):
        return {"version": 1, "presets": {}}
    with open(PATH, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("version", 1); d.setdefault("presets", {})
    return d


def save(d):
    try:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("!! 写不进归档: %s" % e)
        print("   包根可能是只读的。设一个可写路径再试：")
        print("   $env:PRESET_ARCHIVE = \"<某个可写目录>\\presets_archive.json\"")
        sys.exit(1)
    return PATH


def record(preset, song, residual, category=None, after_eq=None,
           error_13band=None, solved_eq=None, params=None, di=None, date=None):
    """测完自动调这个 —— 归档是测量流程的副产品，不用专门做一步。"""
    d = load()
    p = d["presets"].setdefault(preset, {"category": [], "params": {}, "sessions": []})
    for c in (category or []):
        if c and c not in p["category"]:
            p["category"].append(c)
    if params: p["params"] = params
    sess = {"song": song, "residual": round(float(residual), 3),
            "date": date or datetime.date.today().isoformat()}
    if after_eq is not None: sess["after_eq"] = round(float(after_eq), 3)
    if di: sess["di"] = di
    if error_13band is not None: sess["error_13band"] = [round(float(v), 2) for v in error_13band]
    if solved_eq is not None: sess["solved_eq"] = [round(float(v), 2) for v in solved_eq]
    # 同一首歌已有记录就覆盖，否则追加
    p["sessions"] = [s for s in p["sessions"] if s.get("song") != song] + [sess]
    save(d)
    return sess


def query(cat):
    """-> [(预设名, 歌名, 残差)]，按残差升序"""
    rows = []
    for name, p in load()["presets"].items():
        if cat not in p.get("category", []):
            continue
        for s in p.get("sessions", []):
            rows.append((name, s.get("song"), s.get("residual")))
    rows.sort(key=lambda r: (r[2] is None, r[2]))
    return rows


def main(argv):
    cmd = argv[0] if argv else "list"
    d = load()
    if cmd == "list":
        print("归档: %s" % PATH)
        if not d["presets"]: print("  （空）"); return 0
        for name, p in sorted(d["presets"].items()):
            cats = ",".join(p.get("category", [])) or "-"
            print("  %-22s [%s]" % (name, cats))
            for s in p.get("sessions", []):
                print("      %-14s 残差 %s dB%s  %s" % (
                    s.get("song"), s.get("residual"),
                    ("  解 EQ 后 %s" % s["after_eq"]) if "after_eq" in s else "",
                    s.get("date", "")))
    elif cmd == "categories":
        cs = {}
        for p in d["presets"].values():
            for c in p.get("category", []): cs[c] = cs.get(c, 0) + 1
        print("归档: %s" % PATH)
        for c, n in sorted(cs.items(), key=lambda z: -z[1]):
            print("  %-16s %d 个预设" % (c, n))
        if not cs: print("  （还没有曲风标签）")
    elif cmd == "query":
        if len(argv) < 2: print("用法: query <曲风>"); return 2
        rows = query(argv[1])
        if not rows:
            print("归档里没有【%s】的记录（这只是记录，不是起点来源）" % argv[1])
            return 0
        print("【%s】试过的（按残差升序）:" % argv[1])
        for name, song, res in rows:
            print("  %-22s %-14s %s dB" % (name, song, res))
    elif cmd == "add":
        if len(argv) < 4: print("用法: add <预设名> <歌名> <残差> [曲风,曲风]"); return 2
        cats = argv[4].split(",") if len(argv) > 4 else []
        s = record(argv[1], argv[2], argv[3], category=cats)
        print("已记录 %s / %s -> %s dB" % (argv[1], argv[2], s["residual"]))
        print("  归档: %s" % PATH)
    else:
        print(__doc__); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))