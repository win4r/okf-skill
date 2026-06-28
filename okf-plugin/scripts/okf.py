#!/usr/bin/env python3
"""okf — a single, zero-dependency CLI for the Open Knowledge Format toolchain.

    okf validate <bundle>     Check OKF v0.1 conformance (errors) + lint (warnings)
    okf new bundle <path>     Scaffold a new bundle
    okf new concept <id> ...  Scaffold a new concept document
    okf index <bundle>        Generate / refresh index.md files
    okf context <bundle> <q>  Progressive-disclosure context pack (only relevant concepts)
    okf graph <bundle>        Render the link graph (html | json | mermaid)
    okf migrate <dir>         Convert Markdown / wiki notes into an OKF bundle

Run `okf <command> --help` for command-specific options.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import okf_validate
import okf_new
import okf_index
import okf_graph
import okf_context
import okf_migrate

COMMANDS = {
    "validate": okf_validate,
    "new": okf_new,
    "index": okf_index,
    "graph": okf_graph,
    "context": okf_context,
    "migrate": okf_migrate,
}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version="okf-tool 0.1 (OKF v0.1)")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, module in COMMANDS.items():
        sp = sub.add_parser(name, help=(module.__doc__ or "").strip().split("\n")[0])
        module.add_arguments(sp)
        sp.set_defaults(_module=module)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args._module.run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        print(f"okf {args.command}: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
