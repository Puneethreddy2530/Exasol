import subprocess
import sys
from pathlib import Path

def main():
    agent_dir = Path(__file__).resolve().parent
    print("Building custom Ollama model: exacommand-c4isr")
    try:
        subprocess.run(["ollama", "create", "exacommand-c4isr", "-f", str(agent_dir / "Modelfile")], check=True)
        print("Success!")
    except subprocess.CalledProcessError as e:
        print(f"Failed to build model. Make sure Ollama is installed and running. Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
