import pytest

from users.serializers import RolesSerializer


def test_roles_serializer_create_is_read_only():
    serializer = RolesSerializer()
    with pytest.raises(NotImplementedError):
        serializer.create({})


def test_roles_serializer_update_is_read_only():
    serializer = RolesSerializer()
    with pytest.raises(NotImplementedError):
        serializer.update({}, {})
