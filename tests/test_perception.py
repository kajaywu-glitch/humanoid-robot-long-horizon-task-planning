import unittest

from submission.task_solver.perception.scene import ObservationParser


class ObservationParserTests(unittest.TestCase):
    def test_missing_fields_produce_safe_defaults(self) -> None:
        snapshot = ObservationParser().parse({})

        self.assertIsNone(snapshot.task_id)
        self.assertEqual(snapshot.elapsed_minutes, 0.0)
        self.assertFalse(snapshot.has_rgb)
        self.assertFalse(snapshot.is_holding_object)

    def test_extracts_contract_fields(self) -> None:
        snapshot = ObservationParser().parse(
            {
                "Kuavo": {
                    "body_state": {
                        "world_position": [1, 2, 3],
                        "world_orient": [0, 0, 0, 1],
                    }
                },
                "pick": True,
                "camera": {"rgb": object(), "depth": object()},
                "extras": {
                    "Current_Task_ID": "TaskTwo",
                    "time(minutes)": 2.5,
                    "scores": {"TaskOne": {"score": 30}},
                    "info": "",
                },
            }
        )

        self.assertEqual(snapshot.task_id, "TaskTwo")
        self.assertEqual(snapshot.robot_position, (1.0, 2.0, 3.0))
        self.assertTrue(snapshot.has_rgb)
        self.assertTrue(snapshot.has_depth)
        self.assertTrue(snapshot.is_holding_object)


if __name__ == "__main__":
    unittest.main()

