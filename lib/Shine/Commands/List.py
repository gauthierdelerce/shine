# List.py -- List FS
# Copyright (C) 2008 CEA
#
# This file is part of shine
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# $Id$

from Shine.Configuration.Configuration import Configuration
from Shine.Configuration.Globals import Globals 
from Shine.Configuration.Exceptions import *

from Shine.Utilities.AsciiTable import *

from Base.Command import Command
from Base.Support.FS import FS


# ----------------------------------------------------------------------
# * shine list
# ----------------------------------------------------------------------
class List(Command):
    """
    Simply list installed file systems.
    """
    def __init__(self):
        Command.__init__(self)

        self.fs_support = FS(self)

    def get_name(self):
        return "list"

    def get_desc(self):
        return "List configured file systems."

    def execute(self):
        for fsname in self.fs_support.iter_fsname():
            print fsname
