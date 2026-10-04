import base64

import pytest

from app.services.skilifts import (
    RANKING_TOKEN_KEYS,
    TABLE_TOKEN_KEYS,
    InvalidToken,
    decode_token,
    encode_token,
    path_date_to_metadata,
)


def test_path_date_becomes_the_stored_sort_key():
    assert path_date_to_metadata("01-01-20") == "01/01/20"


def test_token_is_canonical_unpadded_base64url():
    token = encode_token({"Metadata": "01/01/20", "Lift": "Lift 3"})
    assert "=" not in token
    padded = token + "=" * (-len(token) % 4)
    assert (
        base64.urlsafe_b64decode(padded) == b'{"Lift":"Lift 3","Metadata":"01/01/20"}'
    )


def test_decode_table_token_round_trips():
    token = encode_token({"Lift": "Lift 3", "Metadata": "01/01/20"})
    assert decode_token(token, expected_keys=TABLE_TOKEN_KEYS, lift="Lift 3") == {
        "Lift": "Lift 3",
        "Metadata": "01/01/20",
    }


def test_decode_rejects_wrong_shape():
    table_token = encode_token({"Lift": "Lift 3", "Metadata": "01/01/20"})
    ranking_token = encode_token(
        {"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": 5000}
    )
    other_lift = encode_token({"Lift": "Lift 10", "Metadata": "01/01/20"})
    for token, keys, lift in (
        ("%%%", TABLE_TOKEN_KEYS, "Lift 3"),
        (ranking_token, TABLE_TOKEN_KEYS, "Lift 3"),
        (table_token, RANKING_TOKEN_KEYS, "Lift 3"),
        (other_lift, TABLE_TOKEN_KEYS, "Lift 3"),
    ):
        with pytest.raises(InvalidToken) as caught:
            decode_token(token, expected_keys=keys, lift=lift)
        assert str(caught.value) == "Invalid nextToken"
        assert caught.value.detail == "Invalid nextToken"
    boolean_riders = encode_token(
        {"Lift": "Lift 3", "Metadata": "01/01/20", "TotalUniqueLiftRiders": True}
    )
    with pytest.raises(InvalidToken):
        decode_token(boolean_riders, expected_keys=RANKING_TOKEN_KEYS, lift="Lift 3")
