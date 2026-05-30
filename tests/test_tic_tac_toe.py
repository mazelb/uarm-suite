"""Tests for the tic-tac-toe activity: board, AI, geometry, drawing (Phase 7B)."""

from __future__ import annotations

import pytest

from activities.tic_tac_toe import (
    Board,
    GridConfig,
    O,
    TicTacToe,
    X,
    best_move,
    grid_strokes,
    o_strokes,
    x_strokes,
)
from kinematics import in_workspace

# ---------------------------------------------------------------------------
# Board model
# ---------------------------------------------------------------------------


def test_winner_rows_cols_diags():
    assert Board([[X, X, X], ["", "", ""], ["", "", ""]]).winner() == X
    assert Board([["", "", ""], [O, O, O], ["", "", ""]]).winner() == O
    assert Board([[X, "", ""], [X, "", ""], [X, "", ""]]).winner() == X
    assert Board([[X, "", ""], ["", X, ""], ["", "", X]]).winner() == X
    assert Board([["", "", O], ["", O, ""], [O, "", ""]]).winner() == O


def test_no_winner_and_draw():
    assert Board().winner() is None
    full = Board([[X, O, X], [X, O, O], [O, X, X]])
    assert full.winner() is None
    assert full.is_draw() is True
    assert full.is_over() is True


def test_place_rejects_taken_and_oob():
    b = Board()
    b.place(0, 0, X)
    with pytest.raises(ValueError):
        b.place(0, 0, O)
    with pytest.raises(ValueError):
        b.place(3, 0, O)


# ---------------------------------------------------------------------------
# Minimax AI
# ---------------------------------------------------------------------------


def test_ai_takes_immediate_win():
    # O can win by completing the top row at (0, 2).
    b = Board([[O, O, ""], [X, X, ""], ["", "", ""]])
    assert best_move(b, O) == (0, 2)


def test_ai_blocks_opponent_win():
    # X threatens the top row; O must block at (0, 2).
    b = Board([[X, X, ""], [O, "", ""], ["", "", ""]])
    assert best_move(b, O) == (0, 2)


def test_ai_is_deterministic():
    b = Board([["", X, ""], ["", "", ""], ["", "", ""]])
    assert best_move(b, O) == best_move(b, O)


def test_optimal_o_never_loses():
    """Exhaustively: against an optimal O, the human X can never win."""

    def explore(board: Board, to_move: str) -> None:
        if board.is_over():
            assert board.winner() != X, "optimal O should never let X win"
            return
        if to_move == X:
            for r, c in board.available():
                nxt = board.copy()
                nxt.place(r, c, X)
                explore(nxt, O)
        else:
            r, c = best_move(board, O)
            nxt = board.copy()
            nxt.place(r, c, O)
            explore(nxt, X)

    explore(Board(), X)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_cell_center_mapping():
    cfg = GridConfig()  # center (250, 0), cell 40
    assert cfg.cell_center(1, 1) == (250.0, 0.0)
    assert cfg.cell_center(0, 0) == (290.0, 40.0)
    assert cfg.cell_center(2, 2) == (210.0, -40.0)


def _all_points(cfg: GridConfig) -> list[tuple[float, float]]:
    strokes = list(grid_strokes(cfg))
    for r in range(3):
        for c in range(3):
            strokes += x_strokes(cfg, r, c)
            strokes += o_strokes(cfg, r, c)
    return [pt for stroke in strokes for pt in stroke]


def test_all_drawing_points_reachable_default_grid():
    cfg = GridConfig()
    for x, y in _all_points(cfg):
        for z in (cfg.table_z, cfg.pen_up_z):
            assert in_workspace(x, y, z, wrist=cfg.wrist), f"({x:.1f},{y:.1f},{z:.1f}) unreachable"


# ---------------------------------------------------------------------------
# Drawing / integration with a recording fake arm
# ---------------------------------------------------------------------------


class FakeArm:
    """Records motion commands instead of driving a bus — fast and inspectable."""

    def __init__(self) -> None:
        self.positions: list[tuple[float, float, float]] = []
        self.joints: list[tuple[float, float, float, float]] = []
        self.homed = False

    def set_position(self, x, y, z, *, wrist=0.0, speed=None, blocking=False):
        self.positions.append((x, y, z))

    def set_joint_angles(self, j0, j1, j2, j3, *, speed=None, blocking=False):
        self.joints.append((j0, j1, j2, j3))

    def home(self, blocking=True):
        self.homed = True


def test_start_draws_grid():
    game = TicTacToe()
    arm = FakeArm()
    state = game.start(arm)
    assert state["started"] is True
    assert state["turn"] == X
    assert len(arm.positions) > 0  # grid was drawn


def test_human_move_draws_and_arm_responds():
    game = TicTacToe()
    arm = FakeArm()
    game.start(arm)
    arm.positions.clear()
    state = game.human_move(arm, 1, 1)  # X center
    assert state["board"][1][1] == X
    # Arm placed an O somewhere in response (game not over after one move).
    o_count = sum(row.count(O) for row in state["board"])
    assert o_count == 1
    assert len(arm.positions) > 0


def test_invalid_moves_rejected():
    game = TicTacToe()
    arm = FakeArm()
    game.start(arm)
    game.human_move(arm, 0, 0)
    with pytest.raises(ValueError):
        game.human_move(arm, 0, 0)  # taken (also occupied by arm's reply maybe)
    with pytest.raises(ValueError):
        game.human_move(arm, 5, 5)  # out of range


def test_full_game_reaches_terminal_state():
    game = TicTacToe()
    arm = FakeArm()
    game.start(arm)
    # Human always plays the first available cell; against optimal O this ends
    # in a draw or an arm win, never a human win.
    while not game.state()["over"]:
        avail = [(r, c) for r in range(3) for c in range(3) if not game.board.cells[r][c]]
        game.human_move(arm, *avail[0])
    final = game.state()
    assert final["over"] is True
    assert final["winner"] in (O, None)
    assert final["winner"] != X


def test_options_override_grid_config():
    game = TicTacToe()
    arm = FakeArm()
    state = game.start(arm, {"center_x": 240.0, "cell": 36.0})
    assert state["config"]["center_x"] == 240.0
    assert state["config"]["cell"] == 36.0
