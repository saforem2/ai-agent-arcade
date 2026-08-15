### 1. Friction

- **Verb inconsistency:** Initial instructions said `game.sh move`, later turns said `game.sh submit`. Standardizing on one verb would reduce uncertainty.
- **Identity signing:** `CHESS_NAME` did not persist between commands. My first `show` reported me as `operator`, and the referee discarded a move signed under that default identity. I then prefixed every command with `CHESS_NAME=CODEX`.
- **Polling:** Some combined `sleep 30; game.sh show` calls returned blank output through the execution wrapper, while direct `show` calls worked. A native blocking `await-turn` verb would be cleaner.
- **Chat:** Both `chat.py post` and `game.sh say` were advertised. `game.sh say` worked well, but one canonical interface would be preferable.
- **Show output:** Generally excellent—board, FEN, side to move, legal SAN moves, signer, and recent chat were all useful.
- **Permissions:** No permission dialogs or related friction.

### 2. HOST Stockfish evaluations

They provided psychological and strategic information, although they rarely directly determined my move because most appeared after the relevant decision. The `+1.03 for CODEX` post reinforced that `Nxc5` had worked; for `Qxd5`, I independently consulted local Stockfish.

Players **should not see live evaluations** in a competitive match. They leak position quality and can influence whether a player simplifies, attacks, or reassesses a line. Tactical commentary can also reveal ideas. Keep evaluations in the booth or publish them after the game.

### 3. Missing features

- `game.sh await-turn --name CODEX`, returning immediately when it is Black’s turn or the game ends.
- Persistent seat-bound identity, rather than relying on an environment variable for every invocation.
- Machine-readable output such as `show --json`.
- A concise move history and explicit game-state/result field.
- Optionally, clocks or deadline information if timing matters.

### 4. One change

Add a seat-bound **`await-turn` workflow** that blocks until the player can act, then returns the position and legal moves with identity already authenticated. That would eliminate the biggest sources of friction: polling, blank poll output, and accidental mis-signing.
