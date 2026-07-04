# OTT Core Server Engine

A FastAPI and PostgreSQL backend implementation built for managing video streaming pipelines and playlist containers, integrated with Bunny CDN (Storage and Stream APIs).

## Folder Structure

```text
projectvideo-backend/
│
├── app/                        # Main application package
│   ├── static/                 # Static web assets served by FastAPI
│   │   ├── api.py              # Duplicate copy of Python API client boilerplate
│   │   └── index.html          # Interactive admin dashboard (with upload/play/edit options)
│   │
│   ├── main.py                 # FastAPI application startup, CORS setup, and API routes
│   ├── models.py               # SQLAlchemy database models (Videos, Playlists)
│   └── schemas.py              # Pydantic schemas for request validation & API responses
│
├── .env                        # Local configuration and secret keys (Ignored by Git)
├── .gitignore                  # Git ignore rules for cached/sensitive environment files
├── api.py                      # Standalone Python client boilerplate to interact with the API
├── README.md                   # This project documentation
└── requirements.txt            # Python dependencies lists
```
