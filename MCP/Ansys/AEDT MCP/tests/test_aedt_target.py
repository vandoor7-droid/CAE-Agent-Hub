from dataclasses import FrozenInstanceError
import unittest

from aedt_target import AedtTarget, TargetValidationError


class AedtTargetTests(unittest.TestCase):
    def test_from_values_normalizes_pid(self):
        target = AedtTarget.from_values(pid=1234, port=None)

        self.assertEqual(target, AedtTarget(kind="pid", value=1234))
        self.assertEqual(target.key, "pid:1234")

    def test_from_values_normalizes_port(self):
        target = AedtTarget.from_values(pid=None, port=50051)

        self.assertEqual(target, AedtTarget(kind="port", value=50051))
        self.assertEqual(target.key, "port:50051")

    def test_from_values_rejects_missing_target(self):
        with self.assertRaises(TargetValidationError):
            AedtTarget.from_values(pid=None, port=None)

    def test_from_values_rejects_multiple_targets(self):
        with self.assertRaises(TargetValidationError):
            AedtTarget.from_values(pid=1234, port=50051)

    def test_from_values_rejects_zero_and_negative_values(self):
        for field, value in (("pid", 0), ("pid", -1), ("port", 0), ("port", -1)):
            with self.subTest(field=field, value=value):
                arguments = {"pid": None, "port": None, field: value}
                with self.assertRaises(TargetValidationError):
                    AedtTarget.from_values(**arguments)

    def test_from_values_rejects_booleans(self):
        for field in ("pid", "port"):
            with self.subTest(field=field):
                arguments = {"pid": None, "port": None, field: True}
                with self.assertRaises(TargetValidationError):
                    AedtTarget.from_values(**arguments)

    def test_from_values_rejects_non_integer_values(self):
        for field, value in (("pid", 1.0), ("pid", "1"), ("port", 1.0), ("port", "1")):
            with self.subTest(field=field, value=value):
                arguments = {"pid": None, "port": None, field: value}
                with self.assertRaises(TargetValidationError):
                    AedtTarget.from_values(**arguments)

    def test_from_values_rejects_port_above_maximum(self):
        with self.assertRaises(TargetValidationError):
            AedtTarget.from_values(pid=None, port=65536)

    def test_direct_construction_rejects_unsupported_kind(self):
        with self.assertRaises(TargetValidationError):
            AedtTarget(kind="process", value=1234)

    def test_target_is_immutable(self):
        target = AedtTarget(kind="pid", value=1234)

        with self.assertRaises(FrozenInstanceError):
            target.value = 5678


if __name__ == "__main__":
    unittest.main()
