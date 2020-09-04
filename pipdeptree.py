from __future__ import print_function
import os
import sys
from itertools import chain
from collections import defaultdict
import argparse
from operator import attrgetter
import json
from pip._internal.utils.misc import get_installed_distributions

from src.package_dag import PackageDAG


# inline:
# from graphviz import backend, Digraph


__version__ = "2.0.0b1"


flatten = chain.from_iterable


def render_text(tree: PackageDAG, list_all: bool = True, frozen: bool = False) -> None:
    """Print tree as text on console

    :param dict tree: the package tree
    :param bool list_all: whether to list all the pgks at the root
                          level or only those that are the
                          sub-dependencies
    :param bool frozen: whether or not show the names of the pkgs in
                        the output that's favourable to pip --freeze
    :returns: None

    """
    tree = tree.sort()
    nodes = tree.keys()
    branch_keys = set(r.key for r in flatten(tree.values()))
    use_bullets = not frozen

    if not list_all:
        nodes = [p for p in nodes if p.key not in branch_keys]

    def aux(node, parent=None, indent=0, chain=None):
        chain = chain or []
        node_str = node.render(parent, frozen)
        if parent:
            prefix = " " * indent + ("- " if use_bullets else "")
            node_str = prefix + node_str
        result = [node_str]
        children = [
            aux(c, node, indent=indent + 2, chain=chain + [c.project_name])
            for c in tree.get_children(node.key)
            if c.project_name not in chain
        ]
        result += list(flatten(children))
        return result

    lines = flatten([aux(p) for p in nodes])
    print("\n".join(lines))


def render_json(tree, indent) -> json:
    """Converts the tree into a flat json representation.

    The json repr will be a list of hashes, each hash having 2 fields:
      - package
      - dependencies: list of dependencies

    :param dict tree: dependency tree
    :param int indent: no. of spaces to indent json
    :returns: json representation of the tree
    :rtype: str

    """
    return json.dumps(
        [
            {"package": k.as_dict(), "dependencies": [v.as_dict() for v in vs]}
            for k, vs in tree.items()
        ],
        indent=indent,
    )


def render_json_tree(tree, indent) -> json:
    """Converts the tree into a nested json representation.

    The json repr will be a list of hashes, each hash having the following
    fields:
      - package_name
      - key
      - required_version
      - installed_version
      - dependencies: list of dependencies

    :param dict tree: dependency tree
    :param int indent: no. of spaces to indent json
    :returns: json representation of the tree
    :rtype: str

    """
    tree = tree.sort()
    branch_keys = set(r.key for r in flatten(tree.values()))
    nodes = [p for p in tree.keys() if p.key not in branch_keys]

    def aux(node, parent=None, chain=None):
        if chain is None:
            chain = [node.project_name]

        d = node.as_dict()
        node_version_spec = node.version_spec if node.version_spec else "Any"
        d["required_version"] = node_version_spec if parent else d["installed_version"]

        d["dependencies"] = [
            aux(c, parent=node, chain=chain + [c.project_name])
            for c in tree.get_children(node.key)
            if c.project_name not in chain
        ]

        return d

    return json.dumps([aux(p) for p in nodes], indent=indent)


