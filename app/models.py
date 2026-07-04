import enum
import os
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Text, ARRAY, Enum as SQLEnum, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

# Bulletproof path resolution to load the .env out of your root folder safely
current_file_dir = Path(__file__).resolve().parent
root_dir = current_file_dir.parent
dotenv_path = root_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/ott_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Many-to-Many Bridge Table linking Playlists and Videos together
playlist_video_association = Table(
    "playlist_video",
    Base.metadata,
    Column("playlist_id", Integer, ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True),
    Column("video_id", Integer, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
)

class VideoStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class VideoModel(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # Enforces individual user isolation
    bunny_video_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    thumbnail_url = Column(String(512), nullable=True)
    alt_thumbnails = Column(ARRAY(String), nullable=True)
    status = Column(SQLEnum(VideoStatus), default=VideoStatus.PENDING)

class PlaylistModel(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(String(512), nullable=True)  # Stores public cover graphic path
    user_id = Column(Integer, nullable=False, index=True)  # Enforces playlist owner validation
    
    # Resolves connected video items on data reads instantly
    videos = relationship("VideoModel", secondary=playlist_video_association, backref="playlists")

def init_db():
    Base.metadata.create_all(bind=engine)