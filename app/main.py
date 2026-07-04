import os
import time
import hashlib
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv
import requests

# 1. Bulletproof Environment Resolution: Find the .env file in the outer root folder
current_file_dir = Path(__file__).resolve().parent
root_dir = current_file_dir.parent
dotenv_path = root_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

# 2. Package Relative Imports for the Modular Structure
from models import SessionLocal, VideoModel, PlaylistModel, VideoStatus, init_db
from schemas import (
    VideoInitiateSchema, VideoUpdateSchema, VideoResponseSchema,
    PlaylistCreateSchema, PlaylistUpdateSchema, PlaylistResponseSchema, PlaylistCreateResponseSchema
)

# 3. Dynamic Secrets Assignment from Environment memory
BUNNY_API_KEY = os.getenv("BUNNY_API_KEY")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")
BUNNY_CDN_URL = os.getenv("BUNNY_CDN_URL")
BUNNY_STORAGE_ZONE_NAME = os.getenv("BUNNY_STORAGE_ZONE_NAME")
BUNNY_STORAGE_API_KEY = os.getenv("BUNNY_STORAGE_API_KEY")
BUNNY_STORAGE_CDN_URL = os.getenv("BUNNY_STORAGE_CDN_URL")
if not BUNNY_STORAGE_CDN_URL and BUNNY_STORAGE_ZONE_NAME:
    BUNNY_STORAGE_CDN_URL = f"https://{BUNNY_STORAGE_ZONE_NAME}.b-cdn.net"

app = FastAPI(title="OTT Core Server Engine API")

# Initialize relational database tables on application boot
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)

@app.get("/")
def read_root():
    return FileResponse(current_file_dir / "static" / "index.html")

app.mount("/static", StaticFiles(directory=current_file_dir / "static"), name="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
#  VIDEO PIPELINE ROUTER ENDPOINTS
# ==========================================

# api/v1/videos/initiate - when clicking upload button - post
@app.post("/api/v1/videos/initiate")
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
        raise HTTPException(status_code=500, detail=f"Bunny Library Handshake Failure: {str(e)}")

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
@app.post("/api/v1/webhooks/bunny")
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

# api/v1/videos/{video_id}/play - get video playback config - get
@app.get("/api/v1/videos/{video_id}/play")
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
@app.get("/api/v1/videos", response_model=List[VideoResponseSchema])
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
@app.patch("/api/v1/videos/{video_id}", response_model=VideoResponseSchema)
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

# api/v1/videos/:video_id - to delete a video - delete
@app.delete("/api/v1/videos/{video_id}", status_code=status.HTTP_200_OK)
def delete_video(video_id: int, user_id: int, db: Session = Depends(get_db)):
    video = db.query(VideoModel).filter(VideoModel.id == video_id, VideoModel.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found or access unauthorized.")
        
    bunny_delete_url = f"https://video.bunnycdn.com/library/{BUNNY_LIBRARY_ID}/videos/{video.bunny_video_id}"
    try:
        requests.delete(bunny_delete_url, headers={"AccessKey": BUNNY_API_KEY}).raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear files from Bunny CDN: {str(e)}")

    # Delete thumbnail from Bunny Storage
    delete_from_bunny_storage(video.thumbnail_url)

    db.delete(video)
    db.commit()
    return {"status": "success", "message": "Video successfully wiped from database and CDN storage blocks."}

# ==========================================
#  PLAYLIST MANAGEMENT ROUTER ENDPOINTS
# ==========================================

# api/v1/playlists - to create a playlist - post
@app.post("/api/v1/playlists", response_model=PlaylistCreateResponseSchema, status_code=status.HTTP_201_CREATED)
def create_playlist(payload: PlaylistCreateSchema, db: Session = Depends(get_db)):
    file_extension = payload.thumbnail_name.split(".")[-1] if "." in payload.thumbnail_name else "jpg"
    unique_filename = f"playlist_{payload.user_id}_{int(time.time())}.{file_extension}"
    
    public_cdn_path = f"{BUNNY_STORAGE_CDN_URL}/assets/playlists/{unique_filename}"
    storage_upload_target = f"https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE_NAME}/assets/playlists/{unique_filename}"

    playlist = PlaylistModel(name=payload.name, description=payload.description, thumbnail_url=public_cdn_path, user_id=payload.user_id)
    
    if payload.video_ids:
        videos = db.query(VideoModel).filter(VideoModel.id.in_(payload.video_ids), VideoModel.user_id == payload.user_id).all()
        playlist.videos = videos
        
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    
    return {
        "id": playlist.id, "user_id": playlist.user_id, "name": playlist.name, "description": playlist.description,
        "thumbnail_url": playlist.thumbnail_url, "image_upload_url": storage_upload_target,
        "image_upload_headers": {"AccessKey": BUNNY_STORAGE_API_KEY}, "videos": playlist.videos
    }

# api/v1/playlists - to get all playlists - get
@app.get("/api/v1/playlists", response_model=List[PlaylistResponseSchema])
def get_all_playlists(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(PlaylistModel).options(joinedload(PlaylistModel.videos))
    if user_id is not None:
        query = query.filter(PlaylistModel.user_id == user_id)
    return query.all()

# api/v1/playlists/:playlist_id - to view the playlist - get
@app.get("/api/v1/playlists/{playlist_id}", response_model=PlaylistResponseSchema)
def view_playlist(playlist_id: int, user_id: int, db: Session = Depends(get_db)):
    playlist = db.query(PlaylistModel).options(joinedload(PlaylistModel.videos)).filter(PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist target not found or access unauthorized.")
    return playlist

# api/v1/playlists/:playlist_id - to edit a playlist - patch
@app.patch("/api/v1/playlists/{playlist_id}", response_model=PlaylistResponseSchema)
def edit_playlist(playlist_id: int, user_id: int, payload: PlaylistUpdateSchema, db: Session = Depends(get_db)):
    playlist = db.query(PlaylistModel).filter(PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist target not found or access unauthorized.")
        
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data: playlist.name = update_data["name"]
    if "description" in update_data: playlist.description = update_data["description"]
    if "thumbnail_url" in update_data: playlist.thumbnail_url = update_data["thumbnail_url"]
        
    if "video_ids" in update_data:
        video_ids = update_data["video_ids"]
        if video_ids:
            videos = db.query(VideoModel).filter(VideoModel.id.in_(video_ids), VideoModel.user_id == user_id).all()
            playlist.videos = videos
        else:
            playlist.videos = []
        
    db.commit()
    db.refresh(playlist)
    return playlist

# api/v1/playlists/:playlist_id - to delete a playlist - delete
@app.delete("/api/v1/playlists/{playlist_id}", status_code=status.HTTP_200_OK)
def delete_playlist(playlist_id: int, user_id: int, db: Session = Depends(get_db)):
    playlist = db.query(PlaylistModel).filter(PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist target not found or access unauthorized.")
        
    # Delete cover from Bunny Storage
    delete_from_bunny_storage(playlist.thumbnail_url)

    db.delete(playlist)
    db.commit()
    return {"status": "success", "message": "Playlist container dropped successfully."}

if __name__ == "__main__":
    import uvicorn
    # This acts as the bridge connecting your code to the machine's ports
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)