import enum
import uuid
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Enum, Index, text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Fixed set of job states (strict system-level status)
class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    # Primary key (unique user ID, UUID instead of 1,2,3)
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,                 # generated in Python
        server_default=text("gen_random_uuid()")  # fallback in DB
    )

    # Login identifier (must be unique + fast lookup)
    email = Column(String, unique=True, nullable=False, index=True)

    # Public username (also unique + indexed for lookup)
    username = Column(String, unique=True, nullable=False, index=True)

    # Hashed password (never store raw password)
    hashed_password = Column(String, nullable=False)

    # Account active flag (soft disable users)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)

    # Auto timestamp when user is created
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # ORM shortcuts (NOT real DB columns)

    # All refresh tokens belonging to user
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"  # delete tokens if user is deleted
    )

    # All jobs belonging to user
    jobs = relationship(
        "Job",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    # Unique token row ID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )

    # Hashed refresh token (security: never store raw token)
    token_hash = Column(String, unique=True, nullable=False, index=True)

    # Link to user (foreign key relationship)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # When this token expires
    expires_at = Column(DateTime, nullable=False)

    # Manual invalidation flag (logout / revoke)
    revoked = Column(Boolean, default=False, server_default=text("false"), nullable=False)

    # When token was created
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # ORM back-reference → token.user gives User object
    user = relationship("User", back_populates="refresh_tokens")


class Job(Base):
    __tablename__ = "jobs"

    # Unique job ID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )

    # Owner of the job
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Original uploaded file name (optional metadata)
    original_filename = Column(String, nullable=True)

    # Where file lives in S3 (not stored in DB itself)
    s3_input_key = Column(String, nullable=True)

    # High-level job lifecycle state (strict enum)
    status = Column(
        Enum(JobStatus),
        default=JobStatus.PENDING,
        server_default=text("'PENDING'"),
        nullable=False
    )

    # Background worker task ID (Celery tracking)
    celery_task_id = Column(String, nullable=True)

    # Progress percent for UI (0–100)
    progress_pct = Column(Integer, default=0, server_default=text("0"), nullable=False)

    # Human-readable current step (flexible string for UI)
    progress_stage = Column(String, nullable=True)

    # Error details if job fails
    error_message = Column(String, nullable=True)

    # Total video length (if applicable)
    duration_seconds = Column(Integer, nullable=True)

    # Soft delete flag (don’t actually remove row)
    is_deleted = Column(Boolean, default=False, server_default=text("false"), nullable=False)

    # When job was created
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # When job finished (null = still running)
    completed_at = Column(DateTime, nullable=True)

    # ORM relationships (Python convenience only)

    # Job → User
    user = relationship("User", back_populates="jobs")

    # Job → many highlights (clips extracted from job)
    highlights = relationship(
        "Highlight",
        back_populates="job",
        cascade="all, delete-orphan"
    )

    # Database performance index (fast lookup by user + filter deleted)
    __table_args__ = (
        Index("ix_jobs_user_id_deleted", "user_id", "is_deleted"),
    )


class Highlight(Base):
    __tablename__ = "highlights"

    # Unique highlight ID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )

    # Which job this highlight belongs to
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False
    )

    # Order of highlight within job (0,1,2...)
    index = Column(Integer, nullable=False)

    # Where output video clip is stored in S3
    s3_output_key = Column(String, nullable=False)

    # Start time in original video (seconds)
    start_second = Column(Float, nullable=False)

    # End time in original video (seconds)
    end_second = Column(Float, nullable=False)

    # AI confidence / ranking score
    score = Column(Float, nullable=False)

    # Whether model is unsure about this highlight
    low_confidence = Column(Boolean, default=False, server_default=text("false"), nullable=False)

    # Duration of clip
    duration_seconds = Column(Float, nullable=False)

    # When highlight was created
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # ORM back-reference → highlight.job gives Job object
    job = relationship("Job", back_populates="highlights")