import os
import sys
import uuid
import time
import shutil
import asyncio
import threading
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Auto-detect FFmpeg binary path if not in standard PATH
FFMPEG_CANDIDATE = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
FFMPEG_BIN = None
if FFMPEG_CANDIDATE.exists():
    for match in FFMPEG_CANDIDATE.rglob("ffmpeg.exe"):
        FFMPEG_BIN = str(match.parent)
        break

if FFMPEG_BIN and FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

app = FastAPI(title="YouTube Downloader & Converter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for download jobs
# Structure: { job_id: { status, percent, speed, eta, filename, file_path, error, title, format, created_at } }
jobs: Dict[str, Dict[str, Any]] = {}

def cleanup_old_files():
    """Removes downloads older than 1 hour to preserve disk space."""
    now = time.time()
    for item in DOWNLOADS_DIR.glob("*"):
        try:
            if item.is_file() and (now - item.stat().st_mtime > 3600):
                item.unlink(missing_ok=True)
        except Exception:
            pass

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp3"  # 'mp3' or 'mp4'
    quality: Optional[str] = "192"  # '128', '192', '320' for mp3; 'best', '1080', '720' for mp4
    save_folder: Optional[str] = None

class OpenFolderRequest(BaseModel):
    path: str

def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def sanitize_youtube_url(url: str) -> str:
    """Removes playlist and radio parameters from single video links."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    try:
        parsed = urlparse(url)
        # Handle standard watch links
        if "youtube.com" in parsed.netloc and "/watch" in parsed.path:
            qs = parse_qs(parsed.query)
            if "v" in qs:
                new_query = urlencode({"v": qs["v"][0]})
                return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
        # Handle youtu.be short links
        elif "youtu.be" in parsed.netloc:
            # Drop query parameters like ?list=...
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    except Exception:
        pass
    return url

@app.get("/api/info")
def get_video_info(url: str = Query(..., description="YouTube video URL")):
    """Fetches video metadata (title, author, thumbnail, duration) without downloading."""
    clean_url = sanitize_youtube_url(url.strip())
    ydl_opts = {
        'skip_download': True,
        'extract_flat': False,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if not info:
                raise HTTPException(status_code=400, detail="Could not extract video details.")
            
            # If info is a playlist extract, get the first entry
            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            
            return {
                "id": info.get("id"),
                "title": info.get("title", "Untitled"),
                "channel": info.get("uploader", "Unknown Channel"),
                "duration": format_duration(info.get("duration")),
                "thumbnail": info.get("thumbnail"),
                "views": info.get("view_count", 0),
            }
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"YouTube Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch info: {str(e)}")

def run_download_job(job_id: str, url: str, target_format: str, quality: str, save_folder: Optional[str] = None):
    clean_url = sanitize_youtube_url(url.strip())
    job = jobs[job_id]

    # Determine target directory
    if save_folder and save_folder.strip():
        target_dir = Path(save_folder.strip())
        target_dir.mkdir(parents=True, exist_ok=True)
        is_custom_folder = True
    else:
        target_dir = DOWNLOADS_DIR
        is_custom_folder = False

    output_template = str(target_dir / f"{job_id}_%(title).100s.%(ext)s")

    def progress_hook(d):
        if job.get("cancelled", False):
            raise Exception("Download cancelled by user.")
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total * 100) if total > 0 else 0
            
            speed = d.get('speed', 0)
            speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "Calculating..."
            
            eta = d.get('eta', 0)
            eta_str = f"{eta}s" if eta else "..."

            job["status"] = "downloading"
            job["percent"] = round(percent, 1)
            job["speed"] = speed_str
            job["eta"] = eta_str
        elif d['status'] == 'finished':
            job["status"] = "converting"
            job["percent"] = 99.0

    ydl_opts: Dict[str, Any] = {
        'outtmpl': output_template,
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
    }
    if FFMPEG_BIN:
        ydl_opts['ffmpeg_location'] = FFMPEG_BIN

    if target_format == "mp3":
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality if quality in ['128', '192', '320'] else '192',
                },
                {'key': 'FFmpegMetadata'},
            ],
        })
    else:  # mp4
        # Select best video + audio and merge into mp4
        if quality == "720":
            fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        elif quality == "1080":
            fmt = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        ydl_opts.update({
            'format': fmt,
            'merge_output_format': 'mp4',
            'postprocessors': [{'key': 'FFmpegMetadata'}],
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(clean_url, download=True)
            job["title"] = meta.get("title", "download")

        # Find the produced file
        matching_files = list(target_dir.glob(f"{job_id}_*"))
        if not matching_files:
            job["status"] = "error"
            job["error"] = "Processed file could not be found."
            return

        raw_file = matching_files[0]
        # Clean visible filename without the job_id prefix
        clean_name = raw_file.name.replace(f"{job_id}_", "")
        final_file = target_dir / clean_name
        
        # Rename so the local file doesn't have the ugly job_id prefix
        try:
            if final_file.exists() and final_file != raw_file:
                final_file.unlink()
            raw_file.rename(final_file)
        except Exception:
            final_file = raw_file
        
        job["status"] = "ready"
        job["percent"] = 100.0
        job["file_path"] = str(final_file)
        job["filename"] = final_file.name
        job["saved_dir"] = str(target_dir)
        job["is_custom_folder"] = is_custom_folder

    except Exception as e:
        if job.get("cancelled", False):
            job["status"] = "cancelled"
            job["error"] = "Download cancelled by user."
        else:
            job["status"] = "error"
            job["error"] = str(e)
        
        # Cleanup any partial or downloaded files for this job
        for f in target_dir.glob(f"{job_id}_*"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

@app.post("/api/download")
def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Initiates a download job in the background and returns a job_id."""
    cleanup_old_files()
    job_id = str(uuid.uuid4())[:8]
    
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "cancelled": False,
        "percent": 0.0,
        "speed": "",
        "eta": "",
        "filename": None,
        "file_path": None,
        "saved_dir": None,
        "is_custom_folder": False,
        "error": None,
        "title": "",
        "format": req.format,
        "created_at": time.time(),
    }

    # Run download in a separate worker thread so progress updates don't block
    t = threading.Thread(
        target=run_download_job,
        args=(job_id, req.url.strip(), req.format.lower(), req.quality or "192", req.save_folder),
        daemon=True
    )
    t.start()

    return {"job_id": job_id}

    return {"job_id": job_id}

