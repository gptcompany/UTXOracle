#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import json
import sys
import subprocess
import random
import platform

def get_completion_messages():
    """Return list of friendly completion messages."""
    return [
        "Work complete!",
        "All done!", 
        "Task finished!",
        "Job complete!",
        "Ready for next task!",
        "Mission accomplished!",
        "Work session ended!"
    ]

def announce_completion():
    """Announce completion using system-appropriate TTS command."""
    try:
        # Get a random completion message
        messages = get_completion_messages()
        message = random.choice(messages)

        # Use system-appropriate TTS command
        system = platform.system().lower()
        if system == "darwin":  # macOS
            subprocess.run([
                "say", "-v", "Samantha", message
            ],
            capture_output=True,  # Suppress output
            timeout=10  # 10-second timeout
            )
        elif system == "linux":  # Linux (Ubuntu, etc.)
            subprocess.run([
                "spd-say", "-t", "female1", message
            ],
            capture_output=True,  # Suppress output
            timeout=10  # 10-second timeout
            )
        
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        # Fail silently if say command encounters issues
        pass
    except Exception:
        # Fail silently for any other errors
        pass

def main():
    try:
        # Read JSON input from stdin
        input_data = json.loads(sys.stdin.read())
        
        # Announce completion
        announce_completion()
        
        sys.exit(0)
        
    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)

if __name__ == '__main__':
    main()