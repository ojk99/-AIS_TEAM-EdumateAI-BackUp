"""한자 전용 ORM 모델. 팀 공통 테이블과 이름이 겹치지 않는다."""
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, JSON, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase):pass
class IssuedQuestion(Base):
    __tablename__='hanja_issued_questions'
    id:Mapped[str]=mapped_column(String(100),primary_key=True)
    owner:Mapped[str]=mapped_column(String(160),index=True)
    payload:Mapped[dict]=mapped_column(JSON)
    expires:Mapped[float]=mapped_column()
class QuizLog(Base):
    __tablename__='hanja_quiz_logs'
    question_id:Mapped[str]=mapped_column(String(100),primary_key=True)
    owner:Mapped[str]=mapped_column(String(160),index=True)
    question_type:Mapped[str]=mapped_column(String(40))
    question:Mapped[str]=mapped_column(Text)
    character:Mapped[str]=mapped_column(String(30))
    grade:Mapped[int|None]=mapped_column(Integer,nullable=True)
    submitted_answer:Mapped[str]=mapped_column(Text)
    expected_answer:Mapped[str]=mapped_column(Text)
    score:Mapped[int]=mapped_column(Integer)
    base_score:Mapped[int]=mapped_column(Integer)
    correct:Mapped[bool]=mapped_column(Boolean)
    feedback:Mapped[str]=mapped_column(Text)
    result:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime)
