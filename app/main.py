import importlib
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# 단독 실행(python app/main.py) 시에도 패키지 경로(app.*)를 인식하도록 루트 경로 추가
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ----------------------------------------------------------------------
# 1. 최상위 FastAPI 앱 인스턴스 생성
# ----------------------------------------------------------------------
app = FastAPI(
    title="EduMate AI - 다분야 맞춤형 AI 튜터 플랫폼",
    description="단원 목차 체계 기반 AI 맞춤형 튜터 & 온디맨드 퀴즈 통합 관제 플랫폼",
    version="1.07",
)

# CORS 설정 (웹 프론트엔드 연동 지원)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 마운트 (web/static -> /static)
STATIC_DIR = BASE_DIR / "web" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

LOBBY_HTML_PATH = BASE_DIR / "web" / "templates" / "index.html"
MYPAGE_HTML_PATH = BASE_DIR / "web" / "templates" / "mypage.html"


# ----------------------------------------------------------------------
# 2. 메인 통합 포털 로비 화면 (GET /) 및 공통 마이페이지 (GET /mypage)
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_portal_lobby():
    """EduMate AI 통합 포털 로비 (로그인 + 6개 과목 입장 버튼 + 실시간 명예의 전당 랭킹)"""
    if LOBBY_HTML_PATH.exists():
        return FileResponse(str(LOBBY_HTML_PATH))
    return HTMLResponse("<h1>web/templates/index.html 파일을 찾을 수 없습니다.</h1>", status_code=404)


@app.get("/mypage", response_class=HTMLResponse)
@app.get("/profile", response_class=HTMLResponse)
def serve_mypage():
    """EduMate AI 공통 마이페이지 (개인정보 수정 + 전과목 누적 점수/포켓몬 등급 + 오답노트/풀이DB + 문제은행/계정 관리)"""
    if MYPAGE_HTML_PATH.exists():
        return FileResponse(str(MYPAGE_HTML_PATH))
    return HTMLResponse("<h1>web/templates/mypage.html 파일을 찾을 수 없습니다.</h1>", status_code=404)


@app.get("/health")
def health_check():
    """EduMate AI 중앙 관제 서버 정상 구동 상태 확인"""
    return {
        "status": "online",
        "version": "1.7 test ver.",
        "message": "EduMate AI 중앙 서버가 정상 구동 중입니다.",
    }


# ----------------------------------------------------------------------
# 3. 플랫폼 공통 관제 라우터 결합 (랭킹, 관리자, 로그인, 개인정보)
# ----------------------------------------------------------------------
from app.routers.platform import router as platform_router

app.include_router(platform_router)

# ----------------------------------------------------------------------
# 4. 6대 과목 라우터 자동 결합 블록 (Step A & Step B 완벽 지원)
# ----------------------------------------------------------------------
# 1) 수학 (조장 전담 - 즉시 연결)
from app.subjects.math.router import router as math_router

app.include_router(math_router)

# 2) 타 과목 (국어, 영어, 사회, 과학, 한자)
# 조원들이 app/subjects/{과목명}/router.py 를 넣어두면 자동으로 연결되며,
# 아직 파일이 없거나 준비 중인 과목은 클릭 시 깔끔한 안내 화면이 표시됩니다.
OTHER_SUBJECTS = [
    ("korean", "국어"),
    ("english", "영어"),
    ("social", "사회"),
    ("science", "과학"),
    ("hanja", "한자"),
]


