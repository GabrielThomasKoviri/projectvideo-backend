from typing import List, Optional
from pydantic import BaseModel

# --- VIDEO PIPELINE INTEGRITY ---
class VideoInitiateSchema(BaseModel):
    user_id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = ""
    thumbnail_names: List[str]

class VideoUpdateSchema(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    thumbnail_url: Optional[str] = None
    alt_thumbnails: Optional[List[str]] = None

class VideoResponseSchema(BaseModel):
    id: int
    user_id: int
    bunny_video_id: str
    title: str
    description: Optional[str]
    category: Optional[str]
    tags: List[str]
    thumbnail_url: Optional[str]
    alt_thumbnails: Optional[List[str]] = []
    status: str

    class Config:
        from_attributes = True

# --- PLAYLIST MANAGEMENT INTEGRITY ---
class PlaylistCreateSchema(BaseModel):
    name: str
    description: Optional[str] = None
    user_id: int
    thumbnail_name: str  # e.g., "cover.png" -> Backend calculates target file extension
    video_ids: Optional[List[int]] = []

class PlaylistUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_ids: Optional[List[int]] = None

class PlaylistResponseSchema(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    videos: List[VideoResponseSchema] = []

    class Config:
        from_attributes = True

# Specialized registration payload returning direct-to-cloud PUT token destinations
class PlaylistCreateResponseSchema(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str]
    thumbnail_url: str
    image_upload_url: str
    image_upload_headers: Optional[dict] = None
    videos: List[VideoResponseSchema] = []

    class Config:
        from_attributes = True