"""T4 tests — ingest/sniff.py (RED first)."""
import unittest

from driphound.ingest.sniff import detect_encoding, detect_format


class TestFormat(unittest.TestCase):
    def test_ofx(self):
        self.assertEqual(detect_format(b"OFXHEADER:100\r\n<OFX><BANKMSGSRSV1>"), "ofx")
        self.assertEqual(detect_format(b"<?xml version='1.0'?>\n<OFX>"), "ofx")
        self.assertEqual(detect_format(b"\xef\xbb\xbf<OFX>"), "ofx")

    def test_json(self):
        self.assertEqual(detect_format(b'[{"date":"2025-01-01"}]'), "json")
        self.assertEqual(detect_format(b'  { "transactions": [] }'), "json")
        self.assertEqual(detect_format(b'{broken json'), "csv")  # unparseable -> csv fallback

    def test_csv(self):
        self.assertEqual(detect_format(b"Date,Amount\n01/01/2025,5.00\n"), "csv")
        self.assertEqual(detect_format(b""), "csv")


class TestEncoding(unittest.TestCase):
    def test_bom(self):
        codec, guessed = detect_encoding(b"\xef\xbb\xbfDate,Amount")
        self.assertEqual(codec, "utf-8-sig")
        self.assertFalse(guessed)

    def test_utf8(self):
        codec, guessed = detect_encoding("Café,€3".encode("utf-8"))
        self.assertEqual(codec, "utf-8")
        self.assertFalse(guessed)

    def test_latin1_fallback(self):
        codec, guessed = detect_encoding(b"Caf\xe9\n01/01/2025")
        self.assertIn(codec, ("cp1252", "latin-1"))
        self.assertTrue(guessed)

    def test_binary_garbage_does_not_crash(self):
        codec, guessed = detect_encoding(bytes(range(256)))
        self.assertTrue(codec)


if __name__ == "__main__":
    unittest.main()
