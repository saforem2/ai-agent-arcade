# Record the live Textual TUI running the canonical dot renderer.
# Usage: vhs docs/arcade-tui.tape   (from the repo root)

Output docs/assets/arcade-tui.gif

Require uv

Set Shell "bash"
Set FontFamily "JetBrains Mono"
Set FontSize 13
Set Width 1800
Set Height 1000
Set Padding 12
Set Theme "Catppuccin Mocha"
Set Framerate 24
Set PlaybackSpeed 1.0

Hide
Type "cd /Users/sam/projects/saforem2/arcade && clear" Enter
Sleep 1s
Show

Type "uv run ai-agent-arcade --view --live-dir games/chess/match-009"
Sleep 500ms
Enter
Sleep 6s

# Replay the archived game so the fly/wake/debris animation runs on screen.
Type "r"
Sleep 14s

# Show the compact board style, then return to the original renderer.
Type "b"
Sleep 3s
Type "b"
Sleep 2s

Type "q"
Sleep 2s
