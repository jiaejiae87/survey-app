import sys
import subprocess
import os

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

print("=" * 60)
print("       GitHub 저장소 업로드 도우미")
print("=" * 60)
print()
print("GitHub(https://github.com)에서 새로 만든 저장소 주소(URL)를 복사한 뒤,")
print("아래에 마우스 우클릭으로 붙여넣고 엔터(Enter)를 눌러주세요.")
print("예: https://github.com/내아이디/survey-app.git")
print()

try:
    repo_url = input("▶ GitHub 저장소 URL 입력: ").strip()
except Exception:
    repo_url = ""

if not repo_url:
    print("\n[오류] URL이 입력되지 않았습니다. 다시 실행해 주세요.")
    sys.exit(1)

print("\n[1/3] Git 기본 브랜치를 'main'으로 설정 중...")
subprocess.run(["git", "branch", "-M", "main"], check=False)

print("[2/3] 원격 저장소(origin) 연결 중...")
subprocess.run(["git", "remote", "remove", "origin"], check=False, stderr=subprocess.DEVNULL)
res_remote = subprocess.run(["git", "remote", "add", "origin", repo_url], check=False)

print("[3/3] GitHub로 소스 코드 업로드(Push) 중...")
res_push = subprocess.run(["git", "push", "-u", "origin", "main"], check=False)

if res_push.returncode == 0:
    print("\n" + "=" * 60)
    print("  ✅ GitHub 업로드가 성공적으로 완료되었습니다!")
    print("  이제 Streamlit Cloud(https://share.streamlit.io)에서")
    print("  Deploy를 진행하시면 됩니다.")
    print("=" * 60 + "\n")
else:
    print("\n" + "=" * 60)
    print("  [알림] GitHub 로그인 창이 브라우저나 팝업으로 떴다면")
    print("  로그인을 완료하신 후 다시 한번 이 창을 실행해 주세요.")
    print("=" * 60 + "\n")
