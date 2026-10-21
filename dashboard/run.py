"""
Start the GEWS Watch Console (backend API + frontend on one port).

    python dashboard/run.py            # http://127.0.0.1:8000
    python dashboard/run.py --port 9000
"""
import argparse, os, sys

import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"GEWS Watch Console -> http://{a.host}:{a.port}")
    uvicorn.run("dashboard.backend.main:app", host=a.host, port=a.port)
