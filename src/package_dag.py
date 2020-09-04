from itertools import chain
from collections import defaultdict, deque, Mapping, OrderedDict
from operator import attrgetter

from .dist_package import DistPackage
from .req_package import ReqPackage

flatten = chain.from_iterable


class PackageDAG(Mapping):
    """Representation of Package dependencies as directed acyclic graph
    using a dict (Mapping) as the underlying datastructure.

    The nodes and their relationships (edges) are internally
    stored using a map as follows,

    {a: [b, c],
     b: [d],
     c: [d, e],
     d: [e],
     e: [],
     f: [b],
     g: [e, f]}

    Here, node `a` has 2 children nodes `b` and `c`. Consider edge
    direction from `a` -> `b` and `a` -> `c` respectively.

    A node is expected to be an instance of a subclass of
    `Package`. The keys are must be of class `DistPackage` and each
    item in values must be of class `ReqPackage`. (See also
    ReversedPackageDAG where the key and value types are
    interchanged).

    """

    @classmethod
    def from_pkgs(cls, pkgs):
        pkgs = [DistPackage(p) for p in pkgs]
        idx = {p.key: p for p in pkgs}
        m = {p: [ReqPackage(r, idx.get(r.key)) for r in p.requires()] for p in pkgs}
        return cls(m)

    def __init__(self, m) -> None:
        """Initialize the PackageDAG object

        :param dict m: dict of node objects (refer class docstring)
        :returns: None
        :rtype: NoneType

        """
        self._obj = m
        self._index = {p.key: p for p in list(self._obj)}

    def get_node_as_parent(self, node_key: str):
        """Get the node from the keys of the dict representing the DAG.

        This method is useful if the dict representing the DAG
        contains different kind of objects in keys and values. Use
        this method to lookup a node obj as a parent (from the keys of
        the dict) given a node key.

        :param node_key: identifier corresponding to key attr of node obj
        :returns: node obj (as present in the keys of the dict)
        :rtype: Object

        """
        try:
            return self._index[node_key]
        except KeyError:
            return None

    def get_children(self, node_key: str) -> ReqPackage:
        """Get child nodes for a node by it's key

        :param str node_key: key of the node to get children of
        :returns: list of child nodes
        :rtype: ReqPackage[]

        """
        node = self.get_node_as_parent(node_key)
        return self._obj[node] if node else []

    def filter(self, include, exclude):
        """Filters nodes in a graph by given parameters

        If a node is included, then all it's children are also
        included.

        :param set include: set of node keys to include (or None)
        :param set exclude: set of node keys to exclude (or None)
        :returns: filtered version of the graph
        :rtype: PackageDAG

        """
        # If neither of the filters are specified, short circuit
        if include is None and exclude is None:
            return self

        # Note: In following comparisons, we use lower cased values so
        # that user may specify `key` or `project_name`. As per the
        # documentation, `key` is simply
        # `project_name.lower()`. Refer:
        # https://setuptools.readthedocs.io/en/latest/pkg_resources.html#distribution-objects
        if include:
            include = set([s.lower() for s in include])
        if exclude:
            exclude = set([s.lower() for s in exclude])
        else:
            exclude = set([])

        # Check for mutual exclusion of show_only and exclude sets
        # after normalizing the values to lowercase
        if include and exclude:
            assert not (include & exclude)

        # Traverse the graph in a depth first manner and filter the
        # nodes according to `show_only` and `exclude` sets
        stack: deque = deque()
        m: set = {}
        seen = set([])
        for node in self._obj.keys():
            if node.key in exclude:
                continue
            if include is None or node.key in include:
                stack.append(node)
            while True:
                if len(stack) > 0:
                    n = stack.pop()
                    cldn = [c for c in self._obj[n] if c.key not in exclude]
                    m[n] = cldn
                    seen.add(n.key)
                    for c in cldn:
                        if c.key not in seen:
                            cld_node = self.get_node_as_parent(c.key)
                            if cld_node:
                                stack.append(cld_node)
                            else:
                                # It means there's no root node
                                # corresponding to the child node
                                # ie. a dependency is missing
                                continue
                else:
                    break

        return self.__class__(m)

    def reverse(self):
        """Reverse the DAG, or turn it upside-down

        In other words, the directions of edges of the nodes in the
        DAG will be reversed.

        Note that this function purely works on the nodes in the
        graph. This implies that to perform a combination of filtering
        and reversing, the order in which `filter` and `reverse`
        methods should be applied is important. For eg. if reverse is
        called on a filtered graph, then only the filtered nodes and
        it's children will be considered when reversing. On the other
        hand, if filter is called on reversed DAG, then the definition
        of "child" nodes is as per the reversed DAG.

        :returns: DAG in the reversed form
        :rtype: ReversedPackageDAG

        """
        m = defaultdict(list)
        child_keys = set(r.key for r in flatten(self._obj.values()))
        for k, vs in self._obj.items():
            for v in vs:
                # if v is already added to the dict, then ensure that
                # we are using the same object. This check is required
                # as we're using array mutation
                try:
                    node = [p for p in m.keys() if p.key == v.key][0]
                except IndexError:
                    node = v
                m[node].append(k.as_parent_of(v))
            if k.key not in child_keys:
                m[k.as_requirement()] = []
        return ReversedPackageDAG(dict(m))

    def sort(self):
        """Return sorted tree in which the underlying _obj dict is an
        OrderedDict, sorted alphabetically by the keys

        :returns: Instance of same class with OrderedDict

        """
        return self.__class__(sorted_tree(self._obj))

    # Methods required by the abstract base class Mapping
    def __getitem__(self, *args):
        return self._obj.get(*args)

    def __iter__(self):
        return self._obj.__iter__()

    def __len__(self):
        return len(self._obj)


class ReversedPackageDAG(PackageDAG):
    """Representation of Package dependencies in the reverse
    order.

    Similar to it's super class `PackageDAG`, the underlying
    datastructure is a dict, but here the keys are expected to be of
    type `ReqPackage` and each item in the values of type
    `DistPackage`.

    Typically, this object will be obtained by calling
    `PackageDAG.reverse`.

    """

    def reverse(self) -> PackageDAG:
        """Reverse the already reversed DAG to get the PackageDAG again

        :returns: reverse of the reversed DAG
        :rtype: PackageDAG

        """
        m: dict = defaultdict(list)
        child_keys = set(r.key for r in flatten(self._obj.values()))
        for k, vs in self._obj.items():
            for v in vs:
                try:
                    node = [p for p in m.keys() if p.key == v.key][0]
                except IndexError:
                    node = v.as_parent_of(None)
                m[node].append(k)
            if k.key not in child_keys:
                m[k.dist] = []
        return PackageDAG(dict(m))


def sorted_tree(tree: PackageDAG) -> OrderedDict:
    """Sorts the dict representation of the tree

    The root packages as well as the intermediate packages are sorted
    in the alphabetical order of the package names.

    :param dict tree: the pkg dependency tree obtained by calling
                     `construct_tree` function
    :returns: sorted tree
    :rtype: collections.OrderedDict

    """
    return OrderedDict(
        sorted(
            [(k, sorted(v, key=attrgetter("key"))) for k, v in tree.items()],
            key=lambda kv: kv[0].key,
        )
    )
