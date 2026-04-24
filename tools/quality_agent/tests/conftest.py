import sys
import os

# Make the quality_agent package importable from tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# quality_agent scripts import from translation_agent (config, translator, etc.)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "translation_agent"))
