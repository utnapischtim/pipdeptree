from typing import Dict, Type, Any
from pip._internal.operations.freeze import FrozenRequirement


def frozen_req_from_dist(dist):
    try:
        return FrozenRequirement.from_dist(dist)
    except TypeError:
        return FrozenRequirement.from_dist(dist, [])


class Package(object):
    """Abstract class for wrappers around objects that pip returns.

    This class needs to be subclassed with implementations for
    `render_as_root` and `render_as_branch` methods.

    """

    def __init__(self, obj: Dict[Any, Any]) -> None:
        self._obj = obj
        self.project_name = obj.project_name
        self.key = obj.key

    def render_as_root(self, frozen: bool) -> Type[NotImplementedError]:
        return NotImplementedError

    def render_as_branch(self, frozen: bool) -> Type[NotImplementedError]:
        return NotImplementedError

    def render(self, parent=None, frozen: bool = False) -> str:
        if not parent:
            return self.render_as_root(frozen)
        else:
            return self.render_as_branch(frozen)

    @staticmethod
    def frozen_repr(obj) -> str:
        fr = frozen_req_from_dist(obj)
        return str(fr).strip()

    def __getattr__(self, key) -> str:
        return getattr(self._obj, key)

    def __repr__(self) -> str:
        return '<{0}("{1}")>'.format(self.__class__.__name__, self.key)
