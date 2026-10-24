"""Cells moved from one player into a new window, as handed over between the
two: each as a cell dragged to another player says itself, with the list it
plays from, if it plays from one."""

from pydantic import BaseModel, Field

from gridplayer.models.media_list import MediaList
from gridplayer.models.video import VideoBlockMime


class MovedCell(BaseModel):
    cell: VideoBlockMime
    media_list: MediaList | None = None


class MovedCells(BaseModel):
    cells: list[MovedCell] = Field(default_factory=list)