def dump_graphviz(tree, output_format="dot", is_reverse=False):
    """Output dependency graph as one of the supported GraphViz output formats.

    :param dict tree: dependency graph
    :param string output_format: output format
    :returns: representation of tree in the specified output format
    :rtype: str or binary representation depending on the output format

    """
    try:
        from graphviz import backend, Digraph
    except ImportError:
        print(
            "graphviz is not available, but necessary for the output "
            "option. Please install it.",
            file=sys.stderr,
        )
        sys.exit(1)

    if output_format not in backend.FORMATS:
        print(
            "{0} is not a supported output format.".format(output_format),
            file=sys.stderr,
        )
        print(
            "Supported formats are: {0}".format(", ".join(sorted(backend.FORMATS))),
            file=sys.stderr,
        )
        sys.exit(1)

    graph = Digraph(format=output_format)

    if not is_reverse:
        for pkg, deps in tree.items():
            pkg_label = "{0}\n{1}".format(pkg.project_name, pkg.version)
            graph.node(pkg.key, label=pkg_label)
            for dep in deps:
                # edge_label = dep.version_spec or "any"
                if dep.is_missing:
                    dep_label = "{0}\n(missing)".format(dep.project_name)
                    graph.node(dep.key, label=dep_label, style="dashed")
                    graph.edge(pkg.key, dep.key, style="dashed")
                else:
                    # , label=edge_label
                    graph.edge(pkg.key, dep.key)
    else:
        for dep, parents in tree.items():
            dep_label = "{0}\n{1}".format(dep.project_name, dep.installed_version)
            graph.node(dep.key, label=dep_label)
            for parent in parents:
                # req reference of the dep associated with this
                # particular parent package
                # req_ref = parent.req
                # edge_label = req_ref.version_spec or "any"
                # , label=edge_label
                graph.edge(dep.key, parent.key)

    # Allow output of dot format, even if GraphViz isn't installed.
    if output_format == "dot":
        return graph.source

    # As it's unknown if the selected output format is binary or not, try to
    # decode it as UTF8 and only print it out in binary if that's not possible.
    try:
        return graph.pipe().decode("utf-8")
    except UnicodeDecodeError:
        return graph.pipe()


def print_graphviz(dump_output):
    """Dump the data generated by GraphViz to stdout.

    :param dump_output: The output from dump_graphviz
    """
    if hasattr(dump_output, "encode"):
        print(dump_output)
    else:
        with os.fdopen(sys.stdout.fileno(), "wb") as bytestream:
            bytestream.write(dump_output)


def conflicting_deps(tree):
    """Returns dependencies which are not present or conflict with the
    requirements of other packages.

    e.g. will warn if pkg1 requires pkg2==2.0 and pkg2==1.0 is installed

    :param tree: the requirements tree (dict)
    :returns: dict of DistPackage -> list of unsatisfied/unknown ReqPackage
    :rtype: dict

    """
    conflicting = defaultdict(list)
    for p, rs in tree.items():
        for req in rs:
            if req.is_conflicting():
                conflicting[p].append(req)
    return conflicting


def render_conflicts_text(conflicts):
    if conflicts:
        print("Warning!!! Possibly conflicting dependencies found:", file=sys.stderr)
        # Enforce alphabetical order when listing conflicts
        pkgs = sorted(conflicts.keys(), key=attrgetter("key"))
        for p in pkgs:
            pkg = p.render_as_root(False)
            print("* {}".format(pkg), file=sys.stderr)
            for req in conflicts[p]:
                req_str = req.render_as_branch(False)
                print(" - {}".format(req_str), file=sys.stderr)


def cyclic_deps(tree):
    """Return cyclic dependencies as list of tuples

    :param PackageDAG pkgs: package tree/dag
    :returns: list of tuples representing cyclic dependencies
    :rtype: list

    """
    index = {p.key: set([r.key for r in rs]) for p, rs in tree.items()}
    cyclic = []
    for p, rs in tree.items():
        for r in rs:
            if p.key in index.get(r.key, []):
                p_as_dep_of_r = [
                    x
                    for x in tree.get(tree.get_node_as_parent(r.key))
                    if x.key == p.key
                ][0]
                cyclic.append((p, r, p_as_dep_of_r))
    return cyclic


def render_cycles_text(cycles):
    if cycles:
        print("Warning!! Cyclic dependencies found:", file=sys.stderr)
        # List in alphabetical order of the dependency that's cycling
        # (2nd item in the tuple)
        cycles = sorted(cycles, key=lambda xs: xs[1].key)
        for a, b, c in cycles:
            print(
                "* {0} => {1} => {2}".format(
                    a.project_name, b.project_name, c.project_name
                ),
                file=sys.stderr,
            )


