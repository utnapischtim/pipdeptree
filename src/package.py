from typing import Type, TypedDict, Any
from pip._internal.operations.freeze import FrozenRequirement


class PackageType(TypedDict):
    key: str
    project_name: str
    package_name: str
    installed_version: str


def frozen_req_from_dist(dist: str) -> FrozenRequirement:
    try:
        return FrozenRequirement.from_dist(dist)
    except TypeError:
        return FrozenRequirement.from_dist(dist, [])


class Package(object):
    """Abstract class for wrappers around objects that pip returns.

    This class needs to be subclassed with implementations for
    `render_as_root` and `render_as_branch` methods.

    """

    def __init__(self, obj: PackageType) -> None:
        self._obj = obj
        self.project_name = obj.get("project_name")
        self.key = obj.get("key")

    def render_as_root(self, frozen: bool) -> Type[NotImplementedError]:
        return NotImplementedError

    def render_as_branch(self, frozen: bool) -> Type[NotImplementedError]:
        return NotImplementedError

    def render(self, parent: str = None, frozen: bool = False) -> Type[NotImplementedError]:
        if parent:
            return self.render_as_branch(frozen)
        else:
            return self.render_as_root(frozen)

    @staticmethod
    def frozen_repr(obj: str) -> str:
        fr = frozen_req_from_dist(obj)
        return str(fr).strip()

    def __getattr__(self, key: str) -> Any:
        return getattr(self._obj, key)

    def __repr__(self) -> str:
        return '<{0}("{1}")>'.format(self.__class__.__name__, self.key)
