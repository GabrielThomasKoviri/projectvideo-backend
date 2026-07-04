import os
import requests
from typing import List, Dict, Any, Optional

class OTTClient:
    """
    OTT Core Server API Python Client
    Simplifies interactions with the OTT backend server endpoints.
    """
    def __init__(self, base_url: str):
        # Strip trailing slash
        self.base_url = base_url.rstrip('/')

    def _handle_response(self, response: requests.Response) -> Any:
        try:
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        except requests.HTTPError as http_err:
            try:
                error_detail = response.json().get("detail", str(http_err))
            except Exception:
                error_detail = response.text or str(http_err)
            raise RuntimeError(f"API Error ({response.status_code}): {error_detail}") from http_err
        except Exception as err:
            raise RuntimeError(f"Connection/Response parsing error: {str(err)}") from err

    # ==========================================
    #  VIDEO PIPELINE ENDPOINTS
    # ==========================================

    def get_videos(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all videos, optionally filtered by user_id."""
        url = f"{self.base_url}/api/v1/videos"
        params = {"user_id": user_id} if user_id is not None else {}
        res = requests.get(url, params=params)
        return self._handle_response(res)

    def initiate_video_upload(
        self, 
        user_id: int, 
        title: str, 
        description: str = "", 
        category: str = "", 
        tags: str = "", 
        thumbnail_names: List[str] = None
    ) -> Dict[str, Any]:
        """
        Register video metadata and obtain Bunny Storage/TUS upload credentials.
        """
        url = f"{self.base_url}/api/v1/videos/initiate"
        payload = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "category": category,
            "tags": tags,
            "thumbnail_names": thumbnail_names or []
        }
        res = requests.post(url, json=payload)
        return self._handle_response(res)

    def get_video_playback(self, video_id: int) -> Dict[str, Any]:
        """Fetch playback streaming URL (.m3u8) and metadata for a video."""
        url = f"{self.base_url}/api/v1/videos/{video_id}/play"
        res = requests.get(url)
        return self._handle_response(res)

    def update_video(
        self, 
        video_id: int, 
        user_id: int, 
        title: Optional[str] = None, 
        description: Optional[str] = None, 
        category: Optional[str] = None, 
        tags: Optional[List[str]] = None,
        thumbnail_url: Optional[str] = None,
        alt_thumbnails: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Update existing video metadata details."""
        url = f"{self.base_url}/api/v1/videos/{video_id}"
        params = {"user_id": user_id}
        payload = {}
        if title is not None: payload["title"] = title
        if description is not None: payload["description"] = description
        if category is not None: payload["category"] = category
        if tags is not None: payload["tags"] = tags
        if thumbnail_url is not None: payload["thumbnail_url"] = thumbnail_url
        if alt_thumbnails is not None: payload["alt_thumbnails"] = alt_thumbnails
        
        res = requests.patch(url, params=params, json=payload)
        return self._handle_response(res)

    def delete_video(self, video_id: int, user_id: int) -> Dict[str, Any]:
        """Wipe video from database and Bunny Storage/Stream."""
        url = f"{self.base_url}/api/v1/videos/{video_id}"
        params = {"user_id": user_id}
        res = requests.delete(url, params=params)
        return self._handle_response(res)

    # ==========================================
    #  PLAYLIST ENDPOINTS
    # ==========================================

    def get_playlists(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all playlists, optionally filtered by user_id."""
        url = f"{self.base_url}/api/v1/playlists"
        params = {"user_id": user_id} if user_id is not None else {}
        res = requests.get(url, params=params)
        return self._handle_response(res)

    def create_playlist(
        self, 
        user_id: int, 
        name: str, 
        description: str = "", 
        thumbnail_name: str = "", 
        video_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Create a new playlist container."""
        url = f"{self.base_url}/api/v1/playlists"
        payload = {
            "user_id": user_id,
            "name": name,
            "description": description,
            "thumbnail_name": thumbnail_name,
            "video_ids": video_ids or []
        }
        res = requests.post(url, json=payload)
        return self._handle_response(res)

    def get_playlist(self, playlist_id: int, user_id: int) -> Dict[str, Any]:
        """View a specific playlist."""
        url = f"{self.base_url}/api/v1/playlists/{playlist_id}"
        params = {"user_id": user_id}
        res = requests.get(url, params=params)
        return self._handle_response(res)

    def update_playlist(
        self, 
        playlist_id: int, 
        user_id: int, 
        name: Optional[str] = None, 
        description: Optional[str] = None, 
        thumbnail_url: Optional[str] = None, 
        video_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Modify existing playlist container."""
        url = f"{self.base_url}/api/v1/playlists/{playlist_id}"
        params = {"user_id": user_id}
        payload = {}
        if name is not None: payload["name"] = name
        if description is not None: payload["description"] = description
        if thumbnail_url is not None: payload["thumbnail_url"] = thumbnail_url
        if video_ids is not None: payload["video_ids"] = video_ids
        
        res = requests.patch(url, params=params, json=payload)
        return self._handle_response(res)

    def delete_playlist(self, playlist_id: int, user_id: int) -> Dict[str, Any]:
        """Delete playlist container."""
        url = f"{self.base_url}/api/v1/playlists/{playlist_id}"
        params = {"user_id": user_id}
        res = requests.delete(url, params=params)
        return self._handle_response(res)

    # ==========================================
    #  UPLOAD DIRECT HELPERS (Bunny Storage / TUS)
    # ==========================================

    def upload_thumbnail(self, upload_url: str, headers: Dict[str, str], file_path: str) -> bool:
        """Uploads thumbnail image directly to Bunny CDN storage using credentials from initiate_upload."""
        with open(file_path, 'rb') as f:
            res = requests.put(upload_url, headers=headers, data=f)
        res.raise_for_status()
        return res.status_code in [200, 201]

    def upload_video_tus(self, tus_url: str, headers: Dict[str, str], file_path: str) -> None:
        """
        Simple TUS protocol helper client using the standard 'tuspy' library or pure requests.
        Note: For production, we recommend installing 'tuspy' (pip install tuspy).
        This pure-python block performs a single-chunk upload for simplicity.
        """
        file_size = os.path.getsize(file_path)
        
        # 1. Create upload session via TUS POST
        tus_headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(file_size),
        }
        tus_headers.update(headers)
        
        create_res = requests.post(tus_url, headers=tus_headers)
        create_res.raise_for_status()
        
        location = create_res.headers.get("Location")
        if not location:
            raise RuntimeError("Failed to receive TUS Location header from Bunny CDN")
        
        # 2. Upload file contents via TUS PATCH
        upload_headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream"
        }
        # Copy custom authorization headers needed for Bunny Stream
        for k, v in headers.items():
            if k.lower() not in ["tus-resumable", "upload-length"]:
                upload_headers[k] = v

        with open(file_path, 'rb') as f:
            patch_res = requests.patch(location, headers=upload_headers, data=f)
            patch_res.raise_for_status()


# Demonstration block showing how to use the client
if __name__ == "__main__":
    # Configure your API Endpoint
    API_URL = "http://localhost:8000"
    client = OTTClient(API_URL)
    
    print("Testing connection to OTT Backend...")
    try:
        videos = client.get_videos()
        print(f"Connection Successful! Found {len(videos)} videos.")
        for v in videos:
            print(f"- ID: {v['id']}, Title: {v['title']}, Status: {v['status']}")
    except Exception as e:
        print(f"Error connecting to backend: {e}")
