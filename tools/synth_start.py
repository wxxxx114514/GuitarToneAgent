"""从【设备规格表】生成一版【起点预设】

规格来源:  devices/<型号>/parameter_table.json   （规范见 reference/13-两表规范.md）
产物:      <歌曲目录>/start_preset.json  或 --out=<文件>
           + 一张【拧到几】的表（设备没有文件接口、或某个模块的键名对不上时，用户照它手动拧）

用法:
  python synth_start.py <曲风> [--device=<型号>] [--out=<文件>]

三条规矩（都是文档里已有的，这里只是执行）:
  §9.0.5  起点【只开 AMP + CAB + 推子】，其余模块显式关，之后按 §10.8 的 7 步逐个开
  §10.7.3 曲风 -> 经典配置表 -> 箱头家族 / 箱体 / 推子；型号用【名字】去参数表里匹配
  §10.7.4 推子当塑形用: Drive/Gain 低、Level 高、Tone 中位

★ 这里【不读出厂预设库】：从现成预设取中位数 = 把厂商的审美当起点，而且会诱导 agent 去"抄"，
  而本工具要的是"从规格组一版出来"。型号匹配（哪个 Type）不算抄值。

每个值都带【依据】。依据只有三档 + 一条规范:

  doctrine         经典配置明确规定的值（推子的 Gain/Level/Tone 那一类）—— 这是规范，不是兜底
  manual_default   说明书给的默认值
  range_midpoint   范围中点 —— 说明书没写默认值时的兜底，会进"未定项"

落盘三条（由真机导出的预设实测得来）:
  ① 链序【不自编】：保留外壳里的 effectChain（它是变量：实测两份真机文件首元素分别是 4 和 0）
  ② 关闭的模块也要填 Data（设备自己的文件里 Switch=0 的模块照样带完整参数）
  ③ 逐模块判定能不能落盘：表里这个 Type 的键名逐字对得上才自动写；对不上就出「在设备上拧到几」的表
"""
import sys, os, json, re, statistics, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from songlib import utf8_stdout, P, song_dir

utf8_stdout()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 箱头【家族 -> 名字关键词】。这张表就是 08-工作流详解.md §9.0.5「为什么名字能当索引」
# 那张表的代码形态 —— 名字本身就是索引，所以不需要标定"客观特征 -> 家族"。
FAMILIES = {
    "marshall": ["J900", "JCM900", "JCM800", "PLEXI", "JVM", "JTM45", "AFD"],
    "mesa":     ["MARK V", "MARKV", "RECT", "JP2C", "TRIAXIS", "LONESTAR"],
    "peavey":   ["5150", "EVH"],
    "diezel":   ["VH4", "FIREBALL", "INVADER"],
    "soldano":  ["SLO100", "UBER", "ECSTASY", "BE100"],
    "fender":   ["TWIN", "DELUXE", "BASSMAN", "PRINCETON"],
    "vox":      ["AC30", "AC15"],
}

# §10.7.3 经典配置对照表: 曲风 -> 家族 / 箱体 / 推子。家族按优先级排，命中第一个就用它。
DOCTRINE = [
    {"genre": ["metalcore", "metal", "djent", "prog", "现代金属", "金属", "前卫"],
     "family": ["peavey", "diezel", "mesa"], "cab": ["V30"], "boost": ["OD808", "TS9", "TS808", "SD-1"]},
    {"genre": ["anisong", "j-rock", "jrock", "日系", "日摇", "二次元"],
     "family": ["mesa", "marshall"], "cab": ["V30"], "boost": ["TS808", "SD-1", "OD808"]},
    {"genre": ["hard-rock", "hardrock", "punk", "rock", "硬摇滚", "朋克", "摇滚"],
     "family": ["marshall", "soldano"], "cab": ["G12T", "4x12"], "boost": ["TS808", "SD-1"]},
    {"genre": ["blues", "clean", "funk", "布鲁斯", "清音"],
     "family": ["fender"], "cab": ["JENSEN", "1x12"], "boost": []},
    {"genre": ["chime", "brit", "英式", "英伦"],
     "family": ["vox"], "cab": ["ALNICO", "2x12"], "boost": []},
]
AMP_RE  = re.compile(r"AMP|PREAMP|HEAD|前级|箱头", re.I)
CAB_RE  = re.compile(r"CAB|IR|SPK|箱体", re.I)
# ★ 不能写光秃秃的 "OD"：它会命中模块名 MOD（模块表里真有 MOD 这类调制模块时，
#   推子会选错，而且自检照样通过）。要求 OD 自成一个词或与 DS 连写。
BOOST_RE = re.compile(r"\bDS\b|\bOD\b|DS\s*/\s*OD|DSOD|DRIVE|BOOST|DIST|OVERDRIVE|\bDS1\b|失真|推子|过载", re.I)


