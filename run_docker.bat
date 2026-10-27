@echo off
chcp 65001 > nul

where docker >nul 2>nul
if errorlevel 1 goto NO_DOCKER

echo ========================================================
echo   [EduMate AI] 도커 컨테이너 서버를 빌드 및 가동합니다
echo ========================================================
echo.
echo 1. 도커 데스크탑[Docker Desktop]이 실행 중이어야 합니다.
echo 2. 브라우저 접속 주소: http://127.0.0.1:8000
echo.
echo 컨테이너를 시작합니다. 잠시만 기다려주세요...
echo.

docker compose up --build

echo.
echo 서버가 종료되었습니다.
pause
exit /b 0

:NO_DOCKER
echo.
echo ========================================================
echo  [안내] Docker[도커]가 설치되어 있지 않거나 실행 중이 아닙니다.
echo ========================================================
echo.
echo 1. Docker Desktop[도커 데스크탑]이 설치되어 있는지 확인해 주세요.
echo 2. 설치되어 있다면 도커 데스크탑을 먼저 실행해 주세요.
echo.
echo 3. 도커 없이 로컬에서 바로 실행하시려면 아래 명령어를 사용하세요:
echo.
echo    python run_dev.py
echo    또는
echo    uvicorn app.main:app --reload
echo.
pause
exit /b 1
