import argparse
import json
import sys
from pathlib import Path
from sys import stderr
from typing import NoReturn

import pipfile
from colorama import Fore, init

from pipenv_setup import (
    lock_file_parser,
    setup_filler,
    setup_updater,
    pipfile_parser,
    setup_parser,
)

# noinspection Mypy
from pipenv_setup.setup_updater import blacken


def print_help():
    print("Commands:")
    print("  " + Fore.GREEN + "sync" + Fore.RESET + "\t\tsync pipfile with setup.py")
    print(
        "  "
        + Fore.BLUE
        + "check"
        + Fore.RESET
        + "\t\tcheck whether Pipfile is consistent with setup.py.\n  \t\tNone zero exit code if there is inconsistency\n  \t\t(package missing; version incompatible)"
    )


def cmd():
    init()
    parser = argparse.ArgumentParser(description="sync pipfile with setup.py")

    subparsers = parser.add_subparsers(dest="command_name")

    # subparsers.required = True

    sync_parser = subparsers.add_parser(
        "sync", help="sync dependencies from Pipfile.lock to setup.py"
    )

    check_parser = subparsers.add_parser(
        "check",
        help="check whether Pipfile is consistent with setup.py. None zero exit code if there is inconsistency (package missing; version incompatible)",
    )

    argv = parser.parse_args()

    if argv.command_name == "sync":
        sync()
    elif argv.command_name == "check":
        check()
    else:
        print_help()


def fatal_error(msg: str) -> NoReturn:
    """
    print red text then exit with error code 1
    """
    print(Fore.RED + msg + Fore.RESET, file=stderr)

    sys.exit(1)


def warn(msg: str):
    print(Fore.YELLOW + "Warning: " + msg + Fore.RESET, file=stderr)


def check():
    if not Path("Pipfile").exists():
        fatal_error("Pipfile not found")
    if not Path("setup.py").exists():
        fatal_error("setup.py not found")

    parsed_pipfile = pipfile.load(Path("Pipfile"))
    local_packages, remote_packages = pipfile_parser.get_default_packages(
        parsed_pipfile
    )

    if local_packages:
        package_names = ", ".join(local_packages)
        fatal_error(
            "local package found in default dependency: %s.\nDo you mean to make it dev dependency?"
            % package_names
        )

    with open("setup.py") as setup_file:
        setup_code = setup_file.read()
    try:
        install_requires, dependency_links = setup_parser.get_install_requires_dependency_links(
            setup_code
        )
    except ValueError as e:
        fatal_error(str(e))

    # fatal_error is a NoReturn function, pycharm gets confused
    # noinspection PyUnboundLocalVariable
    for install_requires_element in install_requires:
        pass

    for package, package_config in remote_packages.items():
        pass


def sync():

    pipfile_path, lock_file_path, setup_file_path = required_files = [
        Path("Pipfile"),
        Path("Pipfile.lock"),
        Path("setup.py"),
    ]

    # found_files = tuple(filter(Path.exists, required_files))
    missing_files = tuple(filter(lambda x: not x.exists(), required_files))
    only_setup_missing = len(missing_files) == 1 and not setup_file_path.exists()

    if not missing_files or only_setup_missing:
        dependency_arguments = {"dependency_links": [], "install_requires": []}
        with open(lock_file_path) as lock_file:
            lock_file_data = json.load(lock_file)
        local_packages, remote_packages = lock_file_parser.get_default_packages(
            lock_file_data
        )
        for local_package in local_packages:
            print("package %s is local, omitted in setup.py" % local_package)

        success_count = 0
        for remote_package_name, remote_package_config in remote_packages.items():
            try:
                destination_kw, value = lock_file_parser.format_remote_package(
                    remote_package_name, remote_package_config
                )
            except ValueError as e:
                print(e, file=stderr)
                print(
                    "package %s is not synced to setup.py" % remote_package_name,
                    file=stderr,
                )
                sys.exit(1)
            else:
                success_count += 1
                dependency_arguments[destination_kw].append(value)
        if only_setup_missing:
            print("setup.py not found under current directory")
            print("Creating boilerplate setup.py...")
            setup_code = setup_filler.fill_boilerplate(dependency_arguments)
            if setup_code is None:
                print("Can not find read setup.py template file", file=stderr)
                sys.exit(1)
            try:
                with open(setup_file_path, "w") as new_setup_file:
                    new_setup_file.write(setup_code)
                blacken(str(setup_file_path))
            except OSError as e:
                print(e, file=stderr)
                print("failed to write setup.py file", file=stderr)
                sys.exit(1)
            else:
                print("setup.py successfully generated under current directory")
                print("%d packages moved from Pipfile.lock to setup.py" % success_count)
                print("Please edit the required fields in the generated file")

        else:  # all files exist. Update setup.py
            setup_updater.update_setup(dependency_arguments, setup_file_path)
            print("setup.py successfully updated")
            print("%d packages from Pipfile.lock synced to setup.py" % success_count)

    else:
        for file in missing_files:
            print("%s not found under current directory" % file, file=stderr)
        print("can not perform sync", file=stderr)
        sys.exit(1)