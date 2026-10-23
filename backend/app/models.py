import enum
from sqlalchemy import Column, Integer, String, Text, Enum as SQLEnum, DateTime
from datetime import datetime
from .db import Base

class TaskStatus(str, enum.Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    source = Column(String(50), default="telegram", nullable=False) # e.g., telegram_text, telegram_voice
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)