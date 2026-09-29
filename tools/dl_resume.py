"""断点续传下载器：分段 Range 请求 + 重试，绕开大文件连接被掐断的问题"""
import os, sys, time, requests

def download(url, dest, total_hint=None, chunk=2*1024*1024, tries=40):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    proxies_list = [None, {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}]
    # 先拿总长度
    total = total_hint
    if total is None:
        for px in proxies_list:
            try:
                r = requests.get(url, stream=True, timeout=20, proxies=px)
                if r.status_code == 200:
                    total = int(r.headers.get('Content-Length', 0))
                    r.close()
                    if total: break
                r.close()
            except Exception as e:
                print('  取长度失败(%s): %s' % ('代理' if px else '直连', str(e)[:60]))
    if not total:
        print('  拿不到文件长度，放弃'); return False
    print('  目标大小: %.1f MB' % (total/1e6))
    got = os.path.getsize(dest) if os.path.exists(dest) else 0
    if got >= total:
        print('  已完整'); return True
    fails = 0
    while got < total and fails < tries:
        end = min(got + chunk - 1, total - 1)
        hdr = {'Range': 'bytes=%d-%d' % (got, end)}
        ok = False
        for px in proxies_list:
            try:
                r = requests.get(url, headers=hdr, stream=True, timeout=30, proxies=px)
                if r.status_code not in (200, 206):
                    r.close(); continue
                data = r.content
                r.close()
                if not data: continue
                with open(dest, 'ab') as f:
                    f.write(data)
                got += len(data)
                ok = True
                fails = 0
                break
            except Exception:
                continue
        if not ok:
            fails += 1
            time.sleep(min(2.0, 0.3*fails))
        if got % (10*1024*1024) < chunk:
            print('    %.1f / %.1f MB' % (got/1e6, total/1e6), flush=True)
    final = os.path.getsize(dest) if os.path.exists(dest) else 0
    print('  完成: %.1f MB / %.1f MB  %s' % (final/1e6, total/1e6, 'OK' if final >= total else '不完整'))
    return final >= total

if __name__ == '__main__':
    base = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/'
    dest_dir = r'AS_MODELS'
    targets = [
        ('Reverb_HQ_By_FoxJoy.onnx', 66780123),
        ('UVR-DeEcho-DeReverb.pth', 223650277),
    ]
    for fn, sz in targets:
        dest = os.path.join(dest_dir, fn)
        if os.path.exists(dest) and os.path.getsize(dest) >= sz:
            print('%s 已存在，跳过' % fn); continue
        print('下载 %s' % fn, flush=True)
        ok = download(base + fn, dest, total_hint=sz)
        print('  ->', 'OK' if ok else '失败', flush=True)
