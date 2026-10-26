import unittest

from aedt_close_watcher import AedtCloseWatcher, WindowState


class AedtCloseWatcherTests(unittest.TestCase):
    def test_visible_to_hidden_transition_triggers_close_once(self):
        states = iter(
            [
                WindowState(False, False),
                WindowState(True, False),
                WindowState(True, False),
                WindowState(False, False),
                WindowState(False, False),
            ]
        )
        reasons = []
        watcher = AedtCloseWatcher(
            session_pid=lambda: 4321,
            window_state=lambda pid: next(states),
            on_close_intent=reasons.append,
        )

        for _ in range(5):
            watcher.poll_once()

        self.assertEqual(reasons, ["main_window_closed"])

    def test_busy_dialog_triggers_close_without_waiting_for_hidden_window(self):
        reasons = []
        watcher = AedtCloseWatcher(
            session_pid=lambda: 4321,
            window_state=lambda pid: WindowState(True, True),
            on_close_intent=reasons.append,
        )

        watcher.poll_once()
        watcher.poll_once()

        self.assertEqual(reasons, ["busy_dialog"])

    def test_missing_session_resets_visible_state(self):
        pids = iter([4321, None, 4321])
        states = iter([WindowState(True, False), WindowState(False, False)])
        reasons = []
        watcher = AedtCloseWatcher(
            session_pid=lambda: next(pids),
            window_state=lambda pid: next(states),
            on_close_intent=reasons.append,
        )

        watcher.poll_once()
        watcher.poll_once()
        watcher.poll_once()

        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
