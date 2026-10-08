"""设备规格表（parameter_table.json）校验 + 出表

规范见 reference/13-两表规范.md，模板见 reference/parameter_table.template.json。

用法:
  python check_parameter_table.py <parameter_table.json>          校验（不通过 exit 2）
  python check_parameter_table.py <parameter_table.json> --table  校验并打印【设备规格表】给人看

为什么要有这一步：规格表是【生成器】唯一的形状来源。表里少一个字段，
生成器就吐不出结构完整的预设，或者悄悄用了一个没依据的值 —— 那正是
"参数表只列了某一个 Type 的键名"这类错法的入口。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from songlib import utf8_stdout
utf8_stdout()

ALLOWED_PARAM_KEYS = {"range", "values", "step", "default", "unit", "note"}
ALLOWED_MODULE_KEYS = {"file_key", "switch_key", "type_key", "data_key",
                       "param_order", "types", "params", "note"}
ALLOWED_TYPE_KEYS = {"id", "manual_item", "name", "params_from_module", "params", "note"}


def strip_private(o):
    """去掉以 _ 开头的说明键（模板自带）"""
    if isinstance(o, dict):
        return {k: strip_private(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, list):
        return [strip_private(v) for v in o]
    return o


def check_param(path, p, errs, warns):
    if not isinstance(p, dict):
        errs.append("%s: 参数规格必须是对象" % path); return
    for k in p:
        if k not in ALLOWED_PARAM_KEYS:
            errs.append("%s.%s: 不认识的键（可用: %s）" % (path, k, " / ".join(sorted(ALLOWED_PARAM_KEYS))))
    has_r, has_v = "range" in p, "values" in p
    if has_r == has_v:
        errs.append("%s: range 和 values 必须【二选一】（都有或都没有都错）" % path)
    lo = hi = None
    if has_r:
        r = p["range"]
        if not (isinstance(r, list) and len(r) == 2 and all(isinstance(x, (int, float)) for x in r)):
            errs.append("%s.range: 要写成 [最小, 最大]，两个数" % path)
        else:
            lo, hi = float(r[0]), float(r[1])
            if lo > hi: errs.append("%s.range: 最小 %.4g > 最大 %.4g" % (path, lo, hi))
    if has_v:
        v = p["values"]
        if not (isinstance(v, list) and v):
            errs.append("%s.values: 要写成非空列表" % path)
    if "step" in p:
        s = p["step"]
        if not isinstance(s, (int, float)) or s <= 0:
            errs.append("%s.step: 必须是正数（连续量 0.1，整数档 1）" % path)
        elif has_r and lo is not None and (hi - lo) > 0 and s > (hi - lo):
            errs.append("%s.step: 步进 %.4g 比整个范围还大" % (path, s))
    if "default" in p:
        d = p["default"]
        if has_r and lo is not None:
            if not (isinstance(d, (int, float)) and lo <= float(d) <= hi):
                errs.append("%s.default: %r 不在 [%.4g, %.4g] 里" % (path, d, lo, hi))
        elif has_v and d not in p["values"]:
            errs.append("%s.default: %r 不在 values 里" % (path, d))
    else:
        warns.append("%s: 没有 default（说明书没写就保持省略，别填 0 充数）" % path)


def check_module(mod_name, m, errs, warns):
    base = "modules.%s" % mod_name
    if not isinstance(m, dict):
        errs.append("%s: 必须是对象" % base); return 0, 0
    for k in m:
        if k not in ALLOWED_MODULE_KEYS:
            errs.append("%s.%s: 不认识的键（可用: %s）" % (base, k, " / ".join(sorted(ALLOWED_MODULE_KEYS))))
    fk = m.get("file_key")
    if not isinstance(fk, str) or not fk:
        errs.append("%s.file_key: 必填 —— 预设文件/设备里这个模块的键名，逐字一致" % base)
    for k in ("switch_key", "type_key", "data_key"):
        if k not in m:
            errs.append("%s.%s: 必填（设备没有这个字段就写 null）" % (base, k))
    params = m.get("params") or {}
    if not isinstance(params, dict):
        errs.append("%s.params: 必须是对象" % base); params = {}
    for pn, ps in params.items():
        check_param("%s.params.%s" % (base, pn), ps, errs, warns)
    order = m.get("param_order")
    if order is not None:
        if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
            errs.append("%s.param_order: 要写成参数名数组" % base)
        else:
            for pn in order:
                if pn not in params:
                    errs.append("%s.param_order: %s 不在这模块的 params 里" % (base, pn))
    types = m.get("types")
    n_types = 0
    if m.get("type_key") is not None:
        if not isinstance(types, list) or not types:
            errs.append("%s.types: type_key 不是 null，就必须给出 Type 列表（模块表那一页）" % base)
            types = []
    elif types:
        warns.append("%s: type_key 是 null 却写了 types —— 生成器会忽略它" % base)
    seen = {}
    for i, t in enumerate(types or []):
        tb = "%s.types[%d]" % (base, i)
        if not isinstance(t, dict):
            errs.append("%s: 必须是对象" % tb); continue
        for k in t:
            if k not in ALLOWED_TYPE_KEYS:
                errs.append("%s.%s: 不认识的键（可用: %s）" % (tb, k, " / ".join(sorted(ALLOWED_TYPE_KEYS))))
        tid = t.get("id")
        if not isinstance(tid, int) or isinstance(tid, bool) or tid < 0:
            errs.append("%s.id: 必填，从 0 开始的整数（设备/预设文件里的编号）" % tb)
        else:
            if tid in seen:
                errs.append("%s.id: 编号 %d 和 types[%d] 撞了" % (tb, tid, seen[tid]))
            seen[tid] = i
        if not (t.get("name") or "").strip():
            errs.append("%s.name: 必填（设备屏幕上显示的名字）" % tb)
        own = t.get("params") or {}
        if not isinstance(own, dict):
            errs.append("%s.params: 必须是对象" % tb); own = {}
        for pn, ps in own.items():
            check_param("%s.params.%s" % (tb, pn), ps, errs, warns)
        inherit = t.get("params_from_module", True)
        if not isinstance(inherit, bool):
            errs.append("%s.params_from_module: 要写 true / false" % tb)
        elif not inherit and not own:
            errs.append("%s: 声明了不继承模块参数，却没写自己的 params" % tb)
        elif inherit and not params:
            errs.append("%s: 继承模块参数，但 modules.%s.params 是空的" % (tb, mod_name))
        n_types += 1
    return len(params), n_types


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    want_table = "--table" in argv
    if not args:
        print(__doc__); return 2
    path = args[0]
    if not os.path.exists(path):
        print("找不到 %s" % path); return 2
    try:
        raw = json.load(open(path, encoding="utf-8-sig"))
    except Exception as e:
        print("!! JSON 读不了: %s" % e); return 2
    d = strip_private(raw)
    errs, warns = [], []

    if d.get("schema") != "parameter_table/v2":
        errs.append('schema: 必须是 "parameter_table/v2"（模板见 reference/parameter_table.template.json）')
    dev = d.get("device") or {}
    if not isinstance(dev, dict) or not (dev.get("brand") or dev.get("model")):
        errs.append("device: 至少填 brand 或 model")
    if d.get("confidence") not in ("high", "medium", "low"):
        errs.append('confidence: 必须是 high / medium / low（从说明书抄 = high，从界面截图猜 = medium）')
    if not d.get("source"):
        warns.append("source: 空着 —— 写清是从哪一页抄的，将来好复核")

    mods = d.get("modules") or {}
    if not isinstance(mods, dict) or not mods:
        errs.append("modules: 空 —— 这是【模块表】，至少要有 AMP")
        mods = {}
    chain = d.get("chain") or {}
    cm = chain.get("modules") if isinstance(chain, dict) else None
    if not isinstance(cm, list) or not cm:
        errs.append("chain.modules: 空 —— 信号从输入到输出的模块顺序")
        cm = []
    for name in cm:
        if name not in mods:
            errs.append("chain.modules: %s 不在 modules 里" % name)

    n_params = n_types = 0
    for name, m in mods.items():
        a, b = check_module(name, m, errs, warns)
        n_params += a; n_types += b

    pf = d.get("preset_format") or {}
    kind = pf.get("kind") if isinstance(pf, dict) else None
    if kind not in ("json", "manual"):
        errs.append('preset_format.kind: 必须是 "json"（能生成预设文件）或 "manual"（只能出表格给人拧）')
    if kind == "json":
        tpl = pf.get("template")
        if not isinstance(tpl, dict) or not tpl:
            errs.append("preset_format.template: kind=json 时必须给一个【空壳预设】（结构完整、值留空）")
        if pf.get("chain_key") is not None and pf.get("chain_value") not in ("module_file_key", "module_index"):
            errs.append('preset_format.chain_value: 有 chain_key 就必须写 "module_file_key" 或 "module_index"')

    unk = d.get("unknowns") or []
    if not isinstance(unk, list):
        errs.append("unknowns: 要写成字符串数组"); unk = []

    print("=" * 62)
    print("  设备规格表: %s" % path)
    print("=" * 62)
    print("  设备     %s %s" % (dev.get("brand", "?"), dev.get("model", "")))
    print("  来源     %s   置信度 %s" % (d.get("source") or "(空)", d.get("confidence") or "(空)"))
    print("  效果链   %s" % (" -> ".join(cm) if cm else "(空)"))
    print("  模块 %d 个 / Type %d 个 / 参数 %d 个" % (len(mods), n_types, n_params))
    print("  落盘     %s" % (kind or "(空)"))
    if unk:
        print()
        print("  ⚠️ 未确定 %d 条（生成器会原样带出去，不猜）:" % len(unk))
        for u in unk: print("      · %s" % u)

    if want_table and not errs:
        print()
        print("  模块        参数          范围/取值            默认")
        print("  " + "-" * 56)
        for name in (cm or list(mods)):
            m = mods.get(name) or {}
            rows = []
            for pn, ps in (m.get("params") or {}).items():
                rng = ("%g-%g" % tuple(ps["range"])) if "range" in ps else ("|".join(map(str, ps.get("values", []))))
                rows.append((pn, rng, ps.get("default", "")))
            for t in (m.get("types") or []):
                if t.get("params_from_module", True): continue
                for pn, ps in (t.get("params") or {}).items():
                    rng = ("%g-%g" % tuple(ps["range"])) if "range" in ps else ("|".join(map(str, ps.get("values", []))))
                    rows.append(("%s[%s]" % (pn, t.get("name")), rng, ps.get("default", "")))
            for i, (pn, rng, dflt) in enumerate(rows):
                print("  %-10s  %-12s  %-18s  %s" % (name if i == 0 else "", pn, rng, dflt))

    print()
    for w in warns:
        print("  [提醒] %s" % w)
    if errs:
        print("  !! 不通过，%d 处要改：" % len(errs))
        for e in errs:
            print("     - %s" % e)
        print()
        print("  规范: reference/13-两表规范.md    模板: reference/parameter_table.template.json")
        return 2
    print("  通过。规格表可以交给生成器用了。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
