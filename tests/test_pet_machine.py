import unittest

from context_badge.pet_machine import PetMachine
from context_badge.pet_spec import IDLE, JUMPING, LOOK, WAITING, WAVING, CellRef, look_cell


class PetMachineTests(unittest.TestCase):
    def test_starts_on_idle_row(self) -> None:
        machine = PetMachine()
        self.assertEqual(machine.state, IDLE)
        self.assertEqual(machine.current_cell(), CellRef(0, 0))

    def test_idle_loops_six_frames(self) -> None:
        machine = PetMachine()
        columns = []
        for _ in range(6):
            cell, delay = machine.step()
            columns.append(cell.column)
            self.assertGreaterEqual(delay, 16)
            self.assertEqual(cell.row, 0)
        self.assertEqual(columns, [0, 1, 2, 3, 4, 5])
        self.assertEqual(machine.current_cell(), CellRef(0, 0))

    def test_request_waiting_is_reserved_for_later(self) -> None:
        machine = PetMachine()
        machine.request(WAITING)
        self.assertEqual(machine.state, WAITING)
        self.assertEqual(machine.current_cell(), CellRef(6, 0))

    def test_pulse_oneshot_returns_to_activity(self) -> None:
        machine = PetMachine()
        machine.request(WAITING)
        machine.pulse(WAVING)
        self.assertEqual(machine.state, WAVING)
        for _ in range(4):
            machine.step()
        self.assertEqual(machine.state, WAITING)
        self.assertEqual(machine.current_cell(), CellRef(6, 0))

    def test_look_overlays_idle_only(self) -> None:
        machine = PetMachine()
        machine.set_look_index(4)
        self.assertEqual(machine.state, LOOK)
        self.assertEqual(machine.current_cell(), look_cell(4))
        machine.advance()
        self.assertEqual(machine.current_cell(), look_cell(4))
        machine.request(WAITING)
        self.assertEqual(machine.current_cell().row, 6)
        machine.request(IDLE)
        self.assertEqual(machine.current_cell(), look_cell(4))
        machine.set_look_index(None)
        self.assertEqual(machine.current_cell(), CellRef(0, 0))

    def test_unknown_request_falls_back_to_idle(self) -> None:
        machine = PetMachine()
        machine.request("nope")
        self.assertEqual(machine.state, IDLE)

    def test_pulse_jump_is_wired(self) -> None:
        machine = PetMachine()
        machine.pulse(JUMPING)
        self.assertEqual(machine.current_cell(), CellRef(4, 0))


if __name__ == "__main__":
    unittest.main()
