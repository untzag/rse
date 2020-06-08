"""

Copyright (C) 2020 Vanessa Sochat.

This Source Code Form is subject to the terms of the
Mozilla Public License, v. 2.0. If a copy of the MPL was not distributed
with this file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""

from rse.main import Encyclopedia
from rse.exceptions import DirectoryNotFoundError
import os
import sys
import logging


def main(args, extra):

    bot = logging.getLogger("rse.client")

    # present working directory
    path = args.path
    if args.path == ".":
        path = os.getcwd()

    # directory must exist!
    if not os.path.exists(path):
        raise DirectoryNotFoundError(path)
    config_file = os.path.join(path, args.config_file)

    # generate the software repository in the base
    enc = Encyclopedia(config_file=config_file, generate=True, database=args.database)
