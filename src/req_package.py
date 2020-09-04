from pip._vendor import pkg_resources
from importlib import import_module
from typing import Optional

from .package import Package


def guess_version(pkg_key: str, default: str = "?") -> str:
    """Guess the version of a pkg when pip doesn't provide it

    :param str pkg_key: key of the package
    :param str default: default version to return if unable to find
    :returns: version
    :rtype: string

    """
    try:
        m = import_module(pkg_key)
    except ImportError:
        return default
    else:
        return getattr(m, "__version__", default)


class ReqPackage(Package):
    """Wrapper class for Requirements instance

    :param obj: The `Requirements` instance to wrap over
    :param dist: optional `pkg_resources.Distribution` instance for
                 this requirement
    """

    UNKNOWN_VERSION = "?"

    def __init__(self, obj, dist=None) -> None:
        super(ReqPackage, self).__init__(obj)
        self.dist = dist

    @property
    def version_spec(self) -> Optional[str]:
        specs = sorted(
            self._obj.specs, reverse=True
        )  # `reverse` makes '>' prior to '<'
        return ",".join(["".join(sp) for sp in specs]) if specs else None

    @property
    def installed_version(self) -> str:
        if not self.dist:
            return guess_version(self.key, self.UNKNOWN_VERSION)
        return self.dist.version

    @property
    def is_missing(self) -> bool:
        return self.installed_version == self.UNKNOWN_VERSION

    def is_conflicting(self) -> bool:
        """If installed version conflicts with required version"""
        # unknown installed version is also considered conflicting
        if self.installed_version == self.UNKNOWN_VERSION:
            return True
        ver_spec = self.version_spec if self.version_spec else ""
        req_version_str = "{0}{1}".format(self.project_name, ver_spec)
        req_obj = pkg_resources.Requirement.parse(req_version_str)
        return self.installed_version not in req_obj

    def render_as_root(self, frozen: bool) -> str:
        if not frozen:
            return "{0}=={1}".format(self.project_name, self.installed_version)
        elif self.dist:
            return self.__class__.frozen_repr(self.dist._obj)
        else:
            return self.project_name

    def render_as_branch(self, frozen: bool) -> str:
        if not frozen:
            req_ver = self.version_spec if self.version_spec else "Any"
            return ("{0} [required: {1}, installed: {2}]").format(
                self.project_name, req_ver, self.installed_version
            )
        else:
            return self.render_as_root(frozen)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "package_name": self.project_name,
            "installed_version": self.installed_version,
            "required_version": self.version_spec,
        }
