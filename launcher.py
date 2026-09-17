import subprocess
import time
import urllib.request
import webbrowser
import sys
import os

# 윈도우 콘솔 인코딩 에러 방지
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

app_file = os.path.join(current_dir, "app.py")
url = "http://127.0.0.1:8501"

print("=" * 60)
print("  [만족도 조사 실시간 집계 시스템]")
print("  서버를 시작하고 있습니다. 잠시만 기다려 주세요 (약 2~3초)...")
print("=" * 60, flush=True)

cmd = [
    sys.executable,
    "-m",
    "streamlit",
    "run",
    app_file,
    "--server.port",
    "8501",
    "--server.address",
    "127.0.0.1",
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false"
]

proc = subprocess.Popen(cmd)

server_ready = False
for _ in range(60):
    if proc.poll() is not None:
        print("\n[오류] 서버 실행이 중단되었습니다.", flush=True)
        break
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=1) as response:
            if response.status == 200:
                server_ready = True
                break
    except Exception:
        time.sleep(0.5)

if server_ready:
    print("\n* 서버가 준비되었습니다!", flush=True)
    print(f"* 인터넷 브라우저를 엽니다: {url}", flush=True)
    webbrowser.open(url)
    print("\n" + "=" * 60)
    print("  집계 시스템이 정상 작동 중입니다.")
    print("  ※ 사용을 마치실 때까지 이 검은 콘솔 창을 닫지 마세요.")
    print("  ※ 종료하시려면 이 창을 닫으시면 됩니다.")
    print("=" * 60 + "\n", flush=True)
else:
    print(f"\n* 인터넷 브라우저 주소창에 직접 입력하세요: {url}", flush=True)

try:
    proc.wait()
except KeyboardInterrupt:
    proc.terminate()
