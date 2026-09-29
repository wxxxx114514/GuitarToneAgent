"""下载 BS-Roformer SW 6-stem 分轨模型

  用法:  python dl_bsr.py            # 下到 ../models/
         python dl_bsr.py --check      # 只校验已有文件（不下载）
         python dl_bsr.py <目标目录>

  设计要点（都是踩过的坑）：
    1. .yaml 小文件没有 Content-Length —— 不能靠长度判断完整性，改用 sha256
    2. 大文件连接会被掐断 —— 用 dl_resume 的分段 Range + 重试
    3. 国内直连不通 —— 自动在【直连 / 代理】之间切换
"""
import os, sys, hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dl_resume import download

REPO = "Blakus/bs_roformer_sw_6stem"
COMMIT = "dd755f5f5eaa1b01deb970fb296a55f6fec458a6"
BASE = "https://huggingface.co/%s/resolve/main/" % REPO

TARGETS = [
    ("BS-Rofo-SW-Fixed.ckpt", 699412152,
     "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e"),
    ("BS-Rofo-SW-Fixed.yaml", 4852,
     "e17a3b4bac1b924bcb521f569dcbf8b0318c23effec026de81eb95351b5fc8af"),
]


def sha256(p, blk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(blk)
            if not b: break
            h.update(b)
    return h.hexdigest()


def check(dest, verbose=True):
    """只校验，不下载。文件缺 / 大小不对 / sha256 不符 都算失败。"""
    ok_all = True
    for fn, size, want in TARGETS:
        p = dest / fn
        if not p.exists():
            if verbose: print("  缺:      %s" % fn)
            ok_all = False; continue
        got = p.stat().st_size
        if got != size:
            if verbose: print("  大小不对: %s  %d != %d" % (fn, got, size))
            ok_all = False; continue
        h = sha256(p)
        if h != want:
            if verbose: print("  sha256 不符: %s" % fn)
            ok_all = False; continue
        if verbose: print("  OK:      %-26s %d 字节  sha256 通过" % (fn, got))
    return ok_all


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check_only = "--check" in sys.argv
    dest = Path(args[0]) if args else HERE.parent / "models"
    dest.mkdir(parents=True, exist_ok=True)
    print("目标目录: %s" % dest)
    print("来源:     %s @ %s" % (REPO, COMMIT[:12]))
    print()
    if check_only:
        return 0 if check(dest) else 1
    ok_all = True
    for fn, size, want in TARGETS:
        p = dest / fn
        if p.exists():
            got = p.stat().st_size
            if got == size and sha256(p) == want:
                print("  %-26s 已存在且校验通过，跳过" % fn); continue
            print("  %-26s 存在但不对（%d 字节，应为 %d），重下" % (fn, got, size))
            p.unlink()
        print("  %-26s 下载中..." % fn, flush=True)
        if not download(BASE + fn, str(p), total_hint=size):
            print("  %-26s 下载失败" % fn); ok_all = False; continue
        got = p.stat().st_size
        if got != size:
            print("  %-26s 大小不对: %d / %d" % (fn, got, size)); ok_all = False; continue
        h = sha256(p)
        if h != want:
            print("  %-26s sha256 不匹配" % fn)
            print("       得到 %s" % h)
            print("       应为 %s" % want); ok_all = False; continue
        print("  %-26s OK  %d 字节  sha256 通过" % (fn, got))
    print()
    print("完成。" if ok_all else "有失败，见上面。")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
