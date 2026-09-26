import sys
from pathlib import Path

# The reader is a plain package directory, not an installed distribution: the page loads the same
# files into Pyodide.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