def norm(s):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(s)).upper()


def find_module(modules, pat):
    for name, m in modules.items():
        if pat.search(name) or pat.search(str(m.get("file_key", ""))):
            return name
    return None


def doctrine_for(genre):
    """曲风 -> 规则（并把家族展开成名字关键词列表 amp=）"""
    g = norm(genre)
    for rule in DOCTRINE:
        for alias in rule["genre"]:
            if norm(alias) and norm(alias) in g:
                r = dict(rule)
                r["amp"] = [kw for f in rule["family"] for kw in FAMILIES.get(f, [])]
                return r
    return None


def type_list(mod):
    """设备表里某模块的 Type -> {id: {name, params}}（继承模块参数后展开）"""
    out = {}
    base = mod.get("params") or {}
    for t in (mod.get("types") or []):
        own = t.get("params") or {}
        params = dict(base) if t.get("params_from_module", True) else {}
        params.update(own)
        out[int(t["id"])] = {"name": t.get("name", ""), "params": params,
                             "manual_item": t.get("manual_item")}
    return out


def pick_type(types, keywords):
    """按关键词优先级在设备表的 Type 名里找。-> (id, name, 命中的关键词) 或 None"""
    for kw in keywords:
        for tid, t in sorted(types.items()):
            if norm(kw) and norm(kw) in norm(t["name"]):
                return tid, t["name"], kw
    return None


def value_and_basis(pname, spec, want, out_unknowns, where):
    """一个参数取什么值 + 依据。want = 经典配置指定的取值意图（None 表示没有）

    ★ 依据只有三档，**没有"抄出厂预设"这一档**：从现成预设里取中位数 = 把厂商的审美当起点，
      而且它会让 agent 走"抄"这条路而不是"组"。型号选择（哪个 Type）才允许参考同族名字。
    """
    lo = hi = None
    if "range" in spec:
        lo, hi = float(spec["range"][0]), float(spec["range"][1])
    vals = spec.get("values")

    def clamp(v):
        if vals is not None: return v
        if lo is None: return v
        return max(lo, min(hi, v))

    if want is not None:
        return clamp(want), "doctrine"
    if "default" in spec:
        return clamp(spec["default"]), "manual_default"
    if lo is not None and hi is not None:
        mid = round((lo + hi) / 2.0, 2)
        if mid == int(mid): mid = int(mid)
        out_unknowns.append("%s: 说明书没给默认值 -> 暂用范围中点 %s（%s）" % (pname, mid, where))
        return mid, "range_midpoint"
    if vals:
        out_unknowns.append("%s: 没有默认值 -> 暂用第一个取值 %r（%s）" % (pname, vals[0], where))
        return vals[0], "values_first"
    out_unknowns.append("%s: 表里没有这个参数的范围/默认值 -> 不给值（%s）" % (pname, where))
    return None, "none"


