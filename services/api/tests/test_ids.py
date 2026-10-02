from app.core.ids import is_uuid7, new_id


def test_new_id_is_uuid7() -> None:
    value = new_id()
    assert is_uuid7(value)
    assert value[14] == "7"


def test_ids_are_unique_and_time_ordered() -> None:
    ids = [new_id() for _ in range(200)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_is_uuid7_rejects_other_versions() -> None:
    import uuid

    assert not is_uuid7(str(uuid.uuid4()))
    assert not is_uuid7("not-a-uuid")
    assert not is_uuid7("")
