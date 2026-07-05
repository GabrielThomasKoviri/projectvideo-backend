# Architecture and System Design Documentation

This document explains the technical design of the OTT Core Server Engine, detailing the database models, API endpoints, Pydantic schemas, and how they connect to manage media ingestion and streaming.

---

## Beginner's Introduction: What are SQLAlchemy, Pydantic, Models, and Schemas?

If you have never built a backend with Python, these terms can sound confusing. Let's explain them from absolute scratch using a simple analogy: **running a restaurant**.

### The Restaurant Analogy

| Term / Technology | Restaurant Analogy | What it does in our Code |
| :--- | :--- | :--- |
| **SQL Database (PostgreSQL)** | The Kitchen Freezer | Where the raw food (raw data) is stored permanently. |
| **SQLAlchemy (The Database ORM)** | The Head Chef | The translator. Takes orders from Python and goes into the freezer to get exactly what is needed without you needing to know where it's stored. |
| **Pydantic (Validation Schema)** | The Order Slip Validator | The waiter checking the order slip. If a customer orders a dish that doesn't exist, or leaves their table number blank, the waiter rejects it immediately before sending it to the kitchen. |

---

### 1. What is SQLAlchemy & a "Database Model"?
A **Database Model** is a Python class that matches a specific table inside your PostgreSQL database.
* **The Problem:** Databases don't understand Python. They speak a language called **SQL (Structured Query Language)**. To get a video, you would normally have to write: `SELECT * FROM videos WHERE id = 5;`.
* **The Solution (SQLAlchemy):** SQLAlchemy is an **ORM (Object-Relational Mapper)**. It acts as a translator. It lets you write Python code like:
  ```python
  video = db.query(VideoModel).filter(VideoModel.id == 5).first()
  ```
  SQLAlchemy automatically translates that line into raw SQL under the hood, runs it on the database, and returns the result as a friendly Python object!
* **A "Model"** (defined in `models.py`) is simply the blueprint of a database table. For example, `VideoModel` tells SQLAlchemy that the database has a table named `videos` with columns like `title` (text) and `user_id` (number).

---

### 2. What is Pydantic & a "Validation Schema"?
A **Schema** (defined in `schemas.py` using a library called **Pydantic**) defines what data must look like when it travels over the internet.
* **The Problem:** Anyone can send any data to your API endpoints. If someone tries to upload a video but sends their name instead of a number for `user_id`, the database will crash because it expects a number.
* **The Solution (Pydantic):** Pydantic is a library that checks incoming requests (JSON payloads) before they do anything else.
* **A "Schema"** is like a form check. When a client submits the upload form, Pydantic inspects it:
  - Is `title` a string?
  - Is `user_id` a number?
  - Did they include all required fields?
  If anything is wrong, Pydantic rejects the request immediately with a clear error message (e.g. `user_id: Input should be a valid integer`), protecting the server from crashes.

---

### Key Difference: Models vs. Schemas
It is common to confuse these two. Remember:
* **Models (`models.py`)** define how data is stored **inside the database**.
* **Schemas (`schemas.py`)** define how data looks when it is **received from the client** (incoming request) or **sent back to the client** (outgoing response).

---

## Why Models & Schemas Exist (And What Happens Without Them)

In Python web applications, **Database Models** (SQLAlchemy) and **Validation Schemas** (Pydantic) serve as the structural pillars. 

### 1. The Role of Database Models (`models.py`)
* **What it is:** Python code representations of database tables.
* **Why it is needed:** Writing raw SQL queries (like `SELECT * FROM videos;`) is error-prone, hard to maintain, and does not provide object-oriented mapping. Models allow Python code to speak to the database using Python objects (ORM - Object Relational Mapping).
* **What happens if they are not there:**
  * **SQL Injection Vulnerabilities:** If you insert values into query strings manually, attackers can manipulate query parameters to delete or steal your data.
  * **Manual Table Syncing:** If you change a column type, you have to write manual raw DDL scripts and execute them on the database manually instead of having ORM sync the database automatically on startup.
  * **No IDE Autocomplete:** Without models, your code editor doesn't know that a video has a `title` or `thumbnail_url` attribute, leading to typos and development bugs.
