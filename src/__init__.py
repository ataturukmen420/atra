"""ATA Game Translator package: one coordinate unit per physical screen pixel."""
import os

# Also apply to direct module imports, previews and test entrypoints.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
os.environ.setdefault("QT_SCALE_FACTOR", "1")
