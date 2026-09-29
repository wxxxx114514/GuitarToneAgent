"""为一首新歌建立工作目录（第 0 步开工）

用法:
    python new_song.py "歌名" "D:\\music\\原曲.flac"

产出（<包根>/songs/<歌名>/）:
    source.txt    原曲路径记录（不复制大文件）
    stems\\        分离结果放这里
    target.npy    全曲目标曲线
    spec.json     演奏规格
    di\\  reamp\\  干声 / 录音
    notes.md      进展记录模板
"""
import os, sys, json
from pathlib import Path

# 包根 = 本文件的上上级（tools/ 的父目录），不写死盘符
PKG    = Path(__file__).resolve().parents[1]
ROOT   = PKG / "songs"
# 分离工具在包外（日常用 StemSep）；包内没有就只提示、不影响建目录
STEMSEP = Path(os.environ.get("STEMSEP", r"<包外>\StemSep\separate.ps1"))

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    name, src = sys.argv[1], os.path.abspath(sys.argv[2])
    if not os.path.exists(src):
        print("原曲不存在: %s" % src); sys.exit(1)

    D = ROOT / name
    for sub in ["stems", "di", "reamp"]:
        (D / sub).mkdir(parents=True, exist_ok=True)
    print("已建工作目录: %s" % D)

    (D / "source.txt").write_text(src + chr(10), encoding="utf-8")
    print("  原曲: %s" % src)

    notes = D / "notes.md"
    if not notes.exists():
        F = chr(96)*3
        body  = "# %s" % name + chr(10)*2
        body += "## 第 0 步 分析参考曲" + chr(10)*2
        body += "- [ ] 分离（StemSep）" + chr(10)
        body += "- [ ] 全曲目标曲线" + chr(10)
        body += "- [ ] 调性 / 主要和弦" + chr(10)
        body += "- [ ] 奏法比例" + chr(10)
        body += "- [ ] 音区 / 密度" + chr(10)*2
        body += "## 演奏规格" + chr(10)*2 + F + chr(10)
        body += "调性:" + chr(10) + "主要和弦:" + chr(10) + "奏法:" + chr(10)
        body += "音区:" + chr(10) + "密度:" + chr(10) + F + chr(10)*2
        body += "## 调参记录" + chr(10)*2
        body += "| 轮次 | 预设 | 对目标偏差 | 改动 | 备注 |" + chr(10)
        body += "|---|---|---|---|---|" + chr(10)
        notes.write_text(body, encoding="utf-8")
        print("  已建 notes.md（进展记录模板）")

    print()
    print("=== 下一步：分离 ===")
    if STEMSEP.exists():
        print('  & "%s" "%s" -Out "%s"' % (STEMSEP, src, D / "stems"))
    else:
        print('  （分离工具不在包内：用包外 StemSep，或设 $env:STEMSEP 指向 separate.ps1）')
    print()
    print("分离完成后:")
    print('  $env:SONG_DIR="%s"' % D)
    print("  python target_whole.py   # 全曲目标曲线（脚本读 $env:SONG_DIR）")
    print("  python chords.py         # 调性 + 和弦")

if __name__ == "__main__":
    main()
