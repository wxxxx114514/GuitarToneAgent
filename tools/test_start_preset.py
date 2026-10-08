r"""起点预设生成器（synth_start.py）的固定回归套件

用法:  & venv\Scripts\python.exe tools\test_start_preset.py
产物:  PASS/FAIL + 退出码（0 = 全过）

它守的是【批 1.5 之后不许再出现】的四件事：
  ① 依据里不许出现任何"抄现成预设"的来源（factory_median 之类）
  ② 外壳里已有链序 -> 原样保留，不许自编（实测真机两份文件的 effectChain 首元素是 4 和 0）
  ③ 关闭的模块的 Data 不许是空对象（设备自己的文件里，Switch=0 的模块照样带完整参数）
  ④ 认不出型号时要给出【未定项】，不许静默挑一个
"""
import sys, os, json, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from songlib import utf8_stdout

utf8_stdout()
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

AMP = {"file_key": "AMP", "switch_key": "Switch", "type_key": "Type", "data_key": "Data",
       "types": [{"id": 0, "name": "CLEAN 1", "params": {}},
                 {"id": 1, "name": "JCM900", "params": {}}],
       "params": {"Gain": {"range": [0, 100], "step": 1, "default": 30},
                  "Bass": {"range": [0, 100], "step": 1, "default": 50},
                  "Mst":  {"range": [0, 100], "step": 1}}}
CAB = {"file_key": "CAB", "switch_key": "Switch", "type_key": "Type", "data_key": "Data",
       "types": [{"id": 0, "name": "4x12 G12T-75", "params": {}}],
       "params": {"Level": {"range": [0, 100], "step": 1, "default": 50}}}
BOOST = {"file_key": "DS/OD", "switch_key": "Switch", "type_key": "Type", "data_key": "Data",
         "types": [{"id": 0, "name": "TS808", "params": {}}],
         "params": {"Gain": {"range": [0, 100], "step": 1, "default": 50},
                    "Tone": {"range": [0, 100], "step": 1, "default": 50},
                    "Volume": {"range": [0, 100], "step": 1}}}
EQ = {"file_key": "EQ", "switch_key": "Switch", "type_key": "Type", "data_key": "Data",
      "types": [], "params": {"100Hz": {"range": [0, 100], "step": 1, "default": 50},
                              "Level": {"range": [0, 100], "step": 1}}}
CHAIN = ["DS/OD", "AMP", "CAB", "EQ"]

def make_table(chain_in_template):
    tpl = {"Others": {"Volume": 50}, "effectModule": {}}
    if chain_in_template is not None:
        tpl["effectChain"] = chain_in_template
    return {"schema": "parameter_table/v2", "device": {"brand": "_fixture", "model": "t1"},
            "source": "夹具", "confidence": "low", "updated": "2026-01-01",
            "chain": {"modules": CHAIN, "fixed": True},
            "modules": {"AMP": AMP, "CAB": CAB, "DS/OD": BOOST, "EQ": EQ},
            "preset_format": {"kind": "json", "indent": 4, "chain_key": "effectChain",
                              "chain_value": "module_file_key", "template": tpl},
            "unknowns": []}

# 临时文件写工作区内的 _tmp_*（系统 temp 在文件沙箱外，写不进去）
# 临时文件写【包外】的 _tmp_param：包根可能是只读的，测试不该往包里写。
# （新建目录在本机沙箱下会被拒，所以用工作区里已存在的那个目录。）
TMPROOT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_tmp_param")
def run(table, genre="hard-rock"):
    os.makedirs(TMPROOT, exist_ok=True)
    tp = os.path.join(TMPROOT, "test_start_in.json")
    op = os.path.join(TMPROOT, "test_start_out.json")
    if os.path.exists(op): os.remove(op)
    json.dump(table, open(tp, "w", encoding="utf-8"), ensure_ascii=False)
    p = subprocess.run([PY, os.path.join(HERE, "synth_start.py"), genre,
                        "--table=" + tp, "--out=" + op],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = json.load(open(op, encoding="utf-8")) if os.path.exists(op) else None
    return (p.stdout or "") + (p.stderr or ""), out, p.returncode

def main():
    rows = []
    def check(name, ok, detail=""):
        rows.append((ok, name, detail))

    # ① 依据里不许有"抄预设"这一档
    txt, out, rc = run(make_table(["DS/OD", "AMP", "CAB", "EQ"]))
    # ★ 先断言【产物存在】：否则生成器整个崩掉时 out=None、basis={}，这一条会恒真通过
    #   （审计就是这么证明它恒真的：把 synth_start 改成什么都不产出，本套件第①条仍 PASS）。
    if out is None:
        check("依据里没有『抄现成预设』这一档", False, "生成器没产出文件（rc=%s）" % rc)
    else:
        basis = out.get("basis") or {}
        bad = [k for k, v in basis.items() if "factory" in str(v) or "预设" in str(v)]
        check("依据里没有『抄现成预设』这一档", (not bad) and bool(basis),
              ("%d 条依据，含可疑: " % len(basis)) + ",".join(bad) if bad else "%d 条依据，干净" % len(basis))

    # ② 外壳已有链序 -> 原样保留
    given = ["EQ", "DS/OD", "AMP", "CAB"]
    txt, out, rc = run(make_table(given))
    got = out["preset"].get("effectChain") if out else None
    check("外壳里的链序原样保留", got == given, "得到 %s" % got)

    # ③ 外壳没有链序 -> 生成 + 进未定项（不许静默）
    txt, out, rc = run(make_table(None))
    got = out["preset"].get("effectChain") if out else None
    check("没有链序时生成并说明", got == CHAIN and "链序" in txt, "得到 %s" % got)

    # ④ 关闭模块的 Data 不许是空对象
    txt, out, rc = run(make_table(given))
    em = (out["preset"].get("effectModule") or {}) if out else {}
    eqdata = (em.get("EQ") or {}).get("Data")
    check("关闭模块的 Data 不是空对象", isinstance(eqdata, dict) and len(eqdata) > 0,
          "EQ.Data=%s" % json.dumps(eqdata, ensure_ascii=False))

    # ⑤ 认不出型号时要给未定项
    t = make_table(given)
    t["modules"]["AMP"]["types"] = [{"id": 0, "name": "MYSTERY HEAD", "params": {}}]
    txt, out, rc = run(t)
    check("认不出型号 -> 有未定项", "回读确认" in txt, "输出里有『回读确认』" if "回读确认" in txt else "没有")

    # ⑥ 只开三样：其余模块 Switch 必须是 0
    txt, out, rc = run(make_table(given))
    em = (out["preset"].get("effectModule") or {}) if out else {}
    sw = {k: v.get("Switch") for k, v in em.items()}
    check("只开 AMP/CAB/推子", sw.get("AMP") == 1 and sw.get("CAB") == 1 and sw.get("DS/OD") == 1 and sw.get("EQ") == 0,
          json.dumps(sw, ensure_ascii=False))

    print("=" * 70)
    print("  起点预设生成器 回归套件")
    print("=" * 70)
    bad = 0
    for ok, name, detail in rows:
        if not ok: bad += 1
        print("  %-4s %-28s %s" % ("PASS" if ok else "FAIL", name, detail))
    print()
    print("  %d 条：%d 通过 / %d 失败" % (len(rows), len(rows)-bad, bad))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
