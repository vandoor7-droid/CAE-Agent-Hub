from __future__ import annotations

import io
import unittest

from tools.protocol import ProtocolError, make_request, read_message, unwrap_response, write_message


class ProtocolTests(unittest.TestCase):
    def test_write_and_read_json_line(self):
        stream = io.StringIO()
        payload = make_request("ping", {"x": 1})

        write_message(stream, payload)
        stream.seek(0)

        self.assertEqual(read_message(stream), payload)

    def test_unwrap_rejects_mismatched_id(self):
        with self.assertRaisesRegex(ProtocolError, "mismatched response id"):
            unwrap_response({"id": "other", "ok": True, "result": {}}, "expected")

    def test_unwrap_raises_bridge_error_message(self):
        with self.assertRaisesRegex(RuntimeError, "failed"):
            unwrap_response({"id": "1", "ok": False, "error": {"message": "failed"}}, "1")


if __name__ == "__main__":
    unittest.main()
