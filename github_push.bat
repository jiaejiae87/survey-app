@echo off
chcp 65001 > nul
title GitHub 저장소 업로드 도우미

cd /d "%~dp0"

echo ========================================================
echo       GitHub에 소스 코드를 업로드합니다.
echo ========================================================
echo.
echo GitHub(https://github.com)에서 새로 만든 저장소 주소(URL)를 복사한 뒤,
echo 아래에 붙여넣고 엔터(Enter)를 눌러주세요.
echo (예: https://github.com/내아이디/survey-app.git)
echo.

set /p REPO_URL="▶ GitHub 저장소 URL 입력: "

if "%REPO_URL%"=="" (
    echo [오류] URL이 입력되지 않았습니다.
    pause
    exit /b
)

echo.
echo [1/3] Git 브랜치 설정 중...
git branch -M main

echo [2/3] 원격 저장소 연결 중...
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo [3/3] GitHub로 업로드(Push) 중...
git push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo  ✅ GitHub 업로드가 성공적으로 완료되었습니다!
    echo  이제 Streamlit Cloud(https://share.streamlit.io)에서
    echo  Deploy를 진행하시면 됩니다.
    echo ========================================================
) else (
    echo.
    echo [알림] GitHub 로그인 창이 뜨면 로그인을 완료해 주세요.
)

echo.
pause
