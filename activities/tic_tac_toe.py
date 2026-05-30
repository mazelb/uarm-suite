"""Tic-tac-toe: the human plays X (first), the arm plays O (unbeatable).

Board / world mapping
---------------------
The 3x3 board uses screen-style indices: ``row`` 0 is the top, ``col`` 0 is the
left. These map to arm-frame Cartesian coordinates so the grid sits in front of
the base:

* ``row`` increases toward the base: row 0 is the far side (larger X), row 2 is
  nearest (smaller X).
* ``col`` increases to the arm's right: col 0 is left (+Y), col 2 is right (-Y).

Drawing model
-------------
The kinematics has no wrist pitch, so the pen cannot point straight down in the
model. We command the *tool-tip* Cartesian position as the pen contact point;
the physical pen mount/length is absorbed into Z calibration on hardware. The
pen lifts by ``GridConfig.pen_up`` mm between strokes. See :mod:`activities._draw`.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from kinematics import JointAngles, check_joint_limits

from . import register_activity
from ._draw import Stroke, draw_strokes

if TYPE_CHECKING:
    from arm import UArm

EMPTY = ""
X = "X"
O = "O"  # noqa: E741 — game token, not the letter "oh" ambiguity in this context

_LINES = (
    # rows
    ((0, 0), (0, 1), (0, 2)),
    ((1, 0), (1, 1), (1, 2)),
    ((2, 0), (2, 1), (2, 2)),
    # cols
    ((0, 0), (1, 0), (2, 0)),
    ((0, 1), (1, 1), (2, 1)),
    ((0, 2), (1, 2), (2, 2)),
    # diagonals
    ((0, 0), (1, 1), (2, 2)),
    ((0, 2), (1, 1), (2, 0)),
)


# ---------------------------------------------------------------------------
# Board model (pure)
# ---------------------------------------------------------------------------


class Board:
    """A 3x3 tic-tac-toe board. Cells are ``"" | "X" | "O"``."""

    def __init__(self, cells: list[list[str]] | None = None) -> None:
        self.cells: list[list[str]] = cells or [[EMPTY] * 3 for _ in range(3)]

    def place(self, row: int, col: int, player: str) -> None:
        if not (0 <= row <= 2 and 0 <= col <= 2):
            raise ValueError(f"cell ({row}, {col}) out of range")
        if self.cells[row][col]:
            raise ValueError(f"cell ({row}, {col}) is already taken")
        self.cells[row][col] = player

    def available(self) -> list[tuple[int, int]]:
        return [(r, c) for r in range(3) for c in range(3) if not self.cells[r][c]]

    def winner(self) -> str | None:
        for line in _LINES:
            a, b, c = (self.cells[r][col] for r, col in line)
            if a and a == b == c:
                return a
        return None

    def is_draw(self) -> bool:
        return self.winner() is None and not self.available()

    def is_over(self) -> bool:
        return self.winner() is not None or not self.available()

    def copy(self) -> Board:
        return Board([row[:] for row in self.cells])


# ---------------------------------------------------------------------------
# AI — deterministic minimax with alpha-beta pruning
# ---------------------------------------------------------------------------


def _other(player: str) -> str:
    return O if player == X else X


def _score(board: Board, ai: str, depth: int) -> int | None:
    w = board.winner()
    if w == ai:
        return 10 - depth
    if w is not None:
        return depth - 10
    if not board.available():
        return 0
    return None


def _minimax(board: Board, to_move: str, ai: str, alpha: int, beta: int, depth: int) -> int:
    terminal = _score(board, ai, depth)
    if terminal is not None:
        return terminal

    if to_move == ai:
        best = -math.inf
        for r, c in board.available():
            board.cells[r][c] = to_move
            best = max(best, _minimax(board, _other(to_move), ai, alpha, beta, depth + 1))
            board.cells[r][c] = EMPTY
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return int(best)
    else:
        best = math.inf
        for r, c in board.available():
            board.cells[r][c] = to_move
            best = min(best, _minimax(board, _other(to_move), ai, alpha, beta, depth + 1))
            board.cells[r][c] = EMPTY
            beta = min(beta, best)
            if alpha >= beta:
                break
        return int(best)


def best_move(board: Board, player: str) -> tuple[int, int]:
    """Return the optimal ``(row, col)`` for ``player``.

    Deterministic: cells are scanned in (row, col) order and the first cell
    achieving the best value wins ties, so the same board always yields the
    same move.
    """
    work = board.copy()
    best_val = -math.inf
    best_cell: tuple[int, int] | None = None
    for r, c in work.available():
        work.cells[r][c] = player
        val = _minimax(work, _other(player), player, -math.inf, math.inf, 1)
        work.cells[r][c] = EMPTY
        if val > best_val:
            best_val = val
            best_cell = (r, c)
    if best_cell is None:
        raise ValueError("no moves available")
    return best_cell


# ---------------------------------------------------------------------------
# Grid geometry
# ---------------------------------------------------------------------------


@dataclass
class GridConfig:
    """Placement of the physical grid in the arm's workspace (mm)."""

    center_x: float = 250.0
    center_y: float = 0.0
    cell: float = 40.0
    table_z: float = 0.0  # pen contact height
    pen_up: float = 20.0  # lift above table_z between strokes
    wrist: float = 0.0
    mark_scale: float = 0.35  # mark half-size as a fraction of cell

    @property
    def pen_up_z(self) -> float:
        return self.table_z + self.pen_up

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        """World (x, y) of a cell center. row 0 = far (+X), col 0 = left (+Y)."""
        x = self.center_x + (1 - row) * self.cell
        y = self.center_y + (1 - col) * self.cell
        return x, y


