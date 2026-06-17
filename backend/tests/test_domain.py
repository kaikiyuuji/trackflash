from random import Random
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase

from backend.domain import DomainError, TrackFlashStore, create_seed_store, fold_text, is_correct_guess


class TextMatchingTests(TestCase):
    def test_guess_matching_ignores_case_accents_and_punctuation(self) -> None:
        self.assertEqual(fold_text("Cancao, FINAL!"), "cancao final")
        self.assertTrue(is_correct_guess("signal-burn", "Signal Burn"))


class StoreTests(TestCase):
    def test_create_album_with_tracks(self) -> None:
        store = TrackFlashStore(rng=Random(1))
        album = store.create_album(
            {
                "title": "Test Album",
                "artist": "Test Artist",
                "tracks": [{"title": "First Track"}, {"title": "Second Track"}],
            }
        )

        self.assertEqual(album["track_count"], 2)
        self.assertEqual(len(store.list_tracks(album["id"])), 2)

    def test_round_hides_answer_until_finished(self) -> None:
        store = create_seed_store(rng=Random(1))
        round_data = store.start_round({})

        self.assertNotIn("title", round_data["track"])
        self.assertNotIn("artist", round_data["track"])
        self.assertNotIn("album_title", round_data["track"])
        self.assertNotIn("album_id", round_data["track"])

    def test_hint_unlocks_after_three_wrong_guesses(self) -> None:
        store = create_seed_store(rng=Random(1))
        round_id = store.start_round({})["id"]

        with self.assertRaises(DomainError):
            store.get_hint(round_id)

        for _ in range(3):
            store.submit_guess(round_id, {"guess": "wrong"})

        hint = store.get_hint(round_id)
        self.assertIn("first_letter", hint["hint"])

    def test_round_loses_after_five_wrong_guesses_and_reveals_answer(self) -> None:
        store = create_seed_store(rng=Random(1))
        round_id = store.start_round({})["id"]
        result = {}

        for _ in range(5):
            result = store.submit_guess(round_id, {"guess": "wrong"})

        self.assertEqual(result["status"], "lost")
        self.assertEqual(result["attempts_left"], 0)
        self.assertIn("title", result["track"])
        self.assertNotIn("artist", result["track"])
        self.assertNotIn("album_title", result["track"])

    def test_clear_library_removes_albums_tracks_rounds_and_guesses(self) -> None:
        store = create_seed_store(rng=Random(1))
        round_id = store.start_round({})["id"]
        store.submit_guess(round_id, {"guess": "wrong"})
        deleted = store.clear_library()

        self.assertEqual(deleted["albums_deleted"], 2)
        self.assertEqual(deleted["tracks_deleted"], 6)
        self.assertEqual(store.list_albums(), [])
        self.assertEqual(store.list_tracks(), [])
        with self.assertRaises(DomainError):
            store.get_round(round_id)

    def test_albums_tracks_and_rounds_persist_in_sqlite_file(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "trackflash.sqlite3"
            first_store = TrackFlashStore(db_path=db_path, rng=Random(1))
            album = first_store.create_album(
                {
                    "title": "Persistent Album",
                    "artist": "Persistent Artist",
                    "tracks": [{"title": "Persistent Track"}],
                }
            )
            round_data = first_store.start_round({"album_id": album["id"]})
            first_store.submit_guess(round_data["id"], {"guess": "wrong"})
            first_store.close()

            second_store = TrackFlashStore(db_path=db_path, rng=Random(1))
            self.assertEqual(second_store.list_albums()[0]["title"], "Persistent Album")
            self.assertEqual(second_store.list_tracks(album["id"])[0]["title"], "Persistent Track")
            restored_round = second_store.get_round(round_data["id"])
            self.assertEqual(restored_round["guesses"], ["wrong"])
            self.assertEqual(restored_round["attempts_used"], 1)
            second_store.close()