* **Alternate Ways:** 
  * **Raw SQL Queries:** Execute raw SQL strings manually via python drivers like `psycopg2` or `asyncpg`. This requires writing hundreds of lines of SQL queries and manual mapping scripts, increasing security risks.
  * **NoSQL Database (e.g. MongoDB):** Use a document database where there are no strict tables, and you store data as JSON. While highly flexible, NoSQL lacks strong relational integrity, which makes querying complex relationships (like many-to-many associations between playlists and videos) slower and harder to implement.

### 2. The Role of Validation Schemas (`schemas.py`)
* **What it is:** Rules that validate, cast, and serialize input/output data (using Pydantic).
* **Why it is needed:** When a client sends a request payload to the API, we must verify that parameters are of the correct type (e.g., `user_id` is an `int`, not a string like `"hello"`) before it hits database logic.
* **What happens if they are not there:**
  * **Runtime Database Crashes:** If a user sends a string instead of an integer and the database expects an integer, the query will crash the server.
  * **Lack of Output Filtering (Security Risk):** Without schemas, returning a database model directly would leak private columns (such as database internal keys, passwords, or internal API tokens) to the frontend.
  * **No Automatic API Docs:** FastAPI uses Pydantic schemas to automatically compile Swagger interactive documentation (`/docs`). Without schemas, your endpoints have no parameter templates, and testing becomes difficult.
* **Alternate Ways:**
  * **Manual JSON Parsing:** Read the incoming request dictionary manually (e.g. `data = await request.json()`) and write custom `if/else` checks for every field:
    ```python
    if "user_id" not in data or not isinstance(data["user_id"], int):
        raise HTTPException(status_code=400, detail="Invalid user_id")
    ```
    This adds hundreds of lines of repetitive validation logic, making the code extremely bloated.

---

## 1. Database Schema & Data Models (`app/models.py`)

The database is built on PostgreSQL using SQLAlchemy ORM. It models two main entities—**Videos** and **Playlists**—connected via a many-to-many relationship.

### A. Many-to-Many Bridge Table (`playlist_video`)
* **What it is:** A database junction/bridge table (`playlist_video`) containing two foreign keys: `playlist_id` and `video_id`.
* **Why it is:** In an OTT platform, a single video can belong to multiple playlists (e.g., "Favorites", "Action Hits", "Recommended"), and a playlist contains multiple videos. A many-to-many relationship prevents redundant data storage.
* **How it is:**
  ```python
  playlist_video_association = Table(
      "playlist_video",
      Base.metadata,
      Column("playlist_id", Integer, ForeignKey("playlists.id", ondelete="CASCADE"), primary_key=True),
      Column("video_id", Integer, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
  )
  ```
  `ondelete="CASCADE"` ensures that if a playlist or a video is deleted, their association in this bridge table is automatically cleaned up, preventing orphan records.

### B. Video Model (`VideoModel`)
* **What it is:** The representation of the `videos` database table. It stores information about video files, metadata, and status.
* **Why it is:** To keep track of media metadata, transcoding status (transferred from Bunny CDN), and access URLs without querying Bunny Stream directly on every list request.
* **How it is:**
  ```python
  class VideoModel(Base):
      __tablename__ = "videos"
      id = Column(Integer, primary_key=True, index=True)
      user_id = Column(Integer, nullable=False, index=True)  # Enforces user isolation
      bunny_video_id = Column(String(255), unique=True, nullable=False) # Maps to Bunny Stream ID
      title = Column(String(255), nullable=False)
      description = Column(Text, nullable=True)
      category = Column(String(100), nullable=True)
      tags = Column(ARRAY(String), nullable=True)
      thumbnail_url = Column(String(512), nullable=True) # Current default cover
      alt_thumbnails = Column(ARRAY(String), nullable=True) # Pool of 3 uploaded thumbnails
      status = Column(SQLEnum(VideoStatus), default=VideoStatus.PENDING)
  ```

### C. Playlist Model (`PlaylistModel`)
* **What it is:** The representation of the `playlists` database table.
* **Why it is:** To allow group collection of videos under a playlist title and cover image.
* **How it is:**
  ```python
  class PlaylistModel(Base):
      __tablename__ = "playlists"
      id = Column(Integer, primary_key=True, index=True)
      name = Column(String(255), nullable=False)
      description = Column(Text, nullable=True)
      thumbnail_url = Column(String(512), nullable=True)
      user_id = Column(Integer, nullable=False, index=True)
      
      # Establishes the relationship linking videos to the playlist through the association table
      videos = relationship("VideoModel", secondary=playlist_video_association, backref="playlists")
  ```
  The `relationship` property uses `secondary=playlist_video_association` to load and serialize the list of videos belonging to a playlist automatically.

