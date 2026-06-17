from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from string import punctuation
from threading import RLock
from typing import Any
from unicodedata import category, normalize
from uuid import uuid4


MAX_ATTEMPTS = 5
CLIP_STEPS = [2, 4, 7, 11, 16]

_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration_seconds(data: bytes) -> int:
    """Estimate MP3 duration from raw bytes using first valid frame header."""
    offset = 0
    if len(data) >= 10 and data[:3] == b"ID3":
        sz = (
            ((data[6] & 0x7F) << 21)
            | ((data[7] & 0x7F) << 14)
            | ((data[8] & 0x7F) << 7)
            | (data[9] & 0x7F)
        )
        offset = 10 + sz

    end = len(data)
    while offset < end - 4:
        if data[offset] == 0xFF and (data[offset + 1] & 0xE0) == 0xE0:
            b1, b2 = data[offset + 1], data[offset + 2]
            version = (b1 >> 3) & 3
            layer = (b1 >> 1) & 3
            br_idx = (b2 >> 4) & 0xF
            sr_idx = (b2 >> 2) & 3
            if layer == 1 and version in _SAMPLE_RATES and 0 < br_idx < 15:
                bitrate = (_BITRATES_V1_L3 if version == 3 else _BITRATES_V2_L3)[br_idx]
                sr_list = _SAMPLE_RATES[version]
                if sr_idx < len(sr_list) and bitrate > 0:
                    sample_rate = sr_list[sr_idx]
                    if sample_rate > 0:
                        audio_bytes = end - offset
                        return max(1, round(audio_bytes * 8 / (bitrate * 1000)))
        offset += 1
    return 180


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album_id: str
    album_title: str
    duration_seconds: int = 180
    audio_url: str | None = None

    def public(self, reveal: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "artist": self.artist,
            "album_id": self.album_id,
            "album_title": self.album_title,
            "duration_seconds": self.duration_seconds,
            "audio_url": self.audio_url,
        }
        if reveal:
            data["title"] = self.title
        return data

    def game_public(self, reveal: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "duration_seconds": self.duration_seconds,
            "audio_url": self.audio_url,
        }
        if reveal:
            data["title"] = self.title
        return data


@dataclass
class Album:
    id: str
    title: str
    artist: str
    year: str | None = None
    cover_tone: str = "orange"
    track_count: int = 0
    cover_image_url: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "year": self.year,
            "cover_tone": self.cover_tone,
            "track_count": self.track_count,
            "cover_image_url": self.cover_image_url,
        }


@dataclass
class Round:
    id: str
    track_id: str
    attempts_used: int = 0
    status: str = "playing"
    guesses: list[str] = field(default_factory=list)

    @property
    def attempts_left(self) -> int:
        return max(0, MAX_ATTEMPTS - self.attempts_used)

    @property
    def clip_seconds(self) -> int:
        index = min(self.attempts_used, len(CLIP_STEPS) - 1)
        return CLIP_STEPS[index]

    @property
    def hint_available(self) -> bool:
        return self.status == "playing" and self.attempts_used >= 3


