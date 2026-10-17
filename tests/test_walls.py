import unittest

import mujoco
from shapely.geometry import LineString

from robo_sim_py import Corridor, Scenario
from robo_sim_py.simulation import build_model, example_robot
from robo_sim_py.simulation.walls import WALL_THICKNESS, wall_segments


class WallTests(unittest.TestCase):
    def test_straight_has_two_sides_and_open_ends(self):
        scenario = Scenario((Corridor(2),))
        walls = wall_segments(scenario)
        self.assertEqual(len(walls), 2)
        for start, end in walls:
            self.assertAlmostEqual(start[1], end[1])
            self.assertAlmostEqual(abs(start[1]), (scenario.width + WALL_THICKNESS) / 2)
            self.assertAlmostEqual(abs(end[0] - start[0]), 2)

    def test_turns_and_crossings_do_not_put_walls_across_center_line(self):
        for turns in ((0, 90), (0, -90), (0, 135), (0, 90, 90, 90, 90)):
            with self.subTest(turns=turns):
                scenario = Scenario(tuple(Corridor(.6, turn) for turn in turns))
                route = LineString(scenario.points())
                for start, end in wall_segments(scenario):
                    # Allow the small polygonal approximation of curved walls.
                    clearance = LineString([start, end]).distance(route) - WALL_THICKNESS / 2
                    self.assertGreater(clearance, scenario.width / 2 - .003)

    def test_robot_actually_collides_with_side_wall(self):
        model = build_model(example_robot(), Scenario((Corridor(2),)))
        data = mujoco.MjData(model)
        data.qpos[:2] = [1, .35]
        mujoco.mj_forward(model, data)
        wall_contacts = [contact for contact in data.contact if any(
            model.geom(index).name.startswith("corridor_wall_")
            for index in (contact.geom1, contact.geom2))]
        self.assertTrue(wall_contacts)
        self.assertTrue(any(contact.dist < 0 for contact in wall_contacts))