def grid_strokes(cfg: GridConfig) -> list[Stroke]:
    """The two vertical + two horizontal lines forming the # outline."""
    half = 1.5 * cfg.cell  # outer extent of the 3-cell grid
    off = 0.5 * cfg.cell  # inner line offset from center
    cx, cy = cfg.center_x, cfg.center_y
    strokes: list[Stroke] = []
    # Lines of constant Y (vary X over the full grid height): the two "vertical"
    # bars of the # as seen from above.
    for dy in (-off, off):
        strokes.append([(cx - half, cy + dy), (cx + half, cy + dy)])
    # Lines of constant X (vary Y).
    for dx in (-off, off):
        strokes.append([(cx + dx, cy - half), (cx + dx, cy + half)])
    return strokes


def x_strokes(cfg: GridConfig, row: int, col: int) -> list[Stroke]:
    cx, cy = cfg.cell_center(row, col)
    m = cfg.mark_scale * cfg.cell
    return [
        [(cx - m, cy - m), (cx + m, cy + m)],
        [(cx - m, cy + m), (cx + m, cy - m)],
    ]


def o_strokes(cfg: GridConfig, row: int, col: int, segments: int = 8) -> list[Stroke]:
    cx, cy = cfg.cell_center(row, col)
    r = cfg.mark_scale * cfg.cell
    pts: Stroke = []
    for i in range(segments + 1):  # closed loop
        t = 2.0 * math.pi * i / segments
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return [pts]


# ---------------------------------------------------------------------------
# Drawing routines
# ---------------------------------------------------------------------------


def _draw(arm: UArm, cfg: GridConfig, strokes: list[Stroke]) -> None:
    draw_strokes(
        arm,
        strokes,
        table_z=cfg.table_z,
        pen_up_z=cfg.pen_up_z,
        wrist=cfg.wrist,
    )


def draw_grid(arm: UArm, cfg: GridConfig) -> None:
    _draw(arm, cfg, grid_strokes(cfg))


def draw_x(arm: UArm, cfg: GridConfig, row: int, col: int) -> None:
    _draw(arm, cfg, x_strokes(cfg, row, col))


def draw_o(arm: UArm, cfg: GridConfig, row: int, col: int) -> None:
    _draw(arm, cfg, o_strokes(cfg, row, col))


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

_NEUTRAL = JointAngles(j0=0.0, j1=45.0, j2=-45.0, j3=0.0)


def _safe_joints(arm: UArm, j0: float, j1: float, j2: float, j3: float) -> None:
    """Move to a joint pose, refusing anything outside the limits."""
    check_joint_limits(JointAngles(j0=j0, j1=j1, j2=j2, j3=j3))
    arm.set_joint_angles(j0, j1, j2, j3, blocking=True)


def _celebrate(arm: UArm) -> None:
    """A small wrist wave."""
    for j3 in (30.0, -30.0, 30.0, 0.0):
        _safe_joints(arm, 0.0, 45.0, -45.0, j3)


def _hang_head(arm: UArm) -> None:
    """Droop the arm forward and down."""
    _safe_joints(arm, 0.0, 30.0, -60.0, 0.0)
    time.sleep(0.3)
    _safe_joints(arm, *_NEUTRAL)


@register_activity
class TicTacToe:
    """Interactive tic-tac-toe. Human is X (moves first); arm is O (optimal)."""

    slug = "tic-tac-toe"
    name = "Tic-Tac-Toe"
    description = "Play tic-tac-toe against the arm — you are X, the arm is O."

    def __init__(self, config: GridConfig | None = None) -> None:
        self.config = config or GridConfig()
        self.board = Board()
        self.human = X
        self.ai = O
        self.turn = X
        self.status = "Press New Game to start."
        self.started = False

    # -- ActivityBase ----------------------------------------------------

    def setup(self, arm: UArm) -> None:
        arm.home(blocking=True)

    def run(self, arm: UArm) -> None:
        """Runnable entry point: draw a fresh grid (the game itself is driven
        interactively via start/human_move)."""
        self.start(arm)

    def cleanup(self, arm: UArm) -> None:
        return None

    # -- InteractiveActivity --------------------------------------------

    def start(self, arm: UArm, options: dict | None = None) -> dict:
        if options:
            known = {f for f in GridConfig.__dataclass_fields__}
            self.config = GridConfig(
                **{**asdict(self.config), **{k: v for k, v in options.items() if k in known}}
            )
        self.board = Board()
        self.turn = self.human
        self.started = True
        self.status = "Your turn (X)."
        draw_grid(arm, self.config)
        return self.state()

    def human_move(self, arm: UArm, row: int, col: int) -> dict:
        if not self.started:
            raise ValueError("game has not started")
        if self.board.is_over():
            raise ValueError("game is already over")
        if self.turn != self.human:
            raise ValueError("not your turn")

        self.board.place(row, col, self.human)  # raises on bad/taken cell
        draw_x(arm, self.config, row, col)

        if self._check_outcome(arm):
            return self.state()

        # Arm responds.
        self.turn = self.ai
        self.status = "Arm is thinking…"
        ar, ac = best_move(self.board, self.ai)
        self.board.place(ar, ac, self.ai)
        draw_o(arm, self.config, ar, ac)

        if self._check_outcome(arm):
            return self.state()

        self.turn = self.human
        self.status = "Your turn (X)."
        return self.state()

    def state(self) -> dict:
        w = self.board.winner()
        return {
            "board": [row[:] for row in self.board.cells],
            "turn": self.turn,
            "status": self.status,
            "winner": w,
            "over": self.board.is_over(),
            "started": self.started,
            "config": asdict(self.config),
        }

    # -- internals -------------------------------------------------------

    def _check_outcome(self, arm: UArm) -> bool:
        """Update status/celebration if the game ended. Returns True if over."""
        w = self.board.winner()
        if w == self.human:
            self.status = "You win! 🎉"
            self.turn = self.human
            _hang_head(arm)  # arm lost
            return True
        if w == self.ai:
            self.status = "Arm wins."
            self.turn = self.ai
            _celebrate(arm)
            return True
        if self.board.is_draw():
            self.status = "Draw."
            return True
        return False
