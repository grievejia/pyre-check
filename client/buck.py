# Copyright 2004-present Facebook.  All rights reserved.

import glob
import logging
import os
import subprocess
import sys
from collections import namedtuple
from typing import Dict, Iterable, List, cast  # noqa

from . import log
from .filesystem import find_root


LOG = logging.getLogger(__name__)
CACHE_PATH = ".pyre/buckcache.json"

BuckOut = namedtuple("BuckOut", "source_directories targets_not_found")


class BuckException(Exception):
    pass


def presumed_target_root(target):
    root_index = target.find("//")
    if root_index != -1:
        target = target[root_index + 2 :]
    target = target.replace("/...", "")
    target = target.split(":")[0]
    return target


# Expects the targets to be already normalized.
def _find_built_source_directories(targets: Iterable[str]) -> BuckOut:
    targets_not_found = []
    source_directories = []
    buck_root = find_root(os.getcwd(), ".buckconfig")
    if buck_root is None:
        raise Exception("No .buckconfig found in ancestors of the current directory.")

    targets = sorted(targets)
    for target in targets:
        target_path = target
        target_prefix_index = target_path.find("//")
        if target_prefix_index != -1:
            target_path = target_path[target_prefix_index + 2 :]
        target_path = target_path.replace(":", "/")
        discovered_source_directories = glob.glob(
            os.path.join(buck_root, "buck-out/gen/", target_path + "#*link-tree")
        )
        if len(discovered_source_directories) == 0:
            targets_not_found.append(target)
        source_directories.extend(
            [
                tree
                for tree in discovered_source_directories
                if not tree.endswith(
                    (
                        "-vs_debugger#link-tree",
                        "-interp#link-tree",
                        "-ipython#link-tree",
                    )
                )
            ]
        )
    return BuckOut(source_directories, targets_not_found)


def _normalize(targets: List[str]) -> List[str]:
    LOG.info(
        "Normalizing target%s `%s`",
        "s:" if len(targets) > 1 else "",
        "`, `".join(targets),
    )
    try:
        command = (
            ["buck", "targets", "--show-output"]
            + targets
            + ["--type", "python_binary", "python_test"]
        )
        targets_to_destinations = (
            subprocess.check_output(command, stderr=subprocess.PIPE, timeout=600)
            .decode()
            .strip()
            .split("\n")
        )
        targets_to_destinations = cast(
            List[str], list(filter(bool, targets_to_destinations))
        )
        # The output is of the form //target //corresponding.par
        targets_to_destinations = [
            target.split(" ")[0] for target in targets_to_destinations
        ]
        if not targets_to_destinations:
            LOG.warning(
                "Provided targets do not contain any binary or unittest targets."
            )
            return []
        else:
            LOG.info(
                "Found %d buck target%s.",
                len(targets_to_destinations),
                "s" if len(targets_to_destinations) > 1 else "",
            )
        return targets_to_destinations
    except subprocess.TimeoutExpired as error:
        LOG.error("Buck output so far: %s", error.stderr.decode().strip())
        raise BuckException(
            "Seems like `{}` is hanging.\n   "
            "Try running `buck clean` before trying again.".format(
                # pyre-fixme: command not always defined
                " ".join(command[:-1])
            )
        )
    except subprocess.CalledProcessError as error:
        LOG.error("Buck returned error: %s" % error.stderr.decode().strip())
        raise BuckException(
            "Could not normalize targets. Check the paths or run `buck clean`."
        )


def _build_targets(targets: List[str], original_targets: List[str]) -> None:
    LOG.info(
        "Building target%s `%s`",
        "s:" if len(original_targets) > 1 else "",
        "`, `".join(original_targets),
    )
    command = ["buck", "build"] + targets
    try:
        subprocess.check_output(command, stderr=subprocess.PIPE)
        LOG.warning("Finished building targets.")
    except subprocess.CalledProcessError as error:
        # The output can be overwhelming, hence print only the last 20 lines.
        lines = error.stderr.decode().splitlines()
        LOG.error("Buck returned error: %s" % "\n".join(lines[-20:]))
        raise BuckException(
            "Could not build targets. Check the paths or run `buck clean`."
        )


def _map_normalized_targets_to_original(
    unbuilt_targets: Iterable[str], original_targets: Iterable[str]
) -> List[str]:
    mapped_targets = set()
    for target in unbuilt_targets:
        # Each original target is either a `/...` glob or a proper target.
        # If it's a glob, we're looking for the glob to be a prefix of the unbuilt
        # target. Otherwise, we care about exact matches.
        name = None
        for original in original_targets:
            if original.endswith("/..."):
                if target.startswith(original[:-4]):
                    name = original
            else:
                if target == original:
                    name = original
        # No original target matched, fallback to normalized.
        if name is None:
            name = target
        mapped_targets.add(name)
    return list(mapped_targets)


def generate_source_directories(
    original_targets: Iterable[str], build: bool, prompt: bool = True
):
    original_targets = list(original_targets)
    targets = _normalize(original_targets)
    if build:
        _build_targets(targets, original_targets)
    buck_out = _find_built_source_directories(targets)
    source_directories = buck_out.source_directories

    if buck_out.targets_not_found:
        if (not build) and not prompt or log.get_yes_no_input("Build target?"):
            # Build all targets to ensure buck doesn't remove some link trees as we go.
            _build_targets(targets, original_targets)
            buck_out = _find_built_source_directories(targets)
            source_directories = buck_out.source_directories

    if buck_out.targets_not_found:
        message_targets = _map_normalized_targets_to_original(
            buck_out.targets_not_found, original_targets
        )

        raise BuckException(
            "Could not find link trees for:\n    `{}`.\n   "
            "See `{} --help` for more information.".format(
                "    \n".join(message_targets), sys.argv[0]
            )
        )

    return source_directories