---

## 2. Data Validation & Schemas (`app/schemas.py`)

Pydantic schemas enforce type safety and control the shape of data flowing in (Requests) and out (Responses).

* **What it is:** A layer of classes defining fields, types, and default values.
* **Why it is:** 
  1. **Security:** Sanitizes input and prevents arbitrary user data injections.
  2. **Data Integrity:** Ensures all required fields are present in the request body.
  3. **Abstraction:** Filters sensitive data (e.g., internal tokens) so only public/safe fields are returned to the client.
* **How it is:**
  * **Ingress (Request Schemas):**
    - `VideoInitiateSchema`: Takes `user_id`, `title`, and a list of `thumbnail_names`. Used when starting a new upload.
    - `VideoUpdateSchema`: Defines fields that are allowed to be modified (all fields are `Optional`).
  * **Egress (Response Schemas):**
    - `VideoResponseSchema`: Defines the public fields returned to the frontend. Includes `alt_thumbnails` to support switching covers. Set to use `from_attributes = True` to convert SQLAlchemy database objects to JSON responses.

---

## 3. Core API Endpoints & Logic Flow (`app/main.py`)

The application exposes endpoints divided into two main categories: **Video Pipeline** and **Playlist Management**.

### A. Video Pipeline Endpoints

#### 1. Initiate Video Upload (`POST /api/v1/videos/initiate`)
* **What it is:** The entry point for adding a new video.
* **Why it is:** Instead of passing large video files through the FastAPI backend (which slows down server performance), we register metadata first, then generate secure upload tokens so the client browser can upload files directly to Bunny CDN.
* **How it is:**
  1. **Handshake with Bunny Stream:** Tells Bunny CDN to reserve a video slot and returns a unique `bunny_video_id` (guid).
  2. **Generate Storage Targets:** Creates 3 unique target file paths in Bunny Storage for the 3 thumbnails.
  3. **Create TUS Signature:** Generates a secure HMAC-SHA256 signature allowing TUS resumable uploads.
  4. **Save in DB:** Inserts a record in the database with status `PENDING`.
  5. **Return Upload Instructions:** Returns the TUS endpoint and Bunny Storage PUT URLs directly to the client browser.

#### 2. Get Video Playback (`GET /api/v1/videos/{video_id}/play`)
* **What it is:** Resolves the public streaming link for a specific video.
* **Why it is:** Hides the underlying CDN stream structure and constructs secure streaming URLs dynamically.
* **How it is:**
  It fetches the video from the DB, checks that its status is `ready`, and outputs:
  ```python
  return {
      "id": video.id,
      "title": video.title,
      "stream_url": f"https://vz-b9303f26-5b8.b-cdn.net/{video.bunny_video_id}/playlist.m3u8",
      "thumbnail_url": video.thumbnail_url
  }
  ```

#### 3. Update Video (`PATCH /api/v1/videos/{video_id}`)
* **What it is:** Updates metadata details (title, description, tags, active default thumbnail).
* **Why it is:** Allows updating metadata or changing which of the 3 uploaded thumbnails in `alt_thumbnails` is the main active `thumbnail_url`.
* **How it is:**
  Receives `VideoUpdateSchema`, loads the video record, merges fields dynamically, and commits changes to PostgreSQL.

#### 4. Delete Video (`DELETE /api/v1/videos/{video_id}`)
* **What it is:** Completely removes a video.
* **Why it is:** Avoids storage fees by cleaning up both database records and remote assets.
* **How it is:**
  1. Calls the Bunny Stream API to delete the video file from Bunny Stream transcoder.
  2. Calls the Bunny Storage API to delete the thumbnail images.
  3. Deletes the row from PostgreSQL.

#### 5. Webhook Receiver (`POST /api/v1/webhooks/bunny`)
* **What it is:** An endpoint called automatically by Bunny CDN once a video finished processing.
* **Why it is:** Transcoding takes time. This webhook lets Bunny notify our server asynchronously so we can update the video status from `processing` to `ready`.
* **How it is:**
  Listens for Bunny webhook requests, checks if the status is `3` (Ready) or `4` (Failed), and saves the status to the DB.

---

### B. Playlist Management Endpoints