def _make_placeholder_route(subj_code: str, subj_kor: str):
    @app.get(f"/{subj_code}/", response_class=HTMLResponse, tags=[f"초등{subj_kor}(준비중)"])
    def _subject_placeholder():
        return HTMLResponse(
            f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>EduMate AI | {subj_kor} 과목 안내</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-6 text-slate-800">
    <div class="max-w-md w-full bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center space-y-5">
        <a href="/" class="inline-flex items-center gap-2.5 hover:opacity-80">
            <img src="/static/edumate_logo.svg" alt="EduMate AI" class="w-12 h-12 rounded-xl">
            <span class="text-lg font-extrabold text-slate-900">EduMate AI</span>
        </a>
        <div class="space-y-2">
            <span class="px-3 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-extrabold">{subj_kor} 플러그인 대기 중</span>
            <h1 class="text-xl font-extrabold text-slate-900">{subj_kor} 과목 모듈 연동 준비 완료</h1>
            <p class="text-xs text-slate-500 leading-relaxed">
                담당 조원의 <code class="bg-slate-100 px-1.5 py-0.5 rounded text-slate-700 font-bold">app/subjects/{subj_code}/</code> 파일이
                복사되면 자동으로 본 화면이 {subj_kor} AI 튜터 화면으로 전환됩니다.
            </p>
        </div>
        <a href="/" class="block w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-xs transition-all">
            포털 로비로 돌아가기
        </a>
    </div>
</body>
</html>"""
        )


for _code, _kor in OTHER_SUBJECTS:
    try:
        _mod = importlib.import_module(f"app.subjects.{_code}.router")
        _sub_router = getattr(_mod, "router", None)
        if _sub_router is not None and len(getattr(_sub_router, "routes", [])) > 0:
            # 조원 router.py 내부에 이미 prefix="/korean" 등이 설정되어 있으면 그대로, 없으면 prefix 부여
            if getattr(_sub_router, "prefix", ""):
                app.include_router(_sub_router)
            else:
                app.include_router(_sub_router, prefix=f"/{_code}", tags=[f"초등{_kor}"])
        else:
            _make_placeholder_route(_code, _kor)
    except Exception:
        _make_placeholder_route(_code, _kor)


# ----------------------------------------------------------------------
# 4. 표준 단독 실행 블록 (8000번 포트 자동 정리 + Cloudflared 터널 자동 연동)
# ----------------------------------------------------------------------
def _is_pid_running(pid: int) -> bool:
    """특정 PID 프로세스가 현재 윈도우에서 실행 중인지 확인합니다."""
    if not pid or pid <= 0:
        return False
    try:
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            encoding="cp949",
            errors="ignore",
        )
        return str(pid) in res.stdout
    except Exception:
        return False


def _free_port_8000():
    """기존에 8000번 포트를 점유 중인 이전 서버 프로세스를 자동으로 정리합니다."""
    if os.environ.get("RUN_MAIN") == "true":
        return
    try:
        current_pid = os.getpid()
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding="cp949", errors="ignore")
        pids_to_kill = set()
        for line in result.stdout.splitlines():
            if ":8000 " in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pid_str = parts[-1]
                    if pid_str.isdigit() and int(pid_str) != current_pid and int(pid_str) != 0:
                        pids_to_kill.add(int(pid_str))
        for pid in pids_to_kill:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    except Exception:
        pass


def _ensure_cloudflared_tunnel():
    """
    Cloudflared 터널을 백그라운드로 자동 구동하고 외부 공유 URL을 반환합니다.
    - Ctrl+C로 서버만 껐다 켤 때는 기존 터널(링크 주소)을 그대로 유지합니다.
    - 파워쉘(터미널) 창 자체를 닫으면 백그라운드 감시자가 터널도 함께 자동 종료합니다.
    """
    import json
    import re
    import shutil
    import time

    db_dir = BASE_DIR / "app" / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    state_file = db_dir / ".cloudflared_state.json"
    log_file = db_dir / ".cloudflared.log"

    # 1. 이미 살아있는 터널이 있는지 확인 (서버 재시작 시 기존 링크 그대로 유지)
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            old_pid = int(state.get("pid", 0))
            old_url = state.get("url", "")
            if old_url and _is_pid_running(old_pid):
                return old_url, True
        except Exception:
            pass

    # 2. cloudflared 실행 파일 경로 탐색
    cf_bin = shutil.which("cloudflared")
    if not cf_bin:
        for candidate in [
            r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            r"C:\Program Files\cloudflared\cloudflared.exe",
        ]:
            if os.path.exists(candidate):
                cf_bin = candidate
                break

    if not cf_bin:
        return None, False

    # 혹시 이전 터미널에서 비정상적으로 남은 좀비 cloudflared가 있다면 정리
    subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True)

    # 3. 새 터널 백그라운드 실행 (Ctrl+C 신호를 무시하도록 새 프로세스 그룹 분리)
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    try:
        log_fp = open(log_file, "w", encoding="utf-8", errors="ignore")
        cf_proc = subprocess.Popen(
            [cf_bin, "tunnel", "--url", "http://localhost:8000"],
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
    except Exception:
        return None, False

    # 4. 로그 파일에서 https://xxxx.trycloudflare.com 주소 추출 (최대 12초 대기)
    tunnel_url = None
    url_pattern = re.compile(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com")
    for _ in range(40):
        time.sleep(0.3)
        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            match = url_pattern.search(content)
            if match:
                tunnel_url = match.group(0)
                break
        except Exception:
            pass

    if tunnel_url:
        shell_pid = os.getppid()
        try:
            state_file.write_text(
                json.dumps({"pid": cf_proc.pid, "shell_pid": shell_pid, "url": tunnel_url}),
                encoding="utf-8",
            )
        except Exception:
            pass

        # 5. 터미널(파워쉘) 창이 닫히면 cloudflared도 자동 종료시키는 초경량 감시자 실행
        watchdog_code = (
            "import subprocess, time, os\n"
            f"shell_pid, cf_pid, state_path = {shell_pid}, {cf_proc.pid}, {repr(str(state_file))}\n"
            "def alive(p):\n"
            "    r = subprocess.run(['tasklist', '/FI', f'PID eq {p}', '/NH'], capture_output=True, text=True, errors='ignore')\n"
            "    return str(p) in r.stdout\n"
            "while alive(shell_pid) and alive(cf_pid):\n"
            "    time.sleep(2)\n"
            "if alive(cf_pid):\n"
            "    subprocess.run(['taskkill', '/F', '/PID', str(cf_pid)], capture_output=True)\n"
            "try:\n"
            "    if os.path.exists(state_path): os.remove(state_path)\n"
            "except Exception: pass\n"
        )
        try:
            subprocess.Popen(
                [sys.executable, "-c", watchdog_code],
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    return tunnel_url, False


def start_server():
    """포트 정리 + Cloudflared 터널 자동 연동 + Uvicorn 서버 가동을 한 번에 수행합니다."""
    import uvicorn

    if os.environ.get("RUN_MAIN") != "true":
        _free_port_8000()
        print("\n⏳ [EduMate AI] 서버 및 Cloudflared 외부 공유 터널을 준비 중입니다...")
        tunnel_url, is_reused = _ensure_cloudflared_tunnel()

        print("\n" + "=" * 68)
        print("🚀 [EduMate AI 통합 포털 서버 가동 - 1.7 test ver.]")
        print("👉 내 컴퓨터(로컬) 접속 : http://127.0.0.1:8000")
        print("👉 초등수학 바로 접속   : http://127.0.0.1:8000/math/")
        if tunnel_url:
            status_tag = "기존 링크 유지됨" if is_reused else "신규 개통 완료"
            print("-" * 68)
            print(f"🌍 [외부 공유 링크 ({status_tag})] 조원들에게 아래 주소를 공유하세요:")
            print(f"👉 {tunnel_url}")
            print("💡 서버를 잠시 껐다 켜도(Ctrl+C) 이 파워쉘 창을 닫지 않으면 주소가 유지됩니다!")
        else:
            print("-" * 68)
            print("⚠️ Cloudflared 터널 주소를 가져오지 못했습니다. (로컬 접속은 정상 작동)")
        print("=" * 68 + "\n")

    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 서버가 정상적으로 종료되었습니다. (터미널 복귀)")
        os._exit(0)


if __name__ == "__main__":
    start_server()

