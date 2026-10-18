"""Speaker Detection package. Run entry points with ``python -m src.<name>``."""

# Apply native-library environment defaults before any project module loads
# NumPy/OpenCV/scikit-learn. Importing config does not create files or folders.
from src.core import config as config
