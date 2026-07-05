import os
import time
import hashlib
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, status
from sqlalchemy.orm import Session
import requests

from models import VideoModel, VideoStatus, get_db
from schemas import (
    VideoInitiateSchema, VideoUpdateSchema, VideoResponseSchema
)
from config import (
    BUNNY_API_KEY, BUNNY_LIBRARY_ID, BUNNY_CDN_URL,
    BUNNY_STORAGE_ZONE_NAME, BUNNY_STORAGE_API_KEY, BUNNY_STORAGE_CDN_URL
)

router = APIRouter(prefix="/api/v1/videos", tags=["Videos"])
webhook_router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

def check_and_update_video_status(video: VideoModel, db: Session) -> VideoModel:
    if video.status == VideoStatus.READY:
        return video
    
    bunny_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{video.bunny_video_id}"
    headers = {
        "accept": "application/json",
        "AccessKey": BUNNY_API_KEY
    }
    try:
        res = requests.get(bunny_url, headers=headers, timeout=5)
        if res.status_code == 200:
            bunny_status = res.json().get("status")
            if bunny_status in [3, 4]:
                video.status = VideoStatus.READY
                db.commit()
                db.refresh(video)
            elif bunny_status == 5:
                video.status = VideoStatus.FAILED
                db.commit()
                db.refresh(video)
            elif bunny_status in [0, 1, 2]:
                if video.status != VideoStatus.PROCESSING:
                    video.status = VideoStatus.PROCESSING
                    db.commit()
                    db.refresh(video)
    except Exception as e:
        print(f"Error checking video status on Bunny CDN: {e}")
    return video

def delete_from_bunny_storage(file_url: str):
    if not file_url or not BUNNY_STORAGE_API_KEY:
        return
    if "/assets/" in file_url:
        relative_path = "assets/" + file_url.split("/assets/")[-1]
        delete_url = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE_NAME}/{relative_path}"
        headers = {
            "AccessKey": BUNNY_STORAGE_API_KEY
        }
        try:
            res = requests.delete(delete_url, headers=headers, timeout=5)
            print(f"Deleted {relative_path} from Bunny Storage: status {res.status_code}")
        except Exception as e:
            print(f"Failed to delete {relative_path} from Bunny Storage: {e}")

# api/v1/videos/initiate - when clicking upload button - post
@router.post("/initiate")
async def initiate_upload(
    payload: VideoInitiateSchema,
    db: Session = Depends(get_db)
):
    # --- PHASE 1: Register the Video Entry slot inside Bunny CDN ---
    bunny_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos"
    headers = {
        "accept": "application/json", 
        "content-type": "application/json", 
        "AccessKey": BUNNY_API_KEY
    }
    
    try:
        res = requests.post(bunny_url, json={"title": payload.title}, headers=headers)
        res.raise_for_status()
        bunny_video_id = res.json()["guid"]
    except Exception as e:
        print(f"Error during Bunny CDN Handshake: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to initialize video entry with Bunny CDN Stream Library."
        )

    # --- PHASE 2: Generate storage targets for exactly 3 Thumbnails ---
    if not payload.thumbnail_names or len(payload.thumbnail_names) != 3:
        raise HTTPException(status_code=400, detail="Exactly 3 thumbnail filenames must be provided.")
        
    thumbnail_uploads = []
    alt_thumbnails = []
    
    for idx, name in enumerate(payload.thumbnail_names):
        file_extension = name.split(".")[-1] if "." in name else "jpg"
        unique_filename = f"video_{payload.user_id}_{int(time.time())}_{idx}.{file_extension}"
        
        upload_target = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE_NAME}/assets/thumbnails/{unique_filename}"
        public_cdn_path = f"{BUNNY_STORAGE_CDN_URL}/assets/thumbnails/{unique_filename}"
        
        thumbnail_uploads.append({
            "upload_url": upload_target,
            "public_url": public_cdn_path
        })
        alt_thumbnails.append(public_cdn_path)
 
    default_thumbnail_url = alt_thumbnails[0]

    # --- PHASE 3: Generate TUS credentials ---
    expire_time = int(time.time()) + 3600
    raw_sig_str = f"{BUNNY_LIBRARY_ID}{BUNNY_API_KEY}{expire_time}{bunny_video_id}"
    signature = hashlib.sha256(raw_sig_str.encode("utf-8")).hexdigest()

    # --- PHASE 4: Commit structural references to your local PostgreSQL ---
    tags_list = [t.strip() for t in payload.tags.split(",") if t.strip()] if payload.tags else []

    db_video = VideoModel(
        user_id=payload.user_id, 
        bunny_video_id=bunny_video_id, 
        title=payload.title, 
        description=payload.description,
        category=payload.category, 
        tags=tags_list, 
        thumbnail_url=default_thumbnail_url,
        alt_thumbnails=alt_thumbnails, 
        status=VideoStatus.PENDING
    )
    
    db.add(db_video)
    db.commit()
    db.refresh(db_video)

    # Returns the target direct TUS upload link and storage headers straight back to frontend!
    return {
        "id": db_video.id, 
        "bunny_video_id": db_video.bunny_video_id, 
        "status": db_video.status,
        "tus_url": "https://video.bunnycdn.com/tusupload",
        "tus_headers": {
            "AuthorizationSignature": signature,
            "AuthorizationExpire": str(expire_time),
            "LibraryId": str(BUNNY_LIBRARY_ID),
            "VideoId": bunny_video_id
        },
        "thumbnail_uploads": thumbnail_uploads,
        "thumbnail_upload_headers": {
            "AccessKey": BUNNY_STORAGE_API_KEY
        }
    }

