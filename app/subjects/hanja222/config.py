"""과목 폴더부터 프로젝트 루트까지 설정 탐색. 기존 OS 값은 덮어쓰지 않는다."""
import os
from pathlib import Path
from dotenv import dotenv_values

BASE = Path(__file__).resolve().parent
PROJECT_ROOT = BASE.parents[2]

def load_settings(base=BASE, project_root=PROJECT_ROOT):
    values = {}
    current = Path(base).resolve()
    stop = Path(project_root).resolve()
    while True:
        path = current / '.env'
        if path.is_file():
            for key, value in dotenv_values(path).items():
                if value and key not in values:
                    values[key] = value
        if current == stop or current.parent == current:
            break
        current = current.parent
    # 과목 파일 > 상위 파일 > OS 환경변수. os.environ에는 비밀을 복사하지 않음.
    return {**os.environ, **values}

def api_key():
    settings = load_settings()
    return settings.get('GEMINI_API_KEY', '').strip() or settings.get('GOOGLE_API_KEY', '').strip()

def key_help():
    return 'GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다. 한자 폴더 또는 프로젝트 루트의 .env 파일이나 시스템 환경변수를 확인하세요.'
