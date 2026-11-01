"""Exercise actual worker flow with a fake desktop; never send mouse input."""
import queue
import threading
import unittest
from unittest.mock import patch
from app import App
from core import Candidate


class FakeVision:
    def __init__(self, batches):
        self.batches = iter(batches)
    def scan(self, rgb, keyword):
        return next(self.batches), True, []
    def button(self, rgb, texts):
        return (100,100)


def candidates(status):
    return [Candidate("新加坡-直连",status,(200,300,400,70),True)]


class WorkerTests(unittest.TestCase):
    def make_app(self, batches):
        app = App.__new__(App)
        app.engine = FakeVision(batches)
        app.stop = threading.Event()
        app.now = threading.Event()
        app.lock = threading.Lock()
        app.events = queue.Queue()
        app.config = {"interval":60,"wait":10,"keyword":"新加坡"}
        app.messages = []
        app.log = app.messages.append
        app.waits = []
        app.pause = lambda seconds,label: app.waits.append(seconds)
        return app

    def run_worker(self, app, click):
        with patch("app.windows.activate"), patch("app.windows.capture",return_value=(None,(0,0,1000,1000))), patch("app.windows.click",side_effect=click):
            app.run(1,"once")

    def test_repeated_timeouts_then_success(self):
        # Each round scans before the click and once more after the wait.
        app = self.make_app([candidates(s) for s in ["","Timeout","Timeout","Timeout","Timeout","232"]])
        clicks = []
        self.run_worker(app,lambda *args: clicks.append(args))
        self.assertEqual(len(clicks),3)
        self.assertEqual(app.waits,[10,10,10])
        self.assertTrue(any("连续重试 2 次" in m for m in app.messages))
        self.assertIn("232 ms",app.messages[-1])

    def test_error_does_not_immediately_retry(self):
        app = self.make_app([candidates(""),candidates("Error")])
        clicks=[]
        self.run_worker(app,lambda *args: clicks.append(args))
        self.assertEqual(len(clicks),1)

    def test_missing_node_does_not_trigger_timeout_retry(self):
        before=candidates("")+[Candidate("新加坡-中转","",(610,300,400,70))]
        app=self.make_app([before,candidates("Timeout")])
        clicks=[]
        self.run_worker(app,lambda *args: clicks.append(args))
        self.assertEqual(len(clicks),1)

    def test_stop_while_waiting(self):
        app = self.make_app([candidates("")])
        def pause(*args):
            app.stop.set()
            raise InterruptedError()
        app.pause = pause
        clicks=[]
        self.run_worker(app,lambda *args: clicks.append(args))
        self.assertEqual(len(clicks),1)
        self.assertTrue(any("已停止" in m for m in app.messages))

    def test_closed_window_is_skipped(self):
        app = self.make_app([])
        with patch("app.windows.activate",side_effect=RuntimeError("目标窗口不存在")), patch("app.windows.click") as clicks:
            app.run(1,"once")
        clicks.assert_not_called()
        self.assertTrue(any("目标窗口不存在" in m for m in app.messages))

    def test_selection_confirmation_failure_does_not_click_again(self):
        target = candidates("232")
        target[0].selected=False
        app=self.make_app([candidates(""),target,target])
        clicks=[]
        self.run_worker(app,lambda *args: clicks.append(args))
        self.assertEqual(len(clicks),2)  # Exactly one speed click and one node click.
        self.assertTrue(any("未确认选中样式" in m for m in app.messages))


if __name__ == "__main__":
    unittest.main()
