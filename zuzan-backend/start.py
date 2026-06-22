"""
ZuZan server launcher — run this instead of uvicorn directly.
Strips null bytes from all .py files before starting, which prevents
the file-corruption crash that occurs when the server is killed mid-write.
"""
import os, sys, subprocess

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

def strip_null_bytes():
    fixed = []
    for fname in os.listdir(BACKEND_DIR):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(BACKEND_DIR, fname)
        try:
            with open(path, "rb") as f:
                content = f.read()
            if b"\x00" in content:
                cleaned = content.rstrip(b"\x00").replace(b"\x00", b"")
                with open(path, "wb") as f:
                    f.write(cleaned)
                fixed.append(fname)
        except Exception as e:
            print(f"[start] WARNING: could not check {fname}: {e}")
    if fixed:
        print(f"[start] Repaired null-byte corruption in: {', '.join(fixed)}")
    else:
        print("[start] All .py files clean.")

if __name__ == "__main__":
    strip_null_bytes()
    port = os.environ.get("PORT", "8000")
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", port]
    # Forward any extra args (e.g. --reload)
    cmd += sys.argv[1:]
    print(f"[start] Launching: {' '.join(cmd)}")
    sys.exit(subprocess.call(cmd))
