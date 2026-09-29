"""用运行时注册的方式，让 audio-separator 加载本地 BS-Roformer SW 6-stem
   用法: python load_bsr.py <输入音频> [输出目录]

   路径全部相对本脚本：包根/models 放模型，包根/tools/.cache 放缓存
"""
import os, sys, time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PKG   = TOOLS.parent
MODELS = PKG / 'models'          # 模型放包根/models
CACHE  = TOOLS / '.cache'        # 临时/缓存放 tools/.cache
CACHE.mkdir(exist_ok=True)
os.environ.setdefault('TEMP', str(CACHE))
os.environ.setdefault('TMP',  str(CACHE))
os.environ.setdefault('HF_HOME', str(CACHE / 'hf'))
os.environ.setdefault('TORCH_HOME', str(CACHE / 'torch'))

INP = sys.argv[1] if len(sys.argv) > 1 else None
OUT = sys.argv[2] if len(sys.argv) > 2 else str(CACHE / "bsr_out")
if not INP:
    print("用法: python load_bsr.py <输入音频> [输出目录]"); sys.exit(2)
if not (MODELS / "BS-Rofo-SW-Fixed.ckpt").exists():
    print("找不到模型: " + str(MODELS / "BS-Rofo-SW-Fixed.ckpt")); sys.exit(2)

CKPT = "BS-Rofo-SW-Fixed.ckpt"
YAML = "BS-Rofo-SW-Fixed.yaml"
STEMS = ["vocals", "bass", "drums", "guitar", "piano", "other"]

import numpy as np, soundfile as sf
from audio_separator.separator import Separator

# ---- 运行时注册本地模型 ----
_orig = Separator.list_supported_model_files
def patched(self):
    d = _orig(self)
    md = d.setdefault("MDXC", {})
    md["Roformer Model: BS-Roformer SW 6-stem (local)"] = {
        "filename": CKPT,
        "scores": {},
        "stems": STEMS,
        "download_files": [CKPT, YAML],
    }
    return d
Separator.list_supported_model_files = patched
# ---------------------------------

os.makedirs(OUT, exist_ok=True)
sep = Separator(model_file_dir=str(MODELS), output_dir=OUT, output_format="WAV")
print("torch_device =", sep.torch_device, flush=True)
print("onnx provider =", sep.onnx_execution_provider, flush=True)
t0 = time.time()
sep.load_model(model_filename=CKPT)
print("模型加载耗时 %.1f s" % (time.time()-t0), flush=True)

info = sf.info(INP)
dur = info.frames / info.samplerate
print("输入: %s  %.2f s  %d Hz  %d ch" % (os.path.basename(INP), dur, info.samplerate, info.channels), flush=True)

t1 = time.time()
outs = sep.separate(INP)
el = time.time() - t1
print()
print("=== 结果 ===")
print("音频时长 %.2f s   推理耗时 %.2f s   实时比 %.3fx" % (dur, el, el/dur))
for f in outs:
    p = f if os.path.isabs(f) else os.path.join(OUT, f)
    sz = os.path.getsize(p)/1e6 if os.path.exists(p) else 0
    print("   %-58s %.2f MB" % (os.path.basename(f), sz))