class TrackFlashStore:
    def __init__(self, db_path: str | os.PathLike[str] = ":memory:", rng: Random | None = None):
        self.rng = rng or Random()
        self.db_path = str(db_path)
        self.lock = RLock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.ensure_schema()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def ensure_schema(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS albums (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    year TEXT,
                    cover_tone TEXT NOT NULL DEFAULT 'orange',
                    cover_image_url TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tracks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album_id TEXT NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
                    duration_seconds INTEGER NOT NULL DEFAULT 180,
                    audio_url TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS rounds (
                    id TEXT PRIMARY KEY,
                    track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                    attempts_used INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'playing',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS guesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id TEXT NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                    guess TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_tracks_album_id ON tracks(album_id);
                CREATE INDEX IF NOT EXISTS idx_guesses_round_id ON guesses(round_id);
                """
            )
        # Migration: add cover_image_url to existing databases
        with self.lock:
            try:
                self.conn.execute("SELECT cover_image_url FROM albums LIMIT 1")
            except sqlite3.OperationalError:
                self.conn.execute("ALTER TABLE albums ADD COLUMN cover_image_url TEXT")
                self.conn.commit()

    def seed_defaults(self) -> None:
        with self.lock:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM albums").fetchone()
        if row and row["count"] > 0:
            return

        self.create_album(
            {
                "title": "Neon Grammar",
                "artist": "Lia Voss",
                "year": "2026",
                "cover_tone": "orange",
                "tracks": [
                    {"title": "Signal Burn", "duration_seconds": 224},
                    {"title": "Chrome Weather", "duration_seconds": 243},
                    {"title": "Velvet Metro", "duration_seconds": 198},
                ],
            }
        )
        self.create_album(
            {
                "title": "Cold Signal",
                "artist": "North Arcade",
                "year": "2024",
                "cover_tone": "green",
                "tracks": [
                    {"title": "Glass Memory", "duration_seconds": 251},
                    {"title": "Metro Bloom", "duration_seconds": 217},
                    {"title": "Night Relay", "duration_seconds": 205},
                ],
            }
        )

    def clear_library(self) -> dict[str, int]:
        with self.lock, self.conn:
            album_count = self.conn.execute("SELECT COUNT(*) AS count FROM albums").fetchone()["count"]
            track_count = self.conn.execute("SELECT COUNT(*) AS count FROM tracks").fetchone()["count"]
            self.conn.execute("DELETE FROM albums")
        return {"albums_deleted": album_count, "tracks_deleted": track_count}

    def list_albums(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT a.id, a.title, a.artist, a.year, a.cover_tone, a.cover_image_url,
                       COUNT(t.id) AS track_count
                FROM albums a
                LEFT JOIN tracks t ON t.album_id = a.id
                GROUP BY a.id
                ORDER BY a.created_at, a.title
                """
            ).fetchall()
        return [album_from_row(row).public() for row in rows]

    def list_tracks(self, album_id: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            if album_id:
                self.get_album(album_id)
                rows = self.conn.execute(
                    """
                    SELECT t.id, t.title, t.artist, t.album_id, a.title AS album_title,
                           t.duration_seconds, t.audio_url
                    FROM tracks t
                    JOIN albums a ON a.id = t.album_id
                    WHERE t.album_id = ?
                    ORDER BY t.created_at, t.title
                    """,
                    (album_id,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT t.id, t.title, t.artist, t.album_id, a.title AS album_title,
                           t.duration_seconds, t.audio_url
                    FROM tracks t
                    JOIN albums a ON a.id = t.album_id
                    ORDER BY t.created_at, t.title
                    """
                ).fetchall()
        return [track_from_row(row).public() for row in rows]

    def create_album(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = required_str(payload, "title")
        artist = required_str(payload, "artist")
        tracks_payload = payload.get("tracks", [])
        if not isinstance(tracks_payload, list):
            raise DomainError("faixas deve ser uma lista")

        album = Album(
            id=new_id("alb"),
            title=title,
            artist=artist,
            year=optional_str(payload, "year"),
            cover_tone=optional_str(payload, "cover_tone") or "orange",
            cover_image_url=optional_str(payload, "cover_image_url"),
        )

        with self.lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO albums (id, title, artist, year, cover_tone, cover_image_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (album.id, album.title, album.artist, album.year, album.cover_tone, album.cover_image_url),
            )
            for track_payload in tracks_payload:
                if not isinstance(track_payload, dict):
                    raise DomainError("cada faixa deve ser um objeto")
                self.create_track_locked(album, track_payload)

        return {
            **self.get_album(album.id).public(),
            "tracks": self.list_tracks(album.id),
        }

    def delete_album(self, album_id: str) -> list[str]:
        with self.lock, self.conn:
            self.get_album(album_id)
            rows = self.conn.execute(
                "SELECT audio_url FROM tracks WHERE album_id = ?", (album_id,)
            ).fetchall()
            audio_urls = [row["audio_url"] for row in rows if row["audio_url"]]
            cover_row = self.conn.execute(
                "SELECT cover_image_url FROM albums WHERE id = ?", (album_id,)
            ).fetchone()
            if cover_row and cover_row["cover_image_url"]:
                audio_urls.append(cover_row["cover_image_url"])
            self.conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        return audio_urls

    def add_tracks_to_album(self, album_id: str, tracks_payload: list[dict[str, Any]]) -> dict[str, Any]:
        with self.lock, self.conn:
            album = self.get_album(album_id)
            for tp in tracks_payload:
                if not isinstance(tp, dict):
                    raise DomainError("cada faixa deve ser um objeto")
                self.create_track_locked(album, tp)
        return {
            **self.get_album(album_id).public(),
            "tracks": self.list_tracks(album_id),
        }

    def delete_track(self, track_id: str) -> str | None:
        with self.lock, self.conn:
            row = self.conn.execute(
                "SELECT audio_url FROM tracks WHERE id = ?", (track_id,)
            ).fetchone()
            if not row:
                raise DomainError("musica nao encontrada", 404)
            audio_url = row["audio_url"]
            self.conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        return audio_url

    def create_track(self, album_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock, self.conn:
            album = self.get_album(album_id)
            track = self.create_track_locked(album, payload)
        return track.public()

    def create_track_locked(self, album: Album, payload: dict[str, Any]) -> Track:
        title = required_str(payload, "title")
        duration_seconds = int(payload.get("duration_seconds") or 180)
        if duration_seconds < 1:
            raise DomainError("duration_seconds deve ser positivo")

        track = Track(
            id=new_id("trk"),
            title=title,
            artist=optional_str(payload, "artist") or album.artist,
            album_id=album.id,
            album_title=album.title,
            duration_seconds=duration_seconds,
            audio_url=optional_str(payload, "audio_url"),
        )
        self.conn.execute(
            """
            INSERT INTO tracks (id, title, artist, album_id, duration_seconds, audio_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (track.id, track.title, track.artist, track.album_id, track.duration_seconds, track.audio_url),
        )
        return track

    def start_round(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        album_id = optional_str(payload, "album_id")
        artist = optional_str(payload, "artist")

        with self.lock, self.conn:
            if album_id:
                self.get_album(album_id)

            candidates = self.select_tracks(album_id=album_id)
            if artist:
                wanted = fold_text(artist)
                candidates = [track for track in candidates if fold_text(track.artist) == wanted]
            if not candidates:
                raise DomainError("nenhuma musica disponivel para esta rodada", 404)

            track = self.rng.choice(candidates)
            round_state = Round(id=new_id("rnd"), track_id=track.id)
            self.conn.execute(
                "INSERT INTO rounds (id, track_id, attempts_used, status) VALUES (?, ?, ?, ?)",
                (round_state.id, round_state.track_id, round_state.attempts_used, round_state.status),
            )

        return self.round_public(round_state)

    def get_round(self, round_id: str) -> dict[str, Any]:
        return self.round_public(self.find_round(round_id))

    def submit_guess(self, round_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        guess = required_str(payload, "guess")

        with self.lock, self.conn:
            round_state = self.find_round(round_id)
            if round_state.status != "playing":
                raise DomainError("a rodada ja terminou")

            track = self.get_track(round_state.track_id)
            round_state.guesses.append(guess)
            self.conn.execute("INSERT INTO guesses (round_id, guess) VALUES (?, ?)", (round_state.id, guess))

            if is_correct_guess(guess, track.title):
                round_state.status = "won"
                self.update_round(round_state)
                return {
                    **self.round_public(round_state),
                    "correct": True,
                    "message": "Resposta correta",
                    "answer": track.game_public(reveal=True),
                }

            round_state.attempts_used += 1
            if round_state.attempts_used >= MAX_ATTEMPTS:
                round_state.status = "lost"
                self.update_round(round_state)
                return {
                    **self.round_public(round_state),
                    "correct": False,
                    "message": "Fim das tentativas",
                    "answer": track.game_public(reveal=True),
                }

            self.update_round(round_state)

        return {
            **self.round_public(round_state),
            "correct": False,
            "message": "Resposta incorreta",
        }

    def get_hint(self, round_id: str) -> dict[str, Any]:
        round_state = self.find_round(round_id)
        if not round_state.hint_available:
            raise DomainError("a dica libera depois de 3 erros", 403)
        track = self.get_track(round_state.track_id)
        return {
            "round_id": round_state.id,
            "hint": {
                "title_length": len(track.title.replace(" ", "")),
                "first_letter": track.title[:1].upper(),
                "word_count": len(track.title.split()),
                "duration_seconds": track.duration_seconds,
            },
        }

    def round_public(self, round_state: Round) -> dict[str, Any]:
        track = self.get_track(round_state.track_id)
        reveal = round_state.status in {"won", "lost"}
        if round_state.attempts_used == MAX_ATTEMPTS - 1:
            clip = max(round_state.clip_seconds, track.duration_seconds // 2)
        else:
            clip = round_state.clip_seconds
        return {
            "id": round_state.id,
            "status": round_state.status,
            "clip_seconds": clip,
            "attempts_used": round_state.attempts_used,
            "attempts_left": round_state.attempts_left,
            "max_attempts": MAX_ATTEMPTS,
            "hint_available": round_state.hint_available,
            "guesses": round_state.guesses,
            "track": track.game_public(reveal=reveal),
        }

    def get_album(self, album_id: str) -> Album:
        row = self.conn.execute(
            """
            SELECT a.id, a.title, a.artist, a.year, a.cover_tone, a.cover_image_url,
                   COUNT(t.id) AS track_count
            FROM albums a
            LEFT JOIN tracks t ON t.album_id = a.id
            WHERE a.id = ?
            GROUP BY a.id
            """,
            (album_id,),
        ).fetchone()
        if not row:
            raise DomainError("album nao encontrado", 404)
        return album_from_row(row)

    def get_track(self, track_id: str) -> Track:
        row = self.conn.execute(
            """
            SELECT t.id, t.title, t.artist, t.album_id, a.title AS album_title,
                   t.duration_seconds, t.audio_url
            FROM tracks t
            JOIN albums a ON a.id = t.album_id
            WHERE t.id = ?
            """,
            (track_id,),
        ).fetchone()
        if not row:
            raise DomainError("musica nao encontrada", 404)
        return track_from_row(row)

    def select_tracks(self, album_id: str | None = None) -> list[Track]:
        params: tuple[str, ...] = ()
        where = ""
        if album_id:
            where = "WHERE t.album_id = ?"
            params = (album_id,)
        rows = self.conn.execute(
            f"""
            SELECT t.id, t.title, t.artist, t.album_id, a.title AS album_title,
                   t.duration_seconds, t.audio_url
            FROM tracks t
            JOIN albums a ON a.id = t.album_id
            {where}
            ORDER BY t.created_at, t.title
            """,
            params,
        ).fetchall()
        return [track_from_row(row) for row in rows]

    def find_round(self, round_id: str) -> Round:
        row = self.conn.execute(
            "SELECT id, track_id, attempts_used, status FROM rounds WHERE id = ?",
            (round_id,),
        ).fetchone()
        if not row:
            raise DomainError("rodada nao encontrada", 404)
        guess_rows = self.conn.execute(
            "SELECT guess FROM guesses WHERE round_id = ? ORDER BY id",
            (round_id,),
        ).fetchall()
        return Round(
            id=row["id"],
            track_id=row["track_id"],
            attempts_used=row["attempts_used"],
            status=row["status"],
            guesses=[guess_row["guess"] for guess_row in guess_rows],
        )

    def update_round(self, round_state: Round) -> None:
        self.conn.execute(
            """
            UPDATE rounds
            SET attempts_used = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (round_state.attempts_used, round_state.status, round_state.id),
        )


def create_seed_store(
    db_path: str | os.PathLike[str] = ":memory:",
    rng: Random | None = None,
) -> TrackFlashStore:
    store = TrackFlashStore(db_path=db_path, rng=rng)
    store.seed_defaults()
    return store


def album_from_row(row: sqlite3.Row) -> Album:
    keys = row.keys()
    return Album(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        year=row["year"],
        cover_tone=row["cover_tone"],
        track_count=row["track_count"],
        cover_image_url=row["cover_image_url"] if "cover_image_url" in keys else None,
    )


def track_from_row(row: sqlite3.Row) -> Track:
    return Track(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album_id=row["album_id"],
        album_title=row["album_title"],
        duration_seconds=row["duration_seconds"],
        audio_url=row["audio_url"],
    )


def is_correct_guess(guess: str, answer: str) -> bool:
    return fold_text(guess) == fold_text(answer)


def fold_text(value: str) -> str:
    decomposed = normalize("NFD", value)
    no_marks = "".join(ch for ch in decomposed if category(ch) != "Mn")
    translation = str.maketrans({ch: " " for ch in punctuation})
    words = no_marks.translate(translation).casefold().split()
    return " ".join(words)


def required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{key} e obrigatorio")
    return value.strip()


def optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainError(f"{key} deve ser texto")
    value = value.strip()
    return value or None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
