"""

Copyright (C) 2020 Vanessa Sochat.

This Source Code Form is subject to the terms of the
Mozilla Public License, v. 2.0. If a copy of the MPL was not distributed
with this file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""

from rse.exceptions import (
    DirectoryNotFoundError,
    MultipleReposExistError,
    RepoNotFoundError,
    NoReposError,
)
from rse.utils.file import (
    write_json,
    mkdir_p,
    read_json,
    recursive_find,
    get_latest_modified,
)
from rse.main.database.base import Database
from rse.main.parsers import get_parser
from glob import glob
import logging
import shutil
import os
import re

bot = logging.getLogger("rse.main.database.filesystem")


class FileSystemDatabase(Database):
    """A FileSystemDatabase writes raw json to files to a database.
    """

    database = "filesystem"

    def __init__(self, config_dir, config=None, **kwargs):
        """init for the filesystem ensures that the base folder (named 
           according to the studyid) exists.
        """
        self.config = config
        self.create_database(config_dir)

    def create_database(self, config_dir):
        """Create the database. The parent folder must exist.
        """
        self.data_base = os.path.abspath(os.path.join(config_dir, "database"))
        if not os.path.exists(config_dir):
            raise DirectoryNotFoundError(
                config_dir, "must exist to create database there"
            )
        if not os.path.exists(self.data_base):
            mkdir_p(self.data_base)

    # Global

    def clear(self):
        """clear (delete) all software repositories.
        """
        for parser_dir in self.iter_parsers(fullpath=True):
            if os.path.exists(parser_dir):
                bot.info(f"Removing {parser_dir}")
                shutil.rmtree(parser_dir)
        return True

    # Get, delete, etc. only require uid

    def exists(self, uid):
        """Determine if a repo exists.
        """
        try:
            self.get(uid, exact=True)
            return True
        except:
            return False

    def add(self, uid):
        """Add a new software repository to the database.
        """
        if uid:
            parser = get_parser(uid, config=self.config)
            data = parser.get_metadata()
            if data:
                bot.info(f"{uid} was added to the the database.")
                return SoftwareRepository(parser, data_base=self.data_base)
        else:
            bot.error("Please define a unique identifier to add.")

    def get_or_create(self, uid):
        """Determine if a repo exists.
        """
        try:
            repo = self.get(uid, exact=True)
        except:
            repo = self.add(uid)
        return repo

    def get(self, uid=None, exact=False):
        """Get a software repo based on a uid. If exact is not needed, we can
           search for a match based on the partial uid.  If exact is False, 
           and a uid is not provided, get the last repository created.
        """
        if not uid and not exact:
            repos = get_latest_modified(self.data_base, pattern="metadata*.json")
            if repos:
                uid = (
                    repos.replace("metadata.json", "")
                    .replace(self.data_base, "")
                    .strip("/")
                )
            if not uid or not repos:
                raise NoReposError

        parser = get_parser(uid, config=self.config)
        return SoftwareRepository(parser, exists=True, data_base=self.data_base)

    def update(self, repo):
        """Update a repository by retrieving metadata, and then calling update 
           on the software repository to save it.
        """
        data = repo.parser.get_metadata()
        if data:
            repo.update()

    def search(self, query):
        """A filesystem search can only support returning results with filenames
        """
        results = []
        for repo in self.list_repos():
            if re.search(query, repo[0]):
                results.append(repo)
        return results

    def delete_repo(self, uid):
        """delete a repo based on a specific identifier. 
        """
        if self.exists(uid):
            repo = self.get(uid)
            os.remove(repo.filename)
            bot.info(f"{uid} has been removed.")
            return True

        bot.error(f"{uid} does not exist in the database.")
        return False

    def delete_parser(self, name):
        """delete all repos for a parser, based on executor's name (str).
        """
        parser_dir = os.path.join(self.data_base, name)
        if not os.path.exists(parser_dir):
            bot.info(f"Executor {parser_dir} directory does not exist.")
            return False
        shutil.rmtree(parser_dir)
        return True

    def iter_parsers(self, fullpath=False):
        """list executors based on the subfolders in the base database folder.
        """
        for contender in os.listdir(self.data_base):
            contender = os.path.join(self.data_base, contender)
            if os.path.isdir(contender):
                if not fullpath:
                    yield os.path.basename(contender)
                else:
                    yield contender

    def list_repos(self, name=None):
        """list software repositories, either under a particular parser name
           or just under all parsers. This returns repos in rows to be printed
           (or otherwise parsed).
        """
        listpath = self.data_base
        if name:
            listpath = os.path.join(listpath, name)
        rows = []
        for filename in recursive_find(listpath, pattern="metadata*.json"):
            rows.append(
                [
                    filename.replace("metadata.json", "")
                    .replace(self.data_base, "")
                    .strip("/")
                ]
            )
        return rows


class SoftwareRepository:
    """A software repository is a filesystem representation of a repo. It can 
       take a uid, determine if the repo exists, and then interact with the 
       metadata for it. If the repo is instantiated without a unique id
       it is assumed to not exist yet, otherwise it must already
       exist.
    """

    def __init__(self, parser, data_base, exists=False):
        """A SoftwareRepository holds some uid for a parser, and controls
           interaction with the filesystem. 

           Arguments:
             parser (str)    : the parser
             data_base (str) : the path where the database exists.
             exists (bool)   : if True, must already exists (default is False)
        """
        self.uid = parser.uid
        self.parser = parser
        self.data_base = data_base
        self.data = {}
        self.create(exists)

    @property
    def filename(self):
        return os.path.join(self.parser_dir, "metadata.json")

    @property
    def parser_dir(self):
        return os.path.join(self.data_base, self.parser.uid)

    def update(self, updates=None):
        """Update a data file. This means reading, updating, and writing.
        """
        updates = updates or {}
        self.data.update(updates)
        self.save()

    def create(self, should_exist=False):
        """create the filename if it doesn't exist, otherwise if it should (and
           does not) exit on error.
        """
        if should_exist:
            if not os.path.exists(self.filename):

                # Might be provided prefix
                contenders = glob("%s*" % os.path.join(self.data_base, self.parser.uid))
                if len(contenders) == 1:
                    self.parser.uid = re.sub(
                        "(%s/|[.]json)" % self.data_base, "", contenders[0],
                    )

                elif len(contenders) > 1:
                    raise MultipleReposExistError(self.parser.uid)
                else:
                    raise RepoNotFoundError(self.parser.uid)
            self.data = self.load()

        if not os.path.exists(self.parser_dir):
            mkdir_p(self.parser_dir)

        # If it's the first time saving, create basic file
        if not should_exist:
            self.data = {
                "parser": self.parser.name,
                "uid": self.parser.uid,
                "url": self.parser.get_url(),
                "data": self.parser.export(),
            }
            self.save()

    def export(self):
        """wrapper to expose the executor.export function
        """
        return self.parser.export()

    def save(self):
        """Save a json object (metadata.json) for the software repository.
        """
        write_json(self.data, self.filename)

    def summary(self):
        return self.parser.summary()

    def load(self):
        """Given a software uid, load data from filename.
        """
        if os.path.exists(self.filename):
            return read_json(self.filename)