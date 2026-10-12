# SPDX-License-Identifier: GPL-3.0-or-later
"""Position must track where the handle is *now*, on either monitor."""
import unittest
from betternotes.x11_position import restore_position, looks_wm_centered


class RestorePositionTests(unittest.TestCase):
    monitors = [(0, 0, 1080, 1920), (1080, 0, 2560, 1440)]

    def test_left_monitor_near_top(self):
        self.assertEqual(
            restore_position((140, 80, 58, 58), (440, 500), self.monitors),
            (0, 80),
        )

    def test_right_monitor_keeps_current_screen(self):
        x, y = restore_position((3100, 850, 58, 58), (440, 500), self.monitors)
        self.assertGreaterEqual(x, 1080)
        self.assertLessEqual(x + 440, 3640)
        self.assertEqual(y, 850)

    def test_rightmost_and_lower_edge_clamps(self):
        x, y = restore_position((3590, 1380, 48, 48), (440, 500), self.monitors)
        self.assertEqual(x, 3200)
        self.assertEqual(y, 940)

    def test_secondary_monitor_negative_origin(self):
        screens = [(-1920, 0, 1920, 1080), (0, 0, 2560, 1440)]
        x, y = restore_position((-1810, 120, 58, 58), (600, 450), screens)
        self.assertGreaterEqual(x, -1920)
        self.assertLess(x, 0)
        self.assertEqual(y, 120)

    def test_late_center_snap_detected(self):
        monitors = [(0, 0, 1280, 1024)]
        self.assertTrue(looks_wm_centered(
            (420, 262, 440, 500), monitors, (69, 190)
        ))
        self.assertFalse(looks_wm_centered(
            (79, 195, 440, 500), monitors, (69, 190)
        ))
        # Arbitrary user-initiated movement must not be mistaken for recenter.
        self.assertFalse(looks_wm_centered(
            (640, 40, 440, 500), monitors, (69, 190)
        ))

    def test_center_of_secondary_monitor(self):
        monitors = [(0, 0, 1080, 1920), (1080, 0, 2560, 1440)]
        self.assertTrue(looks_wm_centered(
            (2140, 470, 440, 500), monitors, (1210, 180)
        ))

    def test_without_monitor_information(self):
        self.assertEqual(restore_position((300, 400, 50, 50), (400, 500), []),
                         (125, 400))

    def test_rectangle_uses_live_handle_location(self):
        screens = [(0, 0, 1920, 1080)]
        first = restore_position((10, 10, 188, 46), (600, 500), screens)
        second = restore_position((1300, 300, 188, 46), (600, 500), screens)
        self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()
