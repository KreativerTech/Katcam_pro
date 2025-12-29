#!/usr/bin/env python3
"""
Simple camera open/read stress test for Windows (OpenCV).
Run with the project's virtualenv python. It will attempt N open/read/close cycles
and print a JSON-like line per attempt so you can spot failures.
"""
import time
import json
import sys
import cv2

def try_open(index=0, backend_pref='dshow', open_timeout_s=3, read_frames=2):
    backends = []
    if sys.platform.startswith('win'):
        if backend_pref == 'dshow':
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, None]
        elif backend_pref == 'msmf':
            backends = [cv2.CAP_MSMF, cv2.CAP_DSHOW, None]
        else:
            backends = [None, cv2.CAP_DSHOW, cv2.CAP_MSMF]
    else:
        backends = [None]

    start = time.time()
    for be in backends:
        try:
            if be is None:
                cap = cv2.VideoCapture(index)
            else:
                cap = cv2.VideoCapture(index, be)
        except Exception as e:
            cap = None
        if cap is None:
            continue
        ts0 = time.time()
        opened = cap.isOpened()
        if not opened:
            try:
                cap.release()
            except Exception:
                pass
            continue
        # try reading a couple frames
        ok_frames = 0
        t_deadline = time.time() + open_timeout_s
        while time.time() < t_deadline and ok_frames < read_frames:
            try:
                ok, frame = cap.read()
            except Exception:
                ok = False
                frame = None
            if ok and frame is not None:
                ok_frames += 1
            else:
                time.sleep(0.05)
        duration_ms = int((time.time() - start)*1000)
        info = {
            'attempt_backend': 'AUTO' if be is None else ('DSHOW' if be==cv2.CAP_DSHOW else ('MSMF' if be==cv2.CAP_MSMF else str(be))),
            'opened': True,
            'frames_read': ok_frames,
            'duration_ms': duration_ms
        }
        try:
            cap.release()
        except Exception:
            pass
        return info
    # nothing opened
    return {'attempt_backend': None, 'opened': False, 'frames_read': 0, 'duration_ms': int((time.time()-start)*1000)}

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--index', type=int, default=0)
    p.add_argument('--cycles', type=int, default=10)
    p.add_argument('--delay', type=float, default=1.0, help='delay between cycles (s)')
    args = p.parse_args()

    print(json.dumps({'ts': time.time(), 'type': 'camera_stress_start', 'index': args.index, 'cycles': args.cycles}))
    for i in range(args.cycles):
        t0 = time.time()
        res = try_open(index=args.index)
        res.update({'cycle': i+1})
        res['ts'] = time.time()
        print(json.dumps(res))
        sys.stdout.flush()
        time.sleep(args.delay)
    print(json.dumps({'ts': time.time(), 'type': 'camera_stress_done'}))
