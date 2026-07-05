import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from models import init_db
from routers import videos, playlists

# Initialize relational database tables on application boot
init_db()

app = FastAPI(title="OTT Core Server Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)

current_file_dir = Path(__file__).resolve().parent

@app.get("/")
def read_root():
    return FileResponse(current_file_dir / "static" / "index.html")

app.mount("/static", StaticFiles(directory=current_file_dir / "static"), name="static")

# Include modular API routers
app.include_router(videos.router)
app.include_router(videos.webhook_router)
app.include_router(playlists.router)

if __name__ == "__main__":
    import uvicorn
    # This acts as the bridge connecting your code to the machine's ports
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)