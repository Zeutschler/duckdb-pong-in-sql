"""
DuckPong - A Pong game implemented entirely in SQL using DuckDB

MIT License
Copyright (c) 2025 Thomas Zeutschler

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import time, curses, duckdb, math, random, os, sys, platform

# =============================================================================
# GAME SETUP - Initialize game parameters and state in SQL
# =============================================================================
SETUP_SQL = """
-- Game constants: field dimensions and paddle properties
CREATE TEMP TABLE params AS
SELECT
  80 AS W,              -- Width of the playing field (characters)
  25 AS H,              -- Height of the playing field (characters)
  7 AS PADDLE_H,        -- Height of each paddle (characters)
  2 AS PADDLE_SPEED;    -- How fast paddles can move per frame

-- Game state: positions, velocities, and scores
-- This single row gets updated every frame with new positions
CREATE TEMP TABLE state(
  tick INTEGER,         -- Frame counter (increases each update)
  ax INTEGER,           -- Player A paddle Y position (left side)
  bx INTEGER,           -- Player B paddle Y position (right side)
  ball_x INTEGER,       -- Ball X position (0 to W-1)
  ball_y INTEGER,       -- Ball Y position (0 to H-1)
  vx INTEGER,           -- Ball velocity in X direction (±1)
  vy INTEGER,           -- Ball velocity in Y direction (-2, -1, 0, 1, 2)
  score_a INTEGER,      -- Player A score
  score_b INTEGER       -- Player B score
);

-- Initialize game with random starting position and angle
INSERT INTO state
SELECT
  0,                                                          -- tick = 0 (start)
  (H-PADDLE_H)/2,                                            -- Player A paddle centered
  (H-PADDLE_H)/2,                                            -- Player B paddle centered
  W/2,                                                        -- Ball at horizontal center
  CAST(H/2 + (random() * 6 - 3) AS INTEGER),                -- Ball Y: center ± 3 pixels
  CASE WHEN random() < 0.5 THEN 1 ELSE -1 END,              -- Ball direction: random left/right
  CAST((random() * 5 - 2) AS INTEGER),                      -- Ball angle: -2 to +2 (5 angles)
  0,                                                          -- Score A = 0
  0                                                           -- Score B = 0
FROM params;
"""

# =============================================================================
# GAME LOGIC - One frame of physics, AI, collisions, and scoring
# This SQL query runs every frame and updates the entire game state
# =============================================================================
TICK_SQL = """
-- Use CTEs (Common Table Expressions) to break down the game logic into clear steps
-- Each WITH clause is like a mini-table that feeds into the next step
WITH
  -- Load game parameters and current state for easy reference
  p AS (SELECT * FROM params),
  s AS (SELECT * FROM state),

-- STEP 1: AI DECISION - Calculate where each paddle should move
-- The AI mimics human players: track defensively, then make strategic shots when close
ai AS (
  SELECT
    -- PLAYER A (left side) - Decide where to move the paddle
    CASE
      -- When ball is CLOSE (≤5 pixels away) and approaching: attempt trick shots!
      -- Position paddle to hit ball at specific zones for different angles
      WHEN s.vx < 0 AND s.ball_x <= 5 THEN
        CASE
          WHEN random() < 0.25 THEN greatest(s.ball_y - 0, 1)  -- Hit top: steep up (vy=-2)
          WHEN random() < 0.50 THEN greatest(s.ball_y - 1, 1)  -- Hit upper: diagonal up (vy=-1)
          WHEN random() < 0.55 THEN greatest(s.ball_y - 3, 1)  -- Hit center: straight (vy=0) RARE!
          WHEN random() < 0.75 THEN greatest(s.ball_y - 5, 1)  -- Hit lower: diagonal down (vy=+1)
          ELSE greatest(s.ball_y - 6, 1)                        -- Hit bottom: steep down (vy=+2)
        END
      -- When ball is FAR: track defensively (85% accuracy for more scoring opportunities)
      WHEN random() < 0.85 THEN
        CASE WHEN s.ball_y < s.ax + 2 THEN greatest(s.ax - p.PADDLE_SPEED, 1)
             WHEN s.ball_y > s.ax + p.PADDLE_H - 3 THEN least(s.ax + p.PADDLE_SPEED, p.H - p.PADDLE_H - 1)
             ELSE s.ax END
      -- 15% of the time: don't move (more imperfection for shorter games)
      ELSE s.ax
    END AS ax2,
    -- PLAYER B (right side) - Same logic but mirrored
    CASE
      WHEN s.vx > 0 AND s.ball_x >= p.W - 6 THEN
        CASE
          WHEN random() < 0.25 THEN greatest(s.ball_y - 0, 1)
          WHEN random() < 0.50 THEN greatest(s.ball_y - 1, 1)
          WHEN random() < 0.55 THEN greatest(s.ball_y - 3, 1)
          WHEN random() < 0.75 THEN greatest(s.ball_y - 5, 1)
          ELSE greatest(s.ball_y - 6, 1)
        END
      WHEN random() < 0.85 THEN
        CASE WHEN s.ball_y < s.bx + 2 THEN greatest(s.bx - p.PADDLE_SPEED, 1)
             WHEN s.ball_y > s.bx + p.PADDLE_H - 3 THEN least(s.bx + p.PADDLE_SPEED, p.H - p.PADDLE_H - 1)
             ELSE s.bx END
      ELSE s.bx
    END AS bx2
  FROM p, s
),

-- STEP 2: BALL MOVEMENT - Move ball by its velocity
step AS (
  SELECT s.ball_x + s.vx AS nx, s.ball_y + s.vy AS ny, s.vx, s.vy FROM s
),

-- STEP 3: WALL COLLISION - Bounce ball off top/bottom walls
wall AS (
  SELECT
    nx,
    CASE WHEN ny <= 1 THEN 1 WHEN ny >= p.H-2 THEN p.H-2 ELSE ny END AS ny1,
    vx AS vx1,
    CASE WHEN ny <= 1 OR ny >= p.H-2 THEN -vy ELSE vy END AS vy1  -- Flip Y velocity
  FROM step, p
),

-- STEP 4: PADDLE COLLISION - Detect hits and calculate bounce angles
-- This is the magic! Ball angle depends on WHERE it hits the paddle (classic Pong physics)
paddle AS (
  SELECT
    w.nx, w.ny1,
    -- Reverse horizontal direction if paddle hit
    CASE
      WHEN w.nx <= 1 AND w.vx1 < 0 AND w.ny1 BETWEEN ai.ax2 AND ai.ax2 + p.PADDLE_H - 1 THEN 1
      WHEN w.nx >= p.W-2 AND w.vx1 > 0 AND w.ny1 BETWEEN ai.bx2 AND ai.bx2 + p.PADDLE_H - 1 THEN -1
      ELSE w.vx1 END AS vx2,
    -- Calculate new vertical velocity based on hit zone (5 zones on paddle)
    -- Top edge = steep up (-2), Center = straight (0), Bottom edge = steep down (+2)
    CASE
      WHEN w.nx <= 1 AND w.vx1 < 0 AND w.ny1 BETWEEN ai.ax2 AND ai.ax2 + p.PADDLE_H - 1 THEN
        CASE WHEN w.ny1 - ai.ax2 = 0 THEN -2      -- Position 0: top edge
             WHEN w.ny1 - ai.ax2 <= 2 THEN -1     -- Positions 1-2: upper
             WHEN w.ny1 - ai.ax2 <= 4 THEN 0      -- Positions 3-4: center
             WHEN w.ny1 - ai.ax2 <= 5 THEN 1      -- Position 5: lower
             ELSE 2 END                            -- Position 6: bottom edge
      WHEN w.nx >= p.W-2 AND w.vx1 > 0 AND w.ny1 BETWEEN ai.bx2 AND ai.bx2 + p.PADDLE_H - 1 THEN
        CASE WHEN w.ny1 - ai.bx2 = 0 THEN -2
             WHEN w.ny1 - ai.bx2 <= 2 THEN -1
             WHEN w.ny1 - ai.bx2 <= 4 THEN 0
             WHEN w.ny1 - ai.bx2 <= 5 THEN 1
             ELSE 2 END
      ELSE w.vy1 END AS vy2,
    ai.ax2 AS ax2, ai.bx2 AS bx2
  FROM wall w, ai, p
),
-- STEP 5: SCORING - Detect if ball went past a paddle
sc AS (
  SELECT
    CASE WHEN paddle.nx < 1 THEN 'B'              -- Ball past left: Player B scores
         WHEN paddle.nx > p.W-2 THEN 'A'          -- Ball past right: Player A scores
         ELSE NULL END AS point_to,               -- NULL = still in play
    paddle.*, p.W, p.H
  FROM paddle, p
),

-- STEP 6: UPDATE STATE - Combine all changes and increment scores
next_state AS (
  SELECT
    s.tick + 1 AS tick,                           -- Increment frame counter
    sc.ax2 AS ax, sc.bx2 AS bx,                   -- New paddle positions
    -- Ball position: reset to center if scored, otherwise use new position
    CASE WHEN sc.point_to IS NULL THEN sc.nx
         WHEN sc.point_to='A' THEN sc.W/2 + 1 ELSE sc.W/2 - 1 END AS ball_x,
    CASE WHEN sc.point_to IS NULL THEN sc.ny1
         ELSE CAST(sc.H/2 + (random() * 6 - 3) AS INTEGER) END AS ball_y,
    -- Ball velocity: keep current if in play, otherwise random serve
    CASE WHEN sc.point_to IS NULL THEN sc.vx2
         WHEN sc.point_to='A' THEN -1 ELSE 1 END AS vx,
    CASE WHEN sc.point_to IS NULL THEN sc.vy2
         ELSE CAST((random() * 5 - 2) AS INTEGER) END AS vy,
    -- Increment score if someone scored
    s.score_a + COALESCE((sc.point_to='A')::INT, 0) AS score_a,
    s.score_b + COALESCE((sc.point_to='B')::INT, 0) AS score_b
  FROM sc, state s
)
-- Finally, write the new state back to the state table
UPDATE state
SET tick = n.tick, ax = n.ax, bx = n.bx,
    ball_x = n.ball_x, ball_y = n.ball_y,
    vx = n.vx, vy = n.vy,
    score_a = n.score_a, score_b = n.score_b
FROM next_state n;
"""

# =============================================================================
# RENDERING - Generate the visual display purely in SQL
# =============================================================================
RENDER_SQL = """
-- Generate the entire game screen as ASCII art, one character at a time
-- This creates an 80x25 grid and decides what character to put in each position
SELECT y,
       string_agg(
         CASE
           WHEN y IN (0,p.H-1) THEN '▀'                                         -- Top/bottom borders
           WHEN x=1 AND y BETWEEN s.ax AND s.ax + p.PADDLE_H - 1 THEN '█'      -- Player A paddle (left)
           WHEN x=p.W-2 AND y BETWEEN s.bx AND s.bx + p.PADDLE_H - 1 THEN '█'  -- Player B paddle (right)
           WHEN x=s.ball_x AND y=s.ball_y THEN '█'                              -- Ball
           WHEN x=p.W/2 AND (y % 3)=1 THEN '█'                                  -- Center line (dotted)
           ELSE ' '                                                              -- Empty space
         END, ''
       ) AS line
