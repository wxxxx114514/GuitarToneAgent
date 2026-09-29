import sys, os
sys.path.insert(0, r"HERE")
from dl_resume import download
DEST = str(HERE / "as_models")
JOBS = [
    ("https://huggingface.co/anvuew/dereverb_bs_roformer/resolve/main/dereverb_bs_roformer_anvuew_sdr_22.5050.ckpt",
     "dereverb_bs_roformer_anvuew_sdr_22.5050.ckpt", 204496717),
    ("https://huggingface.co/anvuew/dereverb_bs_roformer/resolve/main/config.yaml",
     "dereverb_bs_roformer_anvuew_sdr_22.5050.yaml", None),
]
for url, fn, sz in JOBS:
    dest = os.path.join(DEST, fn)
    if os.path.exists(dest) and (sz is None or os.path.getsize(dest) >= sz):
        print("%s 已存在，跳过" % fn); continue
    print("下载 %s" % fn, flush=True)
    ok = download(url, dest, total_hint=sz)
    print("  ->", "OK" if ok else "失败", flush=True)
