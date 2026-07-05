import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session, joinedload

from models import VideoModel, PlaylistModel, get_db
from schemas import (
    PlaylistCreateSchema, PlaylistUpdateSchema, PlaylistResponseSchema, PlaylistCreateResponseSchema
)
from config import BUNNY_STORAGE_ZONE_NAME, BUNNY_STORAGE_API_KEY, BUNNY_STORAGE_CDN_URL
from routers.videos import delete_from_bunny_storage

router = APIRouter(prefix="/api/v1/playlists", tags=["Playlists"])

# api/v1/playlists - to create a playlist - post
@router.post("", response_model=PlaylistCreateResponseSchema, status_code=status.HTTP_201_CREATED)
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
@router.get("", response_model=List[PlaylistResponseSchema])
def get_all_playlists(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(PlaylistModel).options(joinedload(PlaylistModel.videos))
    if user_id is not None:
        query = query.filter(PlaylistModel.user_id == user_id)
    return query.all()

# api/v1/playlists/:playlist_id - to view the playlist - get
@router.get("/{playlist_id}", response_model=PlaylistResponseSchema)
def view_playlist(playlist_id: int, user_id: int, db: Session = Depends(get_db)):
    playlist = db.query(PlaylistModel).options(joinedload(PlaylistModel.videos)).filter(PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist target not found or access unauthorized.")
    return playlist

# api/v1/playlists/:playlist_id - to edit a playlist - patch
@router.patch("/{playlist_id}", response_model=PlaylistResponseSchema)
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
@router.delete("/{playlist_id}", status_code=status.HTTP_200_OK)
def delete_playlist(playlist_id: int, user_id: int, db: Session = Depends(get_db)):
    playlist = db.query(PlaylistModel).filter(PlaylistModel.id == playlist_id, PlaylistModel.user_id == user_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist target not found or access unauthorized.")
        
    # Delete cover from Bunny Storage
    delete_from_bunny_storage(playlist.thumbnail_url)

    db.delete(playlist)
    db.commit()
    return {"status": "success", "message": "Playlist container dropped successfully."}