def get_parser():
    parser = argparse.ArgumentParser(
        description=("Dependency tree of the installed python packages")
    )
    parser.add_argument(
        "-v", "--version", action="version", version="{0}".format(__version__)
    )
    parser.add_argument(
        "-f",
        "--freeze",
        action="store_true",
        help="Print names so as to write freeze files",
    )
    parser.add_argument(
        "-a", "--all", action="store_true", help="list all deps at top level"
    )
    parser.add_argument(
        "-l",
        "--local-only",
        action="store_true",
        help=(
            "If in a virtualenv that has global access "
            "do not show globally installed packages"
        ),
    )
    parser.add_argument(
        "-u",
        "--user-only",
        action="store_true",
        help=("Only show installations in the user site dir"),
    )
    parser.add_argument(
        "-w",
        "--warn",
        action="store",
        dest="warn",
        nargs="?",
        default="suppress",
        choices=("silence", "suppress", "fail"),
        help=(
            'Warning control. "suppress" will show warnings '
            "but return 0 whether or not they are present. "
            '"silence" will not show warnings at all and '
            'always return 0. "fail" will show warnings and '
            "return 1 if any are present. The default is "
            '"suppress".'
        ),
    )
    parser.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        default=False,
        help=(
            "Shows the dependency tree in the reverse fashion "
            "ie. the sub-dependencies are listed with the "
            "list of packages that need them under them."
        ),
    )
    parser.add_argument(
        "-p",
        "--packages",
        help=(
            "Comma separated list of select packages to show "
            "in the output. If set, --all will be ignored."
        ),
    )
    parser.add_argument(
        "-e",
        "--exclude",
        help=(
            "Comma separated list of select packages to exclude "
            "from the output. If set, --all will be ignored."
        ),
        metavar="PACKAGES",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=False,
        help=(
            "Display dependency tree as json. This will yield "
            '"raw" output that may be used by external tools. '
            "This option overrides all other options."
        ),
    )
    parser.add_argument(
        "--json-tree",
        action="store_true",
        default=False,
        help=(
            "Display dependency tree as json which is nested "
            "the same way as the plain text output printed by default. "
            "This option overrides all other options (except --json)."
        ),
    )
    parser.add_argument(
        "--graph-output",
        dest="output_format",
        help=(
            "Print a dependency graph in the specified output "
            "format. Available are all formats supported by "
            "GraphViz, e.g.: dot, jpeg, pdf, png, svg"
        ),
    )
    return parser


def _get_args():
    parser = get_parser()
    return parser.parse_args()


def main():
    args = _get_args()

    pkgs = get_installed_distributions(
        local_only=args.local_only, user_only=args.user_only
    )

    tree = PackageDAG.from_pkgs(pkgs)

    is_text_output = not any([args.json, args.json_tree, args.output_format])

    return_code = 0

    # Before any reversing or filtering, show warnings to console
    # about possibly conflicting or cyclic deps if found and warnings
    # are enabled (ie. only if output is to be printed to console)
    if is_text_output and args.warn != "silence":
        conflicts = conflicting_deps(tree)
        if conflicts:
            render_conflicts_text(conflicts)
            print("-" * 72, file=sys.stderr)

        cycles = cyclic_deps(tree)
        if cycles:
            render_cycles_text(cycles)
            print("-" * 72, file=sys.stderr)

        if args.warn == "fail" and (conflicts or cycles):
            return_code = 1

    # Reverse the tree (if applicable) before filtering, thus ensuring
    # that the filter will be applied on ReverseTree
    if args.reverse:
        tree = tree.reverse()

    show_only = set(args.packages.split(",")) if args.packages else None
    exclude = set(args.exclude.split(",")) if args.exclude else None

    # if show_only is not None or exclude is not None:
    #     print(show_only)

    tree = tree.filter(show_only, exclude)

    if args.json:
        print(render_json(tree, indent=4))
    elif args.json_tree:
        print(render_json_tree(tree, indent=4))
    elif args.output_format:
        output = dump_graphviz(
            tree, output_format=args.output_format, is_reverse=args.reverse
        )
        print_graphviz(output)
    else:
        render_text(tree, args.all, args.freeze)

    return return_code


if __name__ == "__main__":
    sys.exit(main())
