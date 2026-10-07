from typing import get_args

import pytest

from mixtapematrix.cache import TAG_FIELDS, TAG_INDEX, TagField
from mixtapematrix.config import Mp3Match


def test_tag_fields_derive_from_the_literal():
    assert get_args(TagField) == TAG_FIELDS


@pytest.mark.parametrize("name", TAG_FIELDS)
def test_every_tag_field_is_a_str_or_none_field_of_mp3_match(name):
    assert name in Mp3Match.model_fields
    assert Mp3Match.model_fields[name].annotation == (str | None)


def test_tag_index_matches_position():
    assert [TAG_INDEX[name] for name in TAG_FIELDS] == list(range(len(TAG_FIELDS)))
