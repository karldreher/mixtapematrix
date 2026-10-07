from typing import get_args

import pytest
from helpers import make_mp3, write_config

from mixtapematrix.cache import TAG_FIELDS, TagField, tag_index
from mixtapematrix.config import Mp3Match
from mixtapematrix.main import MixtapeMatrix
from mixtapematrix.routers.mp3_router import _tag_matches


def test_tag_fields_derive_from_the_literal():
    assert get_args(TagField) == TAG_FIELDS


@pytest.mark.parametrize("name", TAG_FIELDS)
def test_every_tag_field_is_a_str_or_none_field_of_mp3_match(name):
    assert name in Mp3Match.model_fields
    assert Mp3Match.model_fields[name].annotation == (str | None)


def assert_names_key_and_choices(error):
    message = str(error.value)
    assert "'bogus'" in message
    assert all(name in message for name in TAG_FIELDS)


def test_tag_index_matches_position():
    assert [tag_index(name) for name in TAG_FIELDS] == list(range(len(TAG_FIELDS)))


def test_tag_matches_rejects_unknown_tag():
    with pytest.raises(ValueError) as error:
        _tag_matches(("a", None, None, None), "bogus", "x")
    assert_names_key_and_choices(error)


def test_list_tag_rejects_unknown_tag(tmp_path):
    root = tmp_path / "library"
    make_mp3(root / "one.mp3", artist="Alpha")
    matrix = MixtapeMatrix(str(write_config(tmp_path, [root])))
    with pytest.raises(ValueError) as error:
        matrix.list_tag("bogus")
    assert_names_key_and_choices(error)


def test_entries_reject_unknown_tag_even_with_no_files(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    matrix = MixtapeMatrix(str(write_config(tmp_path, [root])))
    with pytest.raises(ValueError) as error:
        list(matrix._entries([("bogus", "x")]))
    assert_names_key_and_choices(error)
