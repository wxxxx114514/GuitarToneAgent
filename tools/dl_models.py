"""兼容别名 —— 实际的下载/校验逻辑在 dl_bsr.py（那边有断点续传 + 代理切换）。

    用法:  python dl_models.py            # 等价于 python dl_bsr.py
           python dl_models.py --check    # 只校验
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runpy
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dl_bsr.py"),
               run_name="__main__")