# api/v1/webhooks/bunny - webhook endpoint - post
@webhook_router.post("/bunny")
async def bunny_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    bunny_video_id = payload.get("VideoGuid")
    status_code = payload.get("Status")
    
    video = db.query(VideoModel).filter(VideoModel.bunny_video_id == bunny_video_id).first()
    if video and status_code == 3:  # 3 indicates finished encoding successfully
        video.status = VideoStatus.READY
        db.commit()
        return {"status": "success"}
    return {"status": "ignored"}

# api/v1/videos/{video_id}/play - get video playback config - get
@router.get("/{video_id}/play")
def get_video_playback(video_id: int, db: Session = Depends(get_db)):
    video = db.query(VideoModel).filter(VideoModel.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video metadata target not found.")
    video = check_and_update_video_status(video, db)
    if video.status != VideoStatus.READY:
        raise HTTPException(status_code=400, detail="Streaming formats are processing and not ready yet.")

    return {
        "title": video.title,
        "stream_url": f"{BUNNY_CDN_URL}/{video.bunny_video_id}/playlist.m3u8", 
        "poster": video.thumbnail_url
    }

# api/v1/videos - to show all videos - get
@router.get("", response_model=List[VideoResponseSchema])
def show_all_videos(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(VideoModel)
    if user_id is not None:
        query = query.filter(VideoModel.user_id == user_id)
    videos = query.all()
    for video in videos:
        if video.status != VideoStatus.READY:
            check_and_update_video_status(video, db)
    return videos

# api/v1/videos/:video_id - to edit the videos details - patch
@router.patch("/{video_id}", response_model=VideoResponseSchema)
def edit_video_details(video_id: int, user_id: int, payload: VideoUpdateSchema, db: Session = Depends(get_db)):
    video = db.query(VideoModel).filter(VideoModel.id == video_id, VideoModel.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found or access unauthorized.")
    
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(video, key, value)
        
    db.commit()
    db.refresh(video)
    return video

# api/v1/videos/:video_id - to delete a video - delete
@router.delete("/{video_id}", status_code=status.HTTP_200_OK)
def delete_video(video_id: int, user_id: int, db: Session = Depends(get_db)):
    video = db.query(VideoModel).filter(VideoModel.id == video_id, VideoModel.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found or access unauthorized.")
        
    bunny_delete_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{video.bunny_video_id}"
    try:
        requests.delete(bunny_delete_url, headers={"AccessKey": BUNNY_API_KEY}).raise_for_status()
    except Exception as e:
        print(f"Error deleting video from Bunny Stream: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to remove video from Bunny CDN Stream Library."
        )

    # Delete thumbnail from Bunny Storage
    delete_from_bunny_storage(video.thumbnail_url)

    db.delete(video)
    db.commit()
    return {"status": "success", "message": "Video successfully wiped from database and CDN storage blocks."}