* **What it is:** REST endpoints managing the lifecycle of playlists.
* **Why it is:** To group collections of videos together.
* **How it is:**
  - `POST /api/v1/playlists`: Creates a playlist, generates a thumbnail storage upload URL, and inserts links to `video_ids` into the many-to-many mapping table.
  - `GET /api/v1/playlists/{playlist_id}`: Retrieves a playlist with its nested list of video objects populated via SQLAlchemy relationship joins.
  - `PATCH /api/v1/playlists/{playlist_id}`: Modifies the playlist name, cover graphic, or updates/replaces the list of videos linked in the bridge table.
  - `DELETE /api/v1/playlists/{playlist_id}`: Removes the playlist container (linked videos are preserved).

---

## 4. Under the Hood: SQLAlchemy and Pydantic Methods Explained

Here is an explanation of the specific methods, attributes, and classes from SQLAlchemy and Pydantic that are used in this codebase and how they function behind the scenes.

### A. SQLAlchemy Methods (Database Operations)

#### 1. `Base.metadata.create_all(bind=engine)`
* **What it does:** Scans the codebase for any class inheriting from `Base` (like `VideoModel` or `PlaylistModel`) and runs SQL commands to automatically create these tables in PostgreSQL if they do not already exist.
* **Under the Hood:** Generates and executes a SQL query like:
  `CREATE TABLE IF NOT EXISTS videos (...);`

#### 2. `db.query(VideoModel)`
* **What it does:** Initializes a `SELECT` statement builder pointing to the `videos` table.
* **Under the Hood:** pre-populates a query parser mapping the columns of the `videos` table.

#### 3. `.filter(VideoModel.id == video_id)`
* **What it does:** Adds filtering constraints to the query.
* **Under the Hood:** Translates directly into the SQL `WHERE` clause:
  `WHERE videos.id = 5`

#### 4. `.first()`
* **What it does:** Executes the query and returns only the first result (or `None` if no match is found).
* **Under the Hood:** Appends a SQL `LIMIT 1` command to save database resources:
  `SELECT * FROM videos WHERE id = 5 LIMIT 1;`

#### 5. `.all()`
* **What it does:** Executes the query and returns all matching rows as a list of Python model objects.
* **Under the Hood:** Runs the query on PostgreSQL, fetches all rows, loops through them, converts each raw SQL row into a Python object instance, and returns them in a standard list.

#### 6. `db.add(db_video)`
* **What it does:** Puts a Python model object into the SQLAlchemy Session tracker, marking it as "staged" for database insertion or update.
* **Under the Hood:** Nothing is written to the database yet. It simply marks the object in memory as "dirty" or "pending insertion".

#### 7. `db.commit()`
* **What it does:** Ends the database transaction and writes all staged changes permanently to PostgreSQL.
* **Under the Hood:** Executes `INSERT INTO ...` or `UPDATE ...` queries followed by a `COMMIT` statement to tell PostgreSQL to persist the changes.

#### 8. `db.refresh(db_video)`
* **What it does:** Reloads the fields of a Python object with fresh data from the database.
* **Why we use it:** Columns like `id` (which are auto-incremented by PostgreSQL) or fields with database-level default values are empty on the Python side until a refresh retrieves them.
* **Under the Hood:** Re-runs a query matching the object's primary key to fetch the newly generated ID and properties.

---

### B. Pydantic Methods (Validation & Formatting Operations)

#### 1. `class Config: from_attributes = True` (ORM Mode)
* **What it does:** Allows Pydantic schemas to read and validate data directly from SQLAlchemy database model attributes (e.g. `video.title`) instead of just raw dictionaries (e.g. `video["title"]`).
* **Under the Hood:** Enables a getter bridge inside Pydantic. It allows FastAPI to return database models directly, and Pydantic will automatically extract the values, format them, and output clean JSON.

#### 2. `payload.model_dump(exclude_unset=True)`
* **What it does:** Converts the Pydantic object into a Python dictionary, but **only includes fields that were explicitly sent by the user in the HTTP request request body**.
* **Why we use it:** In a PATCH request, a user might only want to update the `title`. If we converted the schema directly, other optional fields (like `description`) would default to `None` and overwrite existing values in the database. `exclude_unset=True` ensures we only update what the user modified.
* **Under the Hood:** Filters the schema's dictionary keys by checking the list of parsed field names received in the raw HTTP request.
