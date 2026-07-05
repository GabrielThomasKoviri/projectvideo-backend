import os
from pathlib import Path
from dotenv import load_dotenv

# Bulletproof Environment Resolution: Find the .env file in the outer root folder
current_file_dir = Path(__file__).resolve().parent
root_dir = current_file_dir.parent
dotenv_path = root_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Dynamic Secrets Assignment from Environment memory
BUNNY_API_KEY = os.getenv("BUNNY_API_KEY")
BUNNY_LIBRARY_ID = os.getenv("BUNNY_LIBRARY_ID")
BUNNY_CDN_URL = os.getenv("BUNNY_CDN_URL")
BUNNY_STORAGE_ZONE_NAME = os.getenv("BUNNY_STORAGE_ZONE_NAME")
BUNNY_STORAGE_API_KEY = os.getenv("BUNNY_STORAGE_API_KEY")
BUNNY_STORAGE_CDN_URL = os.getenv("BUNNY_STORAGE_CDN_URL")
if not BUNNY_STORAGE_CDN_URL and BUNNY_STORAGE_ZONE_NAME:
    BUNNY_STORAGE_CDN_URL = f"https://{BUNNY_STORAGE_ZONE_NAME}.b-cdn.net"