@app.post("/api/cancel/{job_id}")
def cancel_job(job_id: str):
    """Cancels an active download job and cleans up partial files."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    job["cancelled"] = True
    job["status"] = "cancelled"
    
    # Try removing partial files immediately
    for f in DOWNLOADS_DIR.glob(f"{job_id}_*"):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    return {"status": "cancelled", "job_id": job_id}

@app.get("/api/status/{job_id}")
def check_job_status(job_id: str):
    """Polls download and conversion progress."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/api/file/{job_id}")
def get_downloaded_file(job_id: str, background_tasks: BackgroundTasks):
    """Sends the converted file to the user's browser."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "ready" or not job["file_path"]:
        raise HTTPException(status_code=400, detail="File is not ready for download.")

    file_path = Path(job["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer exists on disk.")

    # Only schedule deletion if saved in temporary downloads folder (not custom user folder)
    if not job.get("is_custom_folder", False):
        def delete_file(path_str: str, j_id: str):
            try:
                time.sleep(10)  # Wait 10 seconds to allow the stream to finish transfer
                p = Path(path_str)
                if p.exists():
                    p.unlink()
                jobs.pop(j_id, None)
            except Exception:
                pass

        background_tasks.add_task(delete_file, str(file_path), job_id)

    media_type = "audio/mpeg" if job["format"] == "mp3" else "video/mp4"
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=job["filename"],
    )

@app.get("/api/default-paths")
def get_default_paths():
    """Returns common standard paths on the user's computer."""
    home = Path.home()
    return {
        "downloads": str(home / "Downloads"),
        "music": str(home / "Music"),
        "videos": str(home / "Videos"),
        "desktop": str(home / "Desktop"),
        "project": str(BASE_DIR / "downloads"),
        "is_local_desktop": sys.platform == "win32"
    }

@app.post("/api/browse-folder")
def browse_folder():
    """Opens the modern Windows File Explorer Folder Picker (IFileOpenDialog with FOS_PICKFOLDERS)."""
    if sys.platform != "win32":
        return {"folder": None, "message": "Only available in local Windows mode."}
    ps_file = BASE_DIR / "picker.ps1"
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-STA",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(ps_file),
                "-Title", "ជ្រើសរើស Folder សម្រាប់រក្សាទុក File (Select Folder)",
                "-InitialFolder", str(Path.home() / "Downloads")
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120
        )
        selected = proc.stdout.strip()
        if selected:
            return {"folder": selected}
        return {"folder": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dialog error: {str(e)}")

@app.post("/api/open-folder")
def open_folder(req: OpenFolderRequest):
    """Opens the directory in Windows File Explorer and selects the file."""
    if sys.platform != "win32":
        return {"status": "unsupported"}
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Path does not exist on disk.")
    try:
        if p.is_file():
            subprocess.Popen(f'explorer /select,"{str(p)}"')
        else:
            os.startfile(str(p))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static web UI files
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
