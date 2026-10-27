# -*- coding: utf-8 -*-
"""
[EduMate AI - 초등사회] 단독 로컬 테스트용 웹 서버 (social/app.py)

실행 방법:
  uvicorn social.app:app --reload --port 8000
접속 주소:
  http://localhost:8000/ 또는 http://localhost:8000/social
"""

import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from social.router import router as social_router

app = FastAPI(
    title="EduMate AI 초등사회 탐험대",
    description="2022 개정 교육과정 초등사회 270문항 스마트 문제은행 플랫폼",
    version="1.0.0"
)

# 초등사회 라우터 마운트 (/social)
app.include_router(social_router)

SOCIAL_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/", response_class=HTMLResponse)
def root_home():
    """루트 경로 접속 시 초등사회 메인 화면으로 연결"""
    html_path = os.path.join(SOCIAL_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse("<h3>index.html을 찾을 수 없습니다.</h3>", status_code=404)


@app.get("/questions_data.js")
def root_questions_data():
    """루트 경로에서 questions_data.js 요청 시 파일 반환"""
    js_path = os.path.join(SOCIAL_DIR, "questions_data.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    return HTMLResponse("questions_data.js not found", status_code=404)


@app.get("/images/{image_name}")
def root_images(image_name: str):
    """루트 경로에서 문화재 실물 사진 요청 시 서빙"""
    img_path = os.path.join(SOCIAL_DIR, "images", image_name)
    if os.path.exists(img_path):
        media_type = "image/jpeg"
        if image_name.endswith(".webp"):
            media_type = "image/webp"
        elif image_name.endswith(".png"):
            media_type = "image/png"
        return FileResponse(img_path, media_type=media_type)
    return HTMLResponse("Image not found", status_code=404)


@app.get("/logo.svg")
@app.get("/edumate_logo.svg")
def root_logo():
    """루트 경로에서 EduMate AI 공식 로고 서빙"""
    logo_path = os.path.join(SOCIAL_DIR, "edumate_logo.svg")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/svg+xml")
    return HTMLResponse("Logo not found", status_code=404)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("social.app:app", host="0.0.0.0", port=8080, reload=True)
