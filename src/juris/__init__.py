"""juris — Swedish legal data collection tool."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("juris")
except PackageNotFoundError:
    __version__ = "0.0.0"
