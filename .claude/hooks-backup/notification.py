#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import json
import sys
import subprocess
import random
import os
import platform

def announce_notification():
    """Announce notification using system-appropriate TTS command."""
    try:
        # Get engineer name if available
        engineer_name = os.getenv('ENGINEER_NAME', '').strip()

        # Create notification message with 30% chance to include name
        if engineer_name and random.random() < 0.3:
            message = f"{engineer_name}, your agent needs your input"
        else:
            message = "Your agent needs your input"

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
        
        # Only announce for specific notification types (not generic waiting)
        message = input_data.get('message', '')
        if message != 'Claude is waiting for your input':
            announce_notification()
        
        sys.exit(0)
        
    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)

if __name__ == '__main__':
    main()