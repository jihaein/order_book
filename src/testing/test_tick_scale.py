import unittest

from matching import TickScale


class TickScaleTests(unittest.TestCase):
    def setUp(self):
        self.scale = TickScale(size=0.05)

    def test_valid_price_stays_on_same_tick(self):
        self.assertEqual(self.scale.to_ticks(100.05), 2001)
        self.assertEqual(self.scale.floor_to_ticks(100.05), 2001)
        self.assertEqual(self.scale.ceil_to_ticks(100.05), 2001)
        self.assertEqual(self.scale.snap(100.05), 100.05)

    def test_off_tick_price_is_detected(self):
        self.assertFalse(self.scale.is_aligned(100.02))
        self.assertTrue(self.scale.is_aligned(100.05))

    def test_bid_and_ask_directional_rounding(self):
        self.assertEqual(
            self.scale.to_price(self.scale.floor_to_ticks(100.02)),
            100.00,
        )
        self.assertEqual(
            self.scale.to_price(self.scale.ceil_to_ticks(100.02)),
            100.05,
        )


if __name__ == "__main__":
    unittest.main()