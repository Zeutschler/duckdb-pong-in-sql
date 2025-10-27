# DuckPong - Pong in Pure SQL

**A fully functional Pong game where ALL game logic runs in SQL queries.**

![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)

## What Is This?

DuckPong is a playable Pong game where the entire game engine/physics, AI, collision detection, scoring
is implemented as **a single SQL query** that runs every frame. No Python game logic. Just SQL.

```sql
-- Yes, this actually works!
WITH ai AS (SELECT ...),
     step AS (SELECT ...),
     wall AS (SELECT ...),
     paddle AS (SELECT ...)
UPDATE state SET ...
```

The result? A surprisingly fun retro game that showcases SQL's expressive power in an entirely unconventional way!

## Why Does This Exist?

This project started as a playful challenge: *"Can you build a real-time game using only SQL?"*

It demonstrates:
- **Modern SQL-engine's speed**: Complex queries run at 30-480 FPS
- **SQL's expressiveness**: CTEs elegantly model game state transitions
- **Creative coding**: Sometimes the most interesting projects emerge from constraints

Plus, watching two AI players battle it out in pure SQL is oddly mesmerizing. >�

## Quick Start

### Prerequisites
```bash
pip install duckdb
```

### Run
```bash
python pong.py
```

### Controls
- **ESC**: Quit
- **S**: Toggle sound effects (classic score beeps)
- **+**: Double framerate (30 → 60 → 120 → MAX)
- **-**: Halve framerate (back down to 15 FPS minimum)
- **MAX mode**: Shows actual FPS the SQL engine can deliver (no frame limiting)

## Features

### Classic Pong Physics
The game faithfully recreates original Pong mechanics:
- **5 discrete ball angles** based on paddle hit position
- **Strategic AI** that attempts trick shots when ball is close
- **Authentic feel** with squared-dotted center line and retro scoring

### Pure SQL Implementation
Every frame executes ONE SQL query with multiple CTEs:

```sql
WITH
  -- 1. AI Decision: Where should paddles move?
  ai AS (
    SELECT
      CASE WHEN ball is close THEN attempt_trick_shot()
           ELSE track_defensively() END ...
  ),

  -- 2. Physics: Move ball by velocity
  step AS (SELECT ball_x + vx, ball_y + vy ...),

  -- 3. Collisions: Bounce off walls
  wall AS (SELECT CASE WHEN hit_wall THEN -vy ...),

  -- 4. Paddle Hits: Calculate new angles
  paddle AS (
    SELECT CASE
      WHEN hit_top THEN steep_angle
      WHEN hit_center THEN straight_shot ...
  ),

  -- 5. Scoring: Detect points
  -- 6. Update: Write new state
  ...
```

### Smart AI Players
The AI mimics human behavior:
- **Defensive tracking** when ball is far away
- **Trick shots** when ball is within 4-5 pixels
- **Imperfect timing** (92% accuracy) for realistic gameplay
- **Strategic angles**: Attempts steeps, diagonals, and rare straight shots

## =
 Code Highlights

### The Magic: Paddle Hit Zones

One of the coolest parts is how ball angles are calculated based on WHERE the ball hits the paddle:

```sql
-- Divide 7-unit paddle into 5 zones for different angles
CASE
  WHEN hit_position = 0 THEN -2      -- Top: steep up �
  WHEN hit_position <= 2 THEN -1     -- Upper: diagonal up �
  WHEN hit_position <= 4 THEN 0      -- Center: straight �
  WHEN hit_position <= 5 THEN 1      -- Lower: diagonal down �
  ELSE 2                              -- Bottom: steep down �
END AS vy
```

This creates the iconic Pong gameplay where you can "steer" the ball!

### AI That Thinks in SQL

The AI doesn't use traditional if-statements. It uses SQL CASE expressions:

```sql
CASE
  -- Trick shot mode: ball is close!
  WHEN ball_x <= 5 AND vx < 0 THEN
    CASE WHEN random() < 0.25 THEN aim_for_top_edge
         WHEN random() < 0.50 THEN aim_for_upper
         ...
    END
  -- Defensive mode: track the ball
  WHEN random() < 0.92 THEN
    CASE WHEN ball above paddle THEN move_up
         WHEN ball below paddle THEN move_down
    END
END
```

### On-the-Fly Rendering

Even the graphics are generated in SQL! One query creates the entire 80x25 ASCII art frame:

```sql
SELECT y, string_agg(
  CASE
    WHEN is_paddle THEN '�'
    WHEN is_ball THEN '�'
    WHEN is_border THEN '�'
    WHEN is_centerline THEN '�'
    ELSE ' '
  END, ''
) AS line
FROM range(0,25) AS y, range(0,80) AS x
GROUP BY y
```

## Learning Resources

This project is heavily commented for educational purposes. Check out:

- **`pong.py` lines 31-67**: Game state initialization
- **`pong.py` lines 73-205**: The main game loop (all SQL!)
- **`pong.py` lines 210-227**: Pure SQL rendering

Each section has detailed comments explaining not just *what* the code does, but *why* it's structured that way.

## Fun Facts

- **~500 lines** of code (with comments)
- **1 SQL query** runs the entire game each frame
- **6 CTEs** elegantly separate concerns (AI � Physics � Collisions � Scoring)
- **92% AI accuracy** creates balanced gameplay
- **5 ball angles** just like the original Pong (1972)

## Is This Practical?

**Absolutely not!**

But that's not the point. This is:
- A fun exploration of SQL capabilities
- A testament to SQL's versatility beyond traditional data queries
- A conversation starter about creative problem-solving
- Surprisingly playable and entertaining

## Technical Details

**Stack:**
- **SQL**: Game engine implementation (uses DuckDB as the database engine)
- **Python 3.x**: UI wrapper with curses for terminal rendering

**Performance:**
- Runs at 30 FPS by default (configurable: 30 → 60 → 120 → MAX)
- ~33ms per frame at 30 FPS
- Single UPDATE query per frame with 6 CTE steps
- MAX mode shows actual engine performance (typically 200-600+ FPS depending on hardware)

## License

MIT License - Copyright (c) 2025 Thomas Zeutschler

Feel free to fork, modify, and share! If you build something cool with it, let me know!

## Acknowledgments

Inspired by the original Pong (1972) and countless "can you build X in Y" challenges that make programming fun.

Built with DuckDB, a fast and versatile analytical database perfect for this kind of experiment!

---

*"Can it run Pong?" Yes. Yes it can. In SQL.*