FROM params p, state s, range(0,p.H) AS t_y(y), range(0,p.W) AS t_x(x)
GROUP BY y
ORDER BY y;
"""

# =============================================================================
# SCORE DISPLAY - Large 3x5 digit patterns for retro Pong aesthetic
# =============================================================================
DIGITS = {
    0: ["███", "█ █", "█ █", "█ █", "███"],
    1: [" █ ", "██ ", " █ ", " █ ", "███"],
    2: ["███", "  █", "███", "█  ", "███"],
    3: ["███", "  █", "███", "  █", "███"],
    4: ["█ █", "█ █", "███", "  █", "  █"],
    5: ["███", "█  ", "███", "  █", "███"],
    6: ["███", "█  ", "███", "█ █", "███"],
    7: ["███", "  █", "  █", "  █", "  █"],
    8: ["███", "█ █", "███", "█ █", "███"],
    9: ["███", "█ █", "███", "  █", "███"],
}

def draw_digit(stdscr, digit, y, x, color_pair):
    """Draw a large 3x5 digit at the given position."""
    if digit < 0 or digit > 9:
        return
    pattern = DIGITS[digit]
    for i, row in enumerate(pattern):
        try:
            stdscr.addstr(y + i, x, row, color_pair)
        except curses.error:
            pass

def play_beep():
    """Play a simple beep sound."""
    try:
        curses.beep()
    except:
        pass

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    # color pair 1: dim/grey for borders
    curses.init_pair(1, 8, -1)  # grey/dim
    # color pair 2: white for paddles
    curses.init_pair(2, curses.COLOR_WHITE, -1)
    # color pair 3: white for ball
    curses.init_pair(3, curses.COLOR_WHITE, -1)
    # color pair 4: yellow for DuckDB text
    curses.init_pair(4, curses.COLOR_YELLOW, -1)

    con = duckdb.connect(database=":memory:")
    con.execute(SETUP_SQL)

    FPS = 30
    MIN_FPS = 15
    MAX_MODE = False  # Track if we're in "max" performance mode
    sound_enabled = False  # Sound effects (toggle with 's')
    frame_dt = 1.0 / FPS
    last = time.time()
    actual_fps = 30  # Track actual achieved FPS

    # Track previous state for sound effects
    prev_score_a = 0
    prev_score_b = 0
    prev_vx = 1  # Track ball velocity to detect paddle hits
    last_paddle_beep_time = 0  # Throttle paddle beeps to avoid overlap at high FPS
    MIN_PADDLE_BEEP_INTERVAL = 1.0 / 120  # Max 120 paddle beeps per second

    while True:
        # Handle keyboard input
        ch = stdscr.getch()
        if ch == 27:  # ESC
            break
        elif ch == ord('s') or ch == ord('S'):  # Toggle sound effects
            sound_enabled = not sound_enabled
        elif ch == ord('+'):  # + key, double the framerate or go to max
            if FPS == 120:
                MAX_MODE = True
                frame_dt = 0  # No frame limiting in max mode
            elif not MAX_MODE:
                FPS = FPS * 2
                frame_dt = 1.0 / FPS
        elif ch == ord('-'):  # - key, halve the framerate
            if MAX_MODE:
                MAX_MODE = False
                FPS = 120
                frame_dt = 1.0 / FPS
            else:
                new_fps = FPS // 2
                if new_fps >= MIN_FPS:
                    FPS = new_fps
                    frame_dt = 1.0 / FPS

        frame_start = time.time()
        con.execute(TICK_SQL)
        rows = con.execute(RENDER_SQL).fetchall()

        stdscr.erase()

        # Draw field with colors
        for i, (_, line) in enumerate(rows):
            try:
                # Draw character by character to apply colors
                for j, char in enumerate(line):
                    if char == '█':
                        # Check if it's center line (at x=40) - make it grey
                        if j == 40:  # center line (W/2)
                            stdscr.addstr(i, j, char, curses.color_pair(1))
                        else:  # paddles and ball - white
                            stdscr.addstr(i, j, char, curses.color_pair(2) | curses.A_BOLD)
                    elif char == '▀':  # top and bottom borders
                        stdscr.addstr(i, j, char, curses.color_pair(1))
                    else:
                        stdscr.addstr(i, j, char)
            except curses.error:
                pass

        # Get scores and ball velocity for sound effects
        a, b, vx = con.execute("SELECT score_a, score_b, vx FROM state").fetchone()

        # Play sound effects if enabled (only up to 120 FPS, not in MAX mode)
        if sound_enabled and not MAX_MODE:
            # Score - flash screen green and pause
            if a != prev_score_a or b != prev_score_b:
                curses.flash()  # Green screen flash
                time.sleep(0.5)  # Pause game for half a second
            # Paddle hit sound - throttled to max 120 Hz to avoid overlap at high FPS
            elif vx * prev_vx < 0:  # Sign changed = ball bounced off paddle
                current_time = time.time()
                if (current_time - last_paddle_beep_time) >= MIN_PADDLE_BEEP_INTERVAL:
                    play_beep()  # Simple beep for paddle hit
                    last_paddle_beep_time = current_time

        prev_score_a = a
        prev_score_b = b
        prev_vx = vx

        # Draw large scores in upper area of each player's field
        # Player A (left field): right-aligned near center
        # Player B (right field): left-aligned near center
        # Handle multi-digit scores
        a_str = str(a)
        b_str = str(b)

        # Draw Player A score (right-aligned, ending at x=38, starting at y=1 for classic look)
        x_pos_a = 38 - (len(a_str) * 4 - 1)  # 4 chars per digit (3 width + 1 space)
        for i, digit_char in enumerate(a_str):
            draw_digit(stdscr, int(digit_char), 1, x_pos_a + (i * 4), curses.color_pair(1))

        # Draw Player B score (left-aligned, starting at x=43, y=1 for symmetry and classic look)
        for i, digit_char in enumerate(b_str):
            draw_digit(stdscr, int(digit_char), 1, 43 + (i * 4), curses.color_pair(1))

        # Info text directly below the playing field - DuckPong title in yellow
        info_text = "DuckPong - DuckDB playing Pong against itself (in SQL) - SQL is fun!"
        try:
            stdscr.addstr(25, 0, info_text, curses.color_pair(4))
        except curses.error:
            pass

        # Command line in grey with status values in yellow
        sound_status = "ON" if sound_enabled else "OFF"
        try:
            # Draw text in grey
            stdscr.addstr(26, 0, "Press ESC to exit, S for sound [", curses.color_pair(1))
            # Sound status in yellow
            stdscr.addstr(sound_status, curses.color_pair(4))
            # Continue in grey
            stdscr.addstr("], +/- for framerate [", curses.color_pair(1))
            # FPS in yellow
            if MAX_MODE:
                stdscr.addstr(f"{int(actual_fps)} fps MAX", curses.color_pair(4))
            else:
                stdscr.addstr(f"{FPS} fps", curses.color_pair(4))
            # Close bracket in grey
            stdscr.addstr("]", curses.color_pair(1))
        except curses.error:
            pass

        stdscr.refresh()

        # Calculate actual FPS and pacing
        now = time.time()
        frame_time = now - frame_start
        if frame_time > 0:
            actual_fps = 1.0 / frame_time

        # Apply frame rate limiting (unless in MAX mode)
        if not MAX_MODE:
            sleep_for = frame_dt - (now - last)
            if sleep_for > 0:
                time.sleep(sleep_for)
        last = time.time()

if __name__ == "__main__":
    curses.wrapper(main)