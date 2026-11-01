"""Guard coverage with mocked Win32 calls; no real desktop input."""
import threading
import unittest
from unittest.mock import patch
import windows


class ClickGuards(unittest.TestCase):
    def test_stop_prevents_input(self):
        stop=threading.Event()
        stop.set()
        with patch("windows.user") as user:
            with self.assertRaises(InterruptedError):
                windows.click(1,(0,0,100,100),(20,20),stop)
            user.mouse_event.assert_not_called()

    def test_move_and_foreground_change_prevent_input(self):
        stop=threading.Event()
        for current, foreground in [((1,0,101,100),1),((0,0,100,100),2)]:
            with patch("windows.rect",return_value=current),patch("windows.user") as user:
                user.GetForegroundWindow.return_value=foreground
                with self.assertRaises(RuntimeError):
                    windows.click(1,(0,0,100,100),(20,20),stop)
                user.mouse_event.assert_not_called()

    def test_obstruction_prevents_input(self):
        with patch("windows.rect",return_value=(0,0,100,100)),patch("windows.user") as user:
            user.GetForegroundWindow.return_value=1
            user.GetAncestor.return_value=2
            with self.assertRaises(RuntimeError):
                windows.click(1,(0,0,100,100),(20,20),threading.Event())
            user.mouse_event.assert_not_called()


if __name__ == "__main__":
    unittest.main()
