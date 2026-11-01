import unittest
from core import Candidate, choose, all_timeout, next_due


def node(status, selected=False, reliable=True, x=0):
    return Candidate("新加坡", status, (x,0,400,70), selected, reliable)


class Rules(unittest.TestCase):
    def test_lowest(self):
        best = node("232")
        self.assertIs(choose([node("Timeout"),node("233"),best,node("646"),node("Error")]),best)

    def test_tie_keeps_current(self):
        current = node("232",True,x=400)
        self.assertIs(choose([node("232"),current]),current)

    def test_reject_uncertain(self):
        self.assertIsNone(choose([node("1",reliable=False),node("Check"),node("0")]))
        self.assertIsNone(choose([node("232",reliable=False),node("646")]))

    def test_all_timeout(self):
        self.assertTrue(all_timeout([node("Timeout"),node("Timeout")]))
        for other in ["Error","Check","","232"]:
            self.assertFalse(all_timeout([node("Timeout"),node(other)]))
        self.assertFalse(all_timeout([]))
        self.assertFalse(all_timeout([node("Timeout",reliable=False)]))
        self.assertFalse(all_timeout([node("Timeout")],complete=False))

    def test_schedule_and_immediate_retry(self):
        self.assertEqual(next_due(100,110,60),160)
        self.assertEqual(next_due(100,110,60,True),110)
        self.assertEqual(next_due(110,120,60,True),120)
        self.assertEqual(next_due(120,130,60),180)
        self.assertEqual(next_due(100,230,60),280)


if __name__ == "__main__":
    unittest.main()
