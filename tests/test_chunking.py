from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator.chunking import split_text_into_chunks  # noqa: E402


def test_short_text_returns_single_chunk() -> None:
    text = "Hola mundo. Esto es una prueba corta."
    assert split_text_into_chunks(text, max_chars=300) == [text]


def test_prefers_sentence_ending_near_limit() -> None:
    s1 = "Primera frase corta de prueba para comprobar el corte natural."
    s2 = "Segunda frase también de tamaño moderado que termina justo antes del límite."
    s3 = "Tercera frase que debe ir en la siguiente sección porque ya pasamos el límite."
    text = f"{s1} {s2} {s3}"
    chunks = split_text_into_chunks(text, max_chars=150)
    assert len(chunks) == 2
    assert chunks[0] == f"{s1} {s2}"
    assert chunks[1] == s3


def test_does_not_stretch_past_window_when_period_is_too_far() -> None:
    words = ["palabra"] * 80
    long_sentence = " ".join(words) + "."
    chunks = split_text_into_chunks(long_sentence, max_chars=180)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 185
        for token in c.rstrip(".").split():
            assert token == "palabra"


def test_never_cuts_inside_a_word() -> None:
    text = " ".join(f"token{i}" for i in range(60))
    chunks = split_text_into_chunks(text, max_chars=120)
    rejoined = " ".join(chunks)
    assert rejoined == text


def test_respects_paragraph_breaks() -> None:
    text = "Párrafo uno.\n\nPárrafo dos."
    assert split_text_into_chunks(text, max_chars=300) == ["Párrafo uno.", "Párrafo dos."]
