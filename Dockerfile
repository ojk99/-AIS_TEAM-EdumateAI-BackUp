# 1. 가볍고 안정적인 공식 파이썬 슬림 이미지 사용
FROM python:3.10-slim

# 2. 파이썬 버퍼링 비활성화 및 작업 디렉토리 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 3. 필수 패키지 설치
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 4. 프로젝트 전체 소스코드 복사
COPY . /app/

# 5. 외부 접속용 포트(8000) 개방
EXPOSE 8000

# 6. 도커 컨테이너 실행 명령어 (외부 접근 허용 0.0.0.0 바인딩)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