def main(argv):
    pos = [a for a in argv if not a.startswith("--")]
    opt = dict(a[2:].split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    if not pos:
        print(__doc__); return 2
    genre = pos[0]

    devdir = os.path.join(ROOT, "devices")
    dev = opt.get("device") or os.environ.get("TONE_DEVICE")
    if opt.get("table"):
        dev, td = os.path.basename(os.path.dirname(os.path.abspath(opt["table"]))), os.path.abspath(opt["table"])
    elif dev:
        td = os.path.join(devdir, dev, "parameter_table.json")
    else:
        found = []
        if os.path.isdir(devdir):
            for n in sorted(os.listdir(devdir)):
                f = os.path.join(devdir, n, "parameter_table.json")
                if os.path.isfile(f): found.append((n, f))
        if len(found) == 1:
            dev, td = found[0]
        elif not found:
            print("找不到设备规格表。先做第零步（SKILL.md ⓪）：")
            print("  1) 拷模板: reference\\parameter_table.template.json")
            print("              -> devices\\<型号>\\parameter_table.json")
            print("  2) 照说明书填模块表 + 参数表（规范 reference\\13-两表规范.md）")
            print("  3) 校验:   tone.bat run check_parameter_table.py devices\\<型号>\\parameter_table.json")
            return 2
        else:
            print("有 %d 台设备，用 --device=<型号> 指定: %s"
                  % (len(found), ", ".join(n for n, _ in found)))
            return 2
    if not os.path.isfile(td):
        print("找不到 %s" % td); return 2
    d = json.load(open(td, encoding="utf-8-sig"))
    if d.get("schema") != "parameter_table/v2":
        print("%s 不是 parameter_table/v2（先跑 check_parameter_table.py）" % td); return 2

    modules = d.get("modules") or {}
    fmt = d.get("preset_format") or {}
    unknowns = list(d.get("unknowns") or [])
    basis = {}

    # ---- ① 曲风 -> 经典配置 ----
    rule = doctrine_for(genre)
    if not rule:
        print("  !! 认不出曲风 %r（已知: %s）" % (genre, " / ".join(r["genre"][0] for r in DOCTRINE)))
        print("     曲风是你自己定的标签（08-工作流详解.md §9.0.5 ①），照表里挑一个再说")
        return 2
    amp_name = find_module(modules, AMP_RE)
    cab_name = find_module(modules, CAB_RE)
    boost_name = find_module(modules, BOOST_RE)
    if not amp_name:
        print("!! 设备表的模块里找不到【箱头/前级】—— 没有它就出不了起点预设"); return 2
    if not cab_name:
        unknowns.append("设备表里没有【箱体/IR】模块 -> 只开 AMP + 推子（§10.7.2 的 Entire 采集就是这种）")
    if rule["boost"] and not boost_name:
        unknowns.append("经典配置要求推子（%s），但设备表里没有 DS/OD 类模块" % "/".join(rule["boost"]))

    # ---- ② 定值 ----
    # ★ 这里【不再】读出厂预设库。取同族预设的中位数 = 把厂商的审美当起点，
    #   而且它会诱导 agent 走"抄一份现成预设"这条路 —— 本工具要的是"从规格组一版出来"。
    #   型号（哪个 Type）仍然按 §10.7.3 的经典配置、用名字去参数表里匹配（那不算抄值）。
    open_now = {amp_name} | ({cab_name} if cab_name else set()) | ({boost_name} if boost_name else set())
    effect_module, manual_rows = {}, []
    no_land = set()          # 落盘③ 判定为"参数表里没有这个 Type"的模块 —— 自检要跳过它们
    chosen_types = {}

    for name, m in modules.items():
        fk = m.get("file_key") or name
        sw_key, ty_key, dk = m.get("switch_key"), m.get("type_key"), m.get("data_key")
        entry = {}
        if sw_key: entry[sw_key] = 1 if name in open_now else 0
        if name not in open_now:
            if ty_key: entry[ty_key] = 0
            # ★ 关闭的模块也要把 Data 填成【它的说明书默认值】，不能填空对象：
            #   设备自己导出的文件里，Switch=0 的模块照样带完整 Data（实测 DELAY/EQ/FXA…），
            #   空对象会让设备读到"没有参数"这种不该存在的形状。
            data0 = {}
            for pn, ps in (m.get("params") or {}).items():
                if "default" in ps: data0[pn] = ps["default"]
                elif ps.get("values"): data0[pn] = ps["values"][0]
                elif "range" in ps:
                    mid = round((float(ps["range"][0]) + float(ps["range"][1]))/2.0, 2)
                    data0[pn] = int(mid) if mid == int(mid) else mid
            if dk:
                if data0:
                    entry[dk] = data0
                else:
                    # ★ 表里没有它的参数（13 §13.7 教的是「看不清就省略」——所以这是常态），
                    #   那就【不许】写出 Data:{} 这种设备上不该存在的形状：
                    #   保留外壳里设备自己写的值；外壳也没有就不写 Data 这个键。
                    shell_mod = ((fmt.get("template") or {}).get("effectModule") or {}).get(fk)
                    if isinstance(shell_mod, dict) and isinstance(shell_mod.get(dk), dict) and shell_mod[dk]:
                        entry[dk] = dict(shell_mod[dk])
                        unknowns.append("%s: 关闭中，表里没有它的参数 -> Data 用外壳里设备写的原值" % fk)
                    else:
                        unknowns.append("%s: 关闭中，表里没有它的参数、外壳里也没有 -> 不写 Data（设备保持自己的值）" % fk)
            effect_module[fk] = entry
            basis["%s.%s" % (fk, sw_key or "Switch")] = "chain_rule:起点只开 AMP+CAB+推子（§9.0.5）"
            continue

        types = type_list(m)
        pick = None
        if name == amp_name:   pick = pick_type(types, rule["amp"])
        elif name == cab_name: pick = pick_type(types, rule["cab"])
        elif name == boost_name: pick = pick_type(types, rule["boost"])
        if pick is None and types:
            pick = (min(types), types[min(types)]["name"], None)
            unknowns.append("%s: 认不出经典配置要的型号 -> 暂时用第 %d 号 %s，【要让用户在设备上回读确认】"
                            % (name, pick[0], pick[1]))
        if pick is None:
            unknowns.append("%s: 设备表里没有 Type 列表 -> 只能用模块参数" % name)
            tparams, tname = (m.get("params") or {}), None
        else:
            tparams, tname = types[pick[0]]["params"], pick[1]
            chosen_types[name] = (pick[0], tname, pick[2])
            if ty_key: entry[ty_key] = pick[0]
            basis["%s.%s" % (fk, ty_key or "Type")] = "doctrine:§10.7.3" + (
                "（命中关键词 %s）" % pick[2] if pick[2] else "（没命中，需回读确认）")

        data = {}
        for pname, spec in tparams.items():
            want = None
            if name == boost_name:                     # §10.7.4 推子当塑形用
                rng = spec.get("range")
                if rng and re.search(r"gain|drive", pname, re.I):   want = float(rng[0])
                elif rng and re.search(r"level|volume", pname, re.I): want = float(rng[1])
                elif rng and re.search(r"tone", pname, re.I):        want = (float(rng[0])+float(rng[1]))/2.0
            v, why = value_and_basis(pname, spec, want,
                                     unknowns, "%s%s" % (name, ("/" + tname) if tname else ""))
            if v is not None:
                data[pname] = v
                basis["%s.%s" % (fk, pname)] = why
        # ★ 落盘判定：只有"表里记录了这个 Type、而且键名逐字对得上"的模块才自动写文件；
        #   对不上（换了 Type / 固件不同 / 表里没记这个 Type 的参数）就【不落盘】，
        #   改出「在设备上拧到几」的表给用户 —— 这是"其他的东西变了就变成人工调整机器"的落点。
        why_no = None
        if name in open_now and pick is not None and tname:
            if not tparams:   # 表里没有这个 Type 的参数 -> 见下（不落盘）
                why_no = "参数表里这个 Type（%s）没有记录参数" % tname
        if why_no:
            # ★【不落盘】的正确做法：不用我们猜的值去覆盖设备上的东西 ——
            #   ① 外壳里这个模块有 Data（设备自己写的合法数据）-> 原样保留；
            #   ② 没有 -> 只写开关，连 Data 这个键都不写（写空对象是设备上不该存在的形状）；
            #   ③ 无论哪种，都出一行【人工表】让用户在设备上调。
            shell_mod = ((fmt.get("template") or {}).get("effectModule") or {}).get(fk)
            no_land.add(fk)      # ★ 登记：自检必须跳过它，否则保留的每个值都会被逐键判错
            # ★ 外壳里这个模块【整块不动】：外壳的 Type 和 Data 是一套自洽的值。
            #   只搬 Data 却把我们选的 Type 写进去，会造出「Type = JCM900、Data = 外壳里 Type 0 的键」
            #   这种设备上不该存在的组合 —— 而落盘③ 存在的理由恰恰是「换 Type 键名会完全不同」。
            if isinstance(shell_mod, dict) and dk and isinstance(shell_mod.get(dk), dict) and shell_mod[dk]:
                effect_module[fk] = dict(shell_mod)
                # ★ 但【开关】要按起点的规则写：外壳里那个模块可能是关着的，
                #   整块照搬会让文件写着「只开 AMP+CAB+推子」，实际 AMP 却是 Switch=0。
                #   开关与 Type/Data 正交 —— 打开它 + 用外壳那套自洽的 Type/Data，是合法的组合。
                if sw_key: effect_module[fk][sw_key] = 1 if name in open_now else 0
                sh_ty = shell_mod.get(ty_key) if ty_key else None
                unknowns.append("%s: %s -> 该模块【Type/Data 保持设备上的原样】（文件里仍是 Type %s；"
                                "开关已按起点规则打开）" % (name, why_no, sh_ty if sh_ty is not None else "?"))
                if pick is not None and sh_ty != pick[0]:
                    unknowns.append("     经典配置想用的是 Type %s —— 请【在设备上手动切过去并设定参数】"
                                    % pick[0])
            else:
                effect_module[fk] = entry
                unknowns.append("%s: %s，外壳里也没有它 -> 只写开关，参数请【在设备上手动设】"
                                % (name, why_no))
            manual_rows.append((name, "%s（不落盘）" % tname, data))
            continue
        if dk: entry[dk] = data
        else: entry.update(data)
        effect_module[fk] = entry
        if name in open_now:
            manual_rows.append((name, tname, data))

    # ---- ④ 落盘 + 自检 ----
    out = {"device": d.get("device"), "genre": genre,
           "created": datetime.date.today().isoformat(),
           "kind": fmt.get("kind"),
           "basis": basis, "unknowns": unknowns}

    print("=" * 62)
    print("  起点预设（曲风: %s）" % genre)
    print("=" * 62)
    print("  设备   %s %s   规格表 %s" % ((d.get("device") or {}).get("brand", "?"),
                                       (d.get("device") or {}).get("model", ""), td))
    print("  经典配置 箱头 %s / 箱体 %s / 推子 %s（§10.7.3）"
          % ("/".join(rule["amp"]) or "-", "/".join(rule["cab"]) or "-", "/".join(rule["boost"]) or "不用"))
    print("  只开     " + " + ".join(sorted(open_now)))
    print()
    for name, tname, data in manual_rows:
        print("  %-8s %s" % (name, ("Type %s" % tname) if tname else "(无 Type)"))
        if not data:
            # 不落盘的模块必须说清"为什么一个参数都没有"，否则这张表是空的、用户不知道要干什么
            print("      （表里没有这个 Type 的参数 —— 保持设备上的原值，按说明书手动设）")
            continue
        for k, v in data.items():
            print("      %-14s %-6s  %s" % (k, v, basis.get("%s.%s" % (modules[name].get("file_key", name), k), "")))
    print()

    if fmt.get("kind") == "json":
        shell = dict(fmt.get("template") or {})
        ck, cv = fmt.get("chain_key"), fmt.get("chain_value")
        order = d.get("chain", {}).get("modules") or list(modules)
        # ★ 链序【不自编】：外壳（用户从设备导出的那个文件）里已经有 effectChain，原样保留。
        #   实测它是【变量】：两份真机导出文件的 effectChain 首元素分别是 4 和 0 ——
        #   我们推不出设备用的是什么下标空间，自己编就等于赌。
        #   只有外壳里根本没有这个字段时，才按参数表里的链序生成（并记进未定项）。
        if ck and not shell.get(ck):
            if cv == "module_file_key":
                shell[ck] = [modules[n].get("file_key") or n for n in order if n in modules]
            elif cv == "module_index":
                shell[ck] = [order.index(n) for n in order if n in modules]
            unknowns.append("%s: 外壳里没有链序数组 -> 按参数表顺序生成，要在设备上回读确认" % ck)
        elif ck:
            basis["%s" % ck] = "外壳原样保留（链序是变量，不自编）"
        shell.setdefault("effectModule", {}).update(effect_module)
        out["preset"] = shell

        # 自检：结构完整 + 值都在表范围内（不通过就不许往下走）
        bad = []
        ck = fmt.get("chain_key")
        if ck and not (fmt.get("template") or {}).get(ck):
            # 只在我们【自己生成】链序时才做覆盖率检查；原样保留外壳的不判（长度是设备的事）
            order = d.get("chain", {}).get("modules") or list(modules)
            want_n = len([n for n in order if n in modules])
            if len(shell.get(ck) or []) != want_n:
                bad.append("%s 只有 %d 项，应该覆盖整条链的 %d 个模块"
                           % (ck, len(shell.get(ck) or []), want_n))
        for name, m in modules.items():
            fk = m.get("file_key") or name
            if fk not in effect_module: bad.append("%s 不在落盘结果里" % fk)
            if fk in no_land: continue      # 不落盘的模块：它的值是外壳里的原值，不能拿参数表核
            sw = m.get("switch_key")
            if sw and sw not in effect_module[fk]: bad.append("%s.%s 没写开关" % (fk, sw))
            if name in open_now:
                types = type_list(m)
                tid = effect_module[fk].get(m.get("type_key")) if m.get("type_key") else None
                params = types.get(int(tid), {}).get("params", {}) if tid is not None else (m.get("params") or {})
                dk2 = m.get("data_key")
                data = effect_module[fk].get(dk2) if dk2 else None
                if not isinstance(data, dict): continue   # 没有参数容器就没参数可查（不是错误）
                for k, v in data.items():
                    sp = params.get(k)
                    if not sp: bad.append("%s.%s 不在参数表里" % (fk, k)); continue
                    if "range" in sp and not (sp["range"][0] <= v <= sp["range"][1]):
                        bad.append("%s.%s = %s 超出 %s" % (fk, k, v, sp["range"]))
                    if sp.get("values") and v not in sp["values"]:
                        bad.append("%s.%s = %s 不在 %s 里" % (fk, k, v, sp["values"]))
        out["selfcheck"] = "fail" if bad else "pass"
        print("  自检   %s" % ("通过：模块齐、开关明确、值全在表范围内" if not bad
                              else "不通过：\n      - " + "\n      - ".join(bad)))
        if bad: return 2
    else:
        print("  这台设备没有预设文件接口（preset_format.kind=%s）—— 用户照上面的表在设备上手动拧。"
              % (fmt.get("kind") or "manual"))
        print("  拧完让用户在设备屏幕上【回读】模块名和 Type 名（SKILL.md 铁律 3）。")

    if unknowns:
        print()
        print("  未定 %d 条（不猜，原样带出去）:" % len(unknowns))
        for u in unknowns: print("      · %s" % u)

    dest = opt.get("out")
    if not dest:
        try: dest = os.path.join(song_dir(), "start_preset.json")
        except SystemExit: dest = None
        except Exception: dest = None
    if dest:
        json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print()
        print("  已写 %s" % dest)
    print()
    print("  下一步：按 §10.8 的 7 步【逐个】开模块，不要一次全开；")
    print("          每步的验收判据是残差（§10.7.5），不是耳朵。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
