import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Enum as SQLEnum, DateTime, text
from datetime import datetime
import enum
import redis.asyncio as aioredis
from pydantic import BaseModel

# 1. Environment Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/tasks")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# 2. Database Setup
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# 3. Task Model & Schema Definition
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
    source = Column(String(50), default="telegram", nullable=False)  # e.g., telegram_text, telegram_voice
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class TaskUpdate(BaseModel):
    status: TaskStatus


# 4. FastAPI Application Initialization
app = FastAPI(title="AI Task Bot API")

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Create database tables automatically for development
        await conn.run_sync(Base.metadata.create_all)


# Pydantic Schemas
class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    source: str = "telegram"


class TaskResponse(TaskCreate):
    id: int
    status: TaskStatus
    created_at: datetime

    class Config:
        from_attributes = True


# 5. API Endpoints

@app.get("/")
def read_root():
    return {"message": "AI Task Management API is running!"}


@app.get("/tasks")
async def get_tasks(db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    tasks = result.scalars().all()
    return tasks


@app.post("/tasks", response_model=TaskResponse)
async def create_task(task_in: TaskCreate, db: AsyncSession = Depends(get_db)):
    new_task = Task(
        title=task_in.title,
        description=task_in.description,
        source=task_in.source,
        status=TaskStatus.PENDING
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task

@app.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = body.status
    await db.commit()
    await db.refresh(task)
    return task


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint evaluating PostgreSQL and Redis connectivity."""
    health_status = {
        "status": "healthy",
        "services": {
            "postgres": "unknown",
            "redis": "unknown"
        }
    }

    # Check PostgreSQL connection
    try:
        await db.execute(text("SELECT 1"))
        health_status["services"]["postgres"] = "healthy"
    except Exception as e:
        health_status["services"]["postgres"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis connection
    try:
        redis = aioredis.from_url(REDIS_URL)
        await redis.ping()
        await redis.close()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    if health_status["status"] != "healthy":
        raise HTTPException(
            status_code=503,
            detail=health_status
        )

    return health_status
