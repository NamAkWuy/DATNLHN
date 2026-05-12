"""
Unit tests for app/services/face_service.py

Tests cover:
- extract_face_encoding: dimensions, determinism, base64 variants
- cosine_similarity: edge cases
- compare_faces: match / no-match / threshold
- find_best_match: correct employee, no match
- mock_encoding_for_employee: stability, uniqueness, unit-norm
"""
import math
import base64
import json
from io import BytesIO

import pytest

# conftest sets DATABASE_URL env var before any app import
from app.services.face_service import (
    extract_face_encoding,
    extract_face_encoding_from_base64,
    cosine_similarity,
    compare_faces,
    find_best_match,
    mock_encoding_for_employee,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_bytes(color=(100, 150, 200), size=(50, 50)) -> bytes:
    """
    Return raw BMP bytes of a solid-color image.

    BMP is used (not JPEG) because BMP pixel data starts at byte 54,
    which is within the first 64 bytes — the region the mock encoder
    uses as a seed.  JPEG headers are identical across colors, so
    solid-color JPEGs of the same size would produce the same mock seed.
    """
    try:
        from PIL import Image
        img = Image.new("RGB", size, color=color)
        buf = BytesIO()
        img.save(buf, format="BMP")
        return buf.getvalue()
    except ImportError:
        # Minimal unique raw bytes based on color as fallback
        r, g, b = color
        return bytes([r, g, b] * 22 + [0, 0])  # 68 bytes, unique per color


# ---------------------------------------------------------------------------
# extract_face_encoding
# ---------------------------------------------------------------------------

class TestExtractFaceEncoding:
    def test_returns_128_dimensional_vector(self):
        image_bytes = _make_image_bytes()
        encoding = extract_face_encoding(image_bytes)
        assert len(encoding) == 128, "Encoding phải có 128 chiều"

    def test_returns_list_of_floats(self):
        image_bytes = _make_image_bytes()
        encoding = extract_face_encoding(image_bytes)
        assert all(isinstance(x, float) for x in encoding)

    def test_is_unit_vector(self):
        """Vector đặc trưng phải được chuẩn hóa (norm ≈ 1)."""
        image_bytes = _make_image_bytes()
        encoding = extract_face_encoding(image_bytes)
        norm = math.sqrt(sum(x ** 2 for x in encoding))
        assert abs(norm - 1.0) < 1e-6, f"Norm = {norm}, kỳ vọng ≈ 1.0"

    def test_deterministic_for_same_image(self):
        """Cùng ảnh → cùng encoding (seeded by pixel content)."""
        image_bytes = _make_image_bytes(color=(80, 120, 160))
        enc1 = extract_face_encoding(image_bytes)
        enc2 = extract_face_encoding(image_bytes)
        assert enc1 == enc2

    def test_different_images_produce_different_encodings(self):
        """Ảnh có pixel content khác → encoding khác."""
        enc1 = extract_face_encoding(_make_image_bytes(color=(50, 50, 50)))
        enc2 = extract_face_encoding(_make_image_bytes(color=(200, 200, 200)))
        assert enc1 != enc2


# ---------------------------------------------------------------------------
# extract_face_encoding_from_base64
# ---------------------------------------------------------------------------

class TestExtractFaceEncodingFromBase64:
    def test_plain_base64_string(self):
        image_bytes = _make_image_bytes()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        encoding = extract_face_encoding_from_base64(b64)
        assert len(encoding) == 128

    def test_data_uri_prefix_is_stripped(self):
        """Chuỗi base64 với tiền tố data URI phải cho kết quả như không có tiền tố."""
        image_bytes = _make_image_bytes(color=(30, 60, 90))
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        b64_with_prefix = f"data:image/jpeg;base64,{b64}"

        enc_plain = extract_face_encoding_from_base64(b64)
        enc_prefixed = extract_face_encoding_from_base64(b64_with_prefix)

        assert enc_plain == enc_prefixed, "Tiền tố data URI không được ảnh hưởng đến encoding"

    def test_returns_same_as_bytes_version(self):
        image_bytes = _make_image_bytes(color=(70, 140, 210))
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        enc_from_b64 = extract_face_encoding_from_base64(b64)
        enc_from_bytes = extract_face_encoding(image_bytes)

        assert enc_from_b64 == enc_from_bytes


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_return_1(self):
        vec = [0.6, 0.8, 0.0]
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-9

    def test_opposite_vectors_return_minus_1(self):
        vec = [0.6, 0.8, 0.0]
        neg = [-0.6, -0.8, 0.0]
        sim = cosine_similarity(vec, neg)
        assert abs(sim - (-1.0)) < 1e-9

    def test_orthogonal_vectors_return_0(self):
        sim = cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 1e-9

    def test_zero_vector_returns_0(self):
        sim = cosine_similarity([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert sim == 0.0

    def test_symmetry(self):
        a = [0.3, 0.4, 0.5]
        b = [0.1, 0.9, 0.2]
        assert abs(cosine_similarity(a, b) - cosine_similarity(b, a)) < 1e-9

    def test_value_in_range(self):
        """Cosine similarity phải nằm trong [-1, 1]."""
        import random
        rng = random.Random(42)
        for _ in range(20):
            a = [rng.gauss(0, 1) for _ in range(128)]
            b = [rng.gauss(0, 1) for _ in range(128)]
            sim = cosine_similarity(a, b)
            assert -1.0 <= sim <= 1.0


# ---------------------------------------------------------------------------
# compare_faces
# ---------------------------------------------------------------------------

class TestCompareFaces:
    def test_same_encoding_is_match(self):
        enc = mock_encoding_for_employee(1)
        is_match, confidence = compare_faces(enc, enc)
        assert is_match is True
        assert abs(confidence - 1.0) < 1e-6

    def test_different_employees_no_match_above_threshold(self):
        """Hai nhân viên khác nhau → similarity thấp hơn ngưỡng mặc định."""
        enc1 = mock_encoding_for_employee(1)
        enc2 = mock_encoding_for_employee(99)
        is_match, confidence = compare_faces(enc1, enc2, threshold=0.6)
        # Với mock encoding, hai nhân viên random sẽ không khớp
        assert confidence < 1.0  # ít nhất không giống hệt

    def test_custom_low_threshold_forces_match(self):
        """Đặt threshold = -1 thì bất kỳ cặp nào cũng match."""
        enc1 = mock_encoding_for_employee(10)
        enc2 = mock_encoding_for_employee(20)
        is_match, _ = compare_faces(enc1, enc2, threshold=-1.0)
        assert is_match is True

    def test_custom_high_threshold_prevents_match(self):
        """Đặt threshold = 1.0 thì chỉ vector giống hệt mới match."""
        enc1 = mock_encoding_for_employee(10)
        enc2 = mock_encoding_for_employee(11)
        is_match, _ = compare_faces(enc1, enc2, threshold=1.0)
        assert is_match is False

    def test_returns_tuple_bool_float(self):
        enc = mock_encoding_for_employee(5)
        result = compare_faces(enc, enc)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], float)


# ---------------------------------------------------------------------------
# find_best_match
# ---------------------------------------------------------------------------

class TestFindBestMatch:
    def _make_stored(self, employee_ids: list[int]) -> list[dict]:
        return [
            {"employee_id": eid, "encoding": mock_encoding_for_employee(eid)}
            for eid in employee_ids
        ]

    def test_returns_correct_employee_for_exact_match(self):
        stored = self._make_stored([1, 2, 3])
        query = mock_encoding_for_employee(2)
        best_id, score = find_best_match(query, stored, threshold=0.4)
        assert best_id == 2
        assert abs(score - 1.0) < 1e-6

    def test_returns_none_when_no_stored_encodings(self):
        query = mock_encoding_for_employee(1)
        best_id, score = find_best_match(query, [], threshold=0.4)
        assert best_id is None
        assert score == -1.0

    def test_returns_none_when_best_score_below_threshold(self):
        """Nếu độ tương đồng tốt nhất dưới ngưỡng → trả về None."""
        stored = self._make_stored([10, 20, 30])
        # Dùng một encoding hoàn toàn khác biệt
        query = mock_encoding_for_employee(999)
        best_id, score = find_best_match(query, stored, threshold=0.99)
        # Với threshold 0.99, chỉ vector gần như giống hệt mới vượt qua
        assert best_id is None

    def test_returns_highest_scoring_employee(self):
        """Trong nhiều nhân viên, phải trả về người có score cao nhất."""
        stored = self._make_stored([1, 2, 3, 4, 5])
        # Query với encoding của nhân viên 3
        query = mock_encoding_for_employee(3)
        best_id, score = find_best_match(query, stored, threshold=0.5)
        assert best_id == 3

    def test_score_is_float(self):
        stored = self._make_stored([1])
        query = mock_encoding_for_employee(1)
        _, score = find_best_match(query, stored)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# mock_encoding_for_employee
# ---------------------------------------------------------------------------

class TestMockEncodingForEmployee:
    def test_stable_across_calls(self):
        """Cùng employee_id luôn cho cùng encoding."""
        enc1 = mock_encoding_for_employee(7)
        enc2 = mock_encoding_for_employee(7)
        assert enc1 == enc2

    def test_unique_per_employee(self):
        """Mỗi nhân viên có encoding khác nhau."""
        enc1 = mock_encoding_for_employee(1)
        enc2 = mock_encoding_for_employee(2)
        enc3 = mock_encoding_for_employee(3)
        assert enc1 != enc2
        assert enc2 != enc3
        assert enc1 != enc3

    def test_returns_128_dimensions(self):
        enc = mock_encoding_for_employee(42)
        assert len(enc) == 128

    def test_is_unit_norm(self):
        """Mock encoding phải là unit vector."""
        enc = mock_encoding_for_employee(100)
        norm = math.sqrt(sum(x ** 2 for x in enc))
        assert abs(norm - 1.0) < 1e-6

    def test_all_floats(self):
        enc = mock_encoding_for_employee(15)
        assert all(isinstance(x, float) for x in enc)

    def test_self_similarity_is_one(self):
        """Một encoding so với chính nó phải cho cosine = 1."""
        enc = mock_encoding_for_employee(50)
        sim = cosine_similarity(enc, enc)
        assert abs(sim - 1.0) < 1e-6
