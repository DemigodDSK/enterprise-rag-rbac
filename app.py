"""HF Spaces / local entry point. Loads .env, then launches the Gradio app."""
import os
import sys

# Silence ChromaDB anonymous telemetry warnings (no functional impact)
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure src/ is importable both locally and on HF Spaces
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from enterprise_rag.ui import demo

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", show_error=True)
