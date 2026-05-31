from __future__ import annotations

from ..file_manager import FileManager


def build_run_archive(file_manager: FileManager, run_name: str):
    return file_manager.make_run_zip(run_name)
