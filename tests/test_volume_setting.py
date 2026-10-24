"""New videos' volume: chosen from 0 to 100% in the settings, kept as a share
from 0 to 1 as the videos and playlists keep it, and not muted to begin with."""

import pytest

from gridplayer.models.settings_draft import SettingsMode, SetValue
from gridplayer.params.settings_fields.kinds import PercentField
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.params.settings_fields.video import VIDEO_FIELDS
from gridplayer.settings import _default_settings, default_value
from gridplayer.widgets.settings_editors import make_editor
from gridplayer.widgets.settings_form import SettingsForm

VOLUME = "video_defaults/volume"


def test_new_videos_are_heard_at_full_volume_to_begin_with():
    assert _default_settings["video_defaults/muted"] is False
    assert _default_settings[VOLUME] == 1.0


def test_the_volume_is_a_percentage():
    assert isinstance(FIELDS[VOLUME], PercentField)


@pytest.fixture
def editor():
    return make_editor(FIELDS[VOLUME])


@pytest.mark.parametrize(
    ("stored", "shown"),
    [(1.0, 100), (0.35, 35), (0.0, 0), (0.333, 33)],
)
def test_shown_as_a_whole_percentage(editor, stored, shown):
    editor.set_value(stored)

    assert editor.widget.value() == shown
    assert editor.widget.text().replace(" ", "") == f"{shown}%"


@pytest.mark.parametrize(("typed", "kept"), [(35, 0.35), (100, 1.0), (0, 0.0)])
def test_kept_as_a_share(editor, typed, kept):
    editor.widget.setValue(typed)

    assert editor.value() == kept


def test_from_0_to_100(editor):
    editor.widget.setValue(250)
    assert editor.value() == 1.0

    editor.widget.setValue(-5)
    assert editor.value() == 0.0


def test_said_as_a_percentage(editor):
    assert editor.text_of(0.35) == "35%"


def test_a_share_it_cannot_show_exactly_is_kept_until_changed():
    form = SettingsForm(
        VIDEO_FIELDS, reset_to=default_value, mode=SettingsMode.DEFAULTS
    )
    values = {
        spec.settings_key: _default_settings[spec.settings_key] for spec in VIDEO_FIELDS
    }

    form.set_values({**values, VOLUME: 0.333})

    assert form.values()[VOLUME] == 0.33
    assert form.persistence_result()[VOLUME] == SetValue(0.333)

    form.widget(VOLUME).setValue(40)

    assert form.persistence_result()[VOLUME] == SetValue(0.4)
