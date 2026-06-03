"""Voice-command parsing (discord-free, testable). A transcript only becomes a command
if it starts with the wake word, keeping voice control to a small, intentional surface."""


def parse_voice_command(transcript: str, wake: str = "nito"):
    """-> (command, args) if the transcript is wake-worded, else None."""
    parts = transcript.strip().lower().split()
    if len(parts) < 2 or parts[0] != wake:
        return None
    return parts[1], " ".join(parts[2:])
