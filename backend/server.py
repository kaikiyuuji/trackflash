from __future__ import annotations

import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from .domain import DomainError, TrackFlashStore, mp3_duration_seconds


HOST = os.getenv("TRACKFLASH_API_HOST", "127.0.0.1")
PORT = int(os.getenv("TRACKFLASH_API_PORT", "8000"))
DB_PATH = os.getenv(
    "TRACKFLASH_DB_PATH",
    str((os.path.dirname(__file__) + "/data/trackflash.sqlite3").replace("\\", "/")),
)
UPLOAD_DIR = Path(os.getenv("TRACKFLASH_UPLOAD_DIR", str(Path(__file__).parent / "uploads")))
ALLOWED_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}
STORE = TrackFlashStore(db_path=DB_PATH)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
_IMAGE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class TrackFlashHandler(BaseHTTPRequestHandler):
    server_version = "TrackFlashHTTP/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_POST(self) -> None:
        self.handle_request("POST")

    def do_DELETE(self) -> None:
        self.handle_request("DELETE")

    def handle_request(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            path = [part for part in parsed.path.split("/") if part]
            query = parse_qs(parsed.query)
            if method == "GET" and path[:1] == ["media"]:
                self.write_media(path)
                return
            body = self.read_body(method, path)
            result = self.route(method, path, query, body)
            self.write_json(result)
        except DomainError as exc:
            self.write_json({"error": str(exc)}, exc.status_code)
        except json.JSONDecodeError:
            self.write_json({"error": "JSON invalido"}, 400)
        except Exception as exc:  # pragma: no cover - final safety net for HTTP boundary
            self.write_json({"error": "erro interno do servidor", "detail": str(exc)}, 500)

    def route(
        self,
        method: str,
        path: list[str],
        query: dict[str, list[str]],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if method == "GET" and path == ["health"]:
            return {"status": "ok", "service": "trackflash-api"}

        if method == "GET" and path == ["albums"]:
            return {"albums": STORE.list_albums()}

        if method == "POST" and path == ["albums"]:
            return {"album": STORE.create_album(body)}

        if method == "POST" and path == ["albums", "upload"]:
            return {"album": create_album_from_upload(body)}

        if method == "DELETE" and path == ["library"]:
            deleted = STORE.clear_library()
            deleted["files_deleted"] = clear_uploaded_files()
            return {"deleted": deleted}

        if method == "DELETE" and len(path) == 2 and path[0] == "albums":
            audio_urls = STORE.delete_album(path[1])
            delete_media_files(audio_urls)
            return {"deleted": True}

        if method == "POST" and len(path) == 3 and path[0] == "albums" and path[2] == "tracks":
            return {"album": add_tracks_from_upload(path[1], body)}

        if method == "DELETE" and len(path) == 2 and path[0] == "tracks":
            audio_url = STORE.delete_track(path[1])
            if audio_url:
                delete_media_files([audio_url])
            return {"deleted": True}

        if method == "GET" and path == ["tracks"]:
            album_id = first_query_value(query, "album_id")
            return {"tracks": STORE.list_tracks(album_id)}

        if method == "POST" and path == ["rounds"]:
            return {"round": STORE.start_round(body)}

        if len(path) == 2 and path[0] == "rounds" and method == "GET":
            return {"round": STORE.get_round(path[1])}

        if len(path) == 3 and path[0] == "rounds" and path[2] == "guess" and method == "POST":
            return {"round": STORE.submit_guess(path[1], body)}

        if len(path) == 3 and path[0] == "rounds" and path[2] == "hint" and method == "GET":
            return STORE.get_hint(path[1])

        raise DomainError("rota nao encontrada", 404)

    def read_body(self, method: str, path: list[str]) -> dict[str, Any]:
        if method != "POST":
            return {}
        if path == ["albums", "upload"]:
            return self.read_multipart()
        if len(path) == 3 and path[0] == "albums" and path[2] == "tracks":
            return self.read_multipart()
        return self.read_json()

    def read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise DomainError("o JSON deve ser um objeto")
        return value

    def read_multipart(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        boundary = get_multipart_boundary(content_type)
        if not boundary:
            raise DomainError("boundary multipart/form-data obrigatorio")
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length == 0:
            raise DomainError("corpo multipart vazio")

        raw = self.rfile.read(content_length)
        fields: dict[str, str] = {}
        files: list[dict[str, Any]] = []
        delimiter = b"--" + boundary

        for part in raw.split(delimiter):
            part = part.strip(b"\r\n")
            if not part or part == b"--":
                continue
            if part.endswith(b"--"):
                part = part[:-2].strip(b"\r\n")
            header_block, separator, content = part.partition(b"\r\n\r\n")
            if not separator:
                continue

            headers = parse_part_headers(header_block)
            disposition = headers.get("content-disposition", "")
            params = parse_header_params(disposition)
            name = params.get("name")
            if not name:
                continue

            content = content.rstrip(b"\r\n")
            filename = params.get("filename")
            if filename:
                files.append(
                    {
                        "field": name,
                        "filename": filename,
                        "content_type": headers.get("content-type", "application/octet-stream"),
                        "data": content,
                    }
                )
            else:
                fields[name] = content.decode("utf-8").strip()

        return {"fields": fields, "files": files}

    def write_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def write_media(self, path: list[str]) -> None:
        if len(path) != 2:
            raise DomainError("midia nao encontrada", 404)
        filename = unquote(path[1])
        if re.fullmatch(r"[a-f0-9]{32}\.mp3", filename):
            content_type = "audio/mpeg"
        else:
            m = re.fullmatch(r"[a-f0-9]{32}\.([a-z]+)", filename)
            if not m or m.group(1) not in _IMAGE_EXTS:
                raise DomainError("midia nao encontrada", 404)
            content_type = _IMAGE_CONTENT_TYPES[m.group(1)]

        media_path = UPLOAD_DIR / filename
        if not media_path.exists() or not media_path.is_file():
            raise DomainError("midia nao encontrada", 404)

        data = media_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        self.send_header(
            "Access-Control-Allow-Origin",
            origin if origin in ALLOWED_ORIGINS else "http://127.0.0.1:5173",
        )
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def save_mp3_file(content: bytes, filename: str) -> tuple[Path, str, int]:
    stored_name = f"{uuid4().hex}.mp3"
    stored_path = UPLOAD_DIR / stored_name
    stored_path.write_bytes(content)
    duration = mp3_duration_seconds(content)
    return stored_path, stored_name, duration


def save_image_file(content: bytes, filename: str) -> tuple[Path, str]:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in _IMAGE_EXTS:
        raise DomainError("apenas imagens jpg, png ou webp sao aceitas para capa")
    stored_name = f"{uuid4().hex}.{ext}"
    stored_path = UPLOAD_DIR / stored_name
    stored_path.write_bytes(content)
    return stored_path, stored_name


def create_album_from_upload(body: dict[str, Any]) -> dict[str, Any]:
    fields = body.get("fields")
    files = body.get("files")
    if not isinstance(fields, dict) or not isinstance(files, list):
        raise DomainError("upload multipart invalido")

    uploaded_tracks: list[dict[str, Any]] = []
    saved_paths: list[Path] = []
    cover_image_url: str | None = None
    try:
        for file in files:
            if not isinstance(file, dict):
                continue
            field = file.get("field")
            filename = str(file.get("filename") or "")
            content = file.get("data")

            if field == "cover":
                if not isinstance(content, bytes) or not content:
                    continue
                stored_path, stored_name = save_image_file(content, filename)
                saved_paths.append(stored_path)
                cover_image_url = f"/media/{stored_name}"
                continue

            if field != "files":
                continue
            if not filename.lower().endswith(".mp3"):
                raise DomainError("apenas arquivos .mp3 sao aceitos")
            if not isinstance(content, bytes) or not content:
                raise DomainError("arquivo .mp3 vazio")

            stored_path, stored_name, duration = save_mp3_file(content, filename)
            saved_paths.append(stored_path)
            uploaded_tracks.append(
                {
                    "title": title_from_filename(filename),
                    "duration_seconds": duration,
                    "audio_url": f"/media/{stored_name}",
                }
            )

        if not uploaded_tracks:
            raise DomainError("envie pelo menos um arquivo .mp3")

        return STORE.create_album(
            {
                "title": fields.get("title"),
                "artist": fields.get("artist"),
                "year": fields.get("year"),
                "cover_tone": fields.get("cover_tone") or "orange",
                "cover_image_url": cover_image_url,
                "tracks": uploaded_tracks,
            }
        )
    except Exception:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise


def add_tracks_from_upload(album_id: str, body: dict[str, Any]) -> dict[str, Any]:
    files = body.get("files")
    if not isinstance(files, list):
        raise DomainError("upload multipart invalido")

    uploaded_tracks: list[dict[str, Any]] = []
    saved_paths: list[Path] = []
    try:
        for file in files:
            if not isinstance(file, dict):
                continue
            field = file.get("field")
            filename = str(file.get("filename") or "")
            content = file.get("data")
            if field != "files":
                continue
            if not filename.lower().endswith(".mp3"):
                raise DomainError("apenas arquivos .mp3 sao aceitos")
            if not isinstance(content, bytes) or not content:
                raise DomainError("arquivo .mp3 vazio")

            stored_path, stored_name, duration = save_mp3_file(content, filename)
            saved_paths.append(stored_path)
            uploaded_tracks.append(
                {
                    "title": title_from_filename(filename),
                    "duration_seconds": duration,
                    "audio_url": f"/media/{stored_name}",
                }
            )

        if not uploaded_tracks:
            raise DomainError("envie pelo menos um arquivo .mp3")

        return STORE.add_tracks_to_album(album_id, uploaded_tracks)
    except Exception:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise


def delete_media_files(media_urls: list[str]) -> int:
    count = 0
    for url in media_urls:
        filename = url.rsplit("/", 1)[-1] if "/" in url else url
        path = UPLOAD_DIR / filename
        if path.exists() and path.is_file():
            path.unlink(missing_ok=True)
            count += 1
    return count


def get_multipart_boundary(content_type: str) -> bytes | None:
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part.split("=", 1)[1].strip().strip('"')
            return boundary.encode("utf-8")
    return None


def parse_part_headers(header_block: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in header_block.decode("utf-8", errors="replace").split("\r\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def parse_header_params(value: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for index, part in enumerate(value.split(";")):
        part = part.strip()
        if index == 0:
            params[""] = part
            continue
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        params[key.strip().lower()] = raw.strip().strip('"')
    return params


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"[_-]+", " ", stem).strip()
    return cleaned or "Musica sem nome"


def clear_uploaded_files() -> int:
    count = 0
    for path in UPLOAD_DIR.glob("*"):
        if path.is_file():
            path.unlink(missing_ok=True)
            count += 1
    return count


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), TrackFlashHandler)
    print(f"API TrackFlash em http://{HOST}:{PORT}")
    print(f"Banco SQLite: {DB_PATH}")
    print(f"Diretorio de uploads: {UPLOAD_DIR}")
    print("Pressione Ctrl+C para parar.")
    server.serve_forever()


if __name__ == "__main__":
    run()
