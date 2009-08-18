# Stop.py -- Stop file system
# Copyright (C) 2007, 2008, 2009 CEA
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

"""
Shine `stop' command classes.

The stop command aims to stop Lustre filesystem servers or just some
of the filesystem targets on local or remote servers. It is available
for any filesystems previously installed and formatted.
"""

import os

# Configuration
from Shine.Configuration.Configuration import Configuration
from Shine.Configuration.Globals import Globals 
from Shine.Configuration.Exceptions import *

from Shine.Commands.Status import Status

# Command base class
from Base.FSLiveCommand import FSLiveCommand
from Base.FSEventHandler import FSGlobalEventHandler
from Base.CommandRCDefs import *
# -R handler
from Base.RemoteCallEventHandler import RemoteCallEventHandler

# Command helper
from Shine.FSUtils import open_lustrefs

# Lustre events
import Shine.Lustre.EventHandler

# Shine Proxy Protocol
from Shine.Lustre.Actions.Proxies.ProxyAction import *
from Shine.Lustre.FileSystem import *


class GlobalStopEventHandler(FSGlobalEventHandler):

    def __init__(self, verbose=False):
        FSGlobalEventHandler.__init__(self, verbose)

    def handle_pre(self, fs):
        if self.verbose > 0:
            print "Stopping %d targets of %s on %s" % (fs.target_count,
                    fs.fs_name, fs.target_servers)

    def handle_post(self, fs):
        if self.verbose > 0:
            Status.status_view_fs(fs, show_clients=False)

    def ev_stoptarget_start(self, node, target):
        if self.verbose > 1:
            print "%s: Stopping %s %s (%s)..." % (node, \
                    target.type.upper(), target.get_id(), target.dev)
        self.update()

    def ev_stoptarget_done(self, node, target):
        self.status_changed = True
        if self.verbose > 1:
            if target.status_info:
                print "%s: Stop of %s %s (%s): %s" % \
                        (node, target.type.upper(), target.get_id(), target.dev,
                                target.status_info)
            else:
                print "%s: Stop of %s %s (%s) succeeded" % \
                        (node, target.type.upper(), target.get_id(), target.dev)
        self.update()

    def ev_stoptarget_failed(self, node, target, rc, message):
        self.status_changed = True
        if rc:
            strerr = os.strerror(rc)
        else:
            strerr = message
        print "%s: Failed to stop %s %s (%s): %s" % \
                (node, target.type.upper(), target.get_id(), target.dev,
                        strerr)
        if rc:
            print message
        self.update()

class LocalStopEventHandler(Shine.Lustre.EventHandler.EventHandler):

    def __init__(self, verbose=1):
        self.verbose = verbose


class Stop(FSLiveCommand):
    """
    shine stop [-f <fsname>] [-t <target>] [-i <index(es)>] [-n <nodes>] [-qv]
    """

    def __init__(self):
        FSLiveCommand.__init__(self)

    def get_name(self):
        return "stop"

    def get_desc(self):
        return "Stop file system servers."

    target_status_rc_map = { \
            MOUNTED : RC_FAILURE,
            RECOVERING : RC_FAILURE,
            EXTERNAL : RC_ST_EXTERNAL,
            OFFLINE : RC_OK,
            TARGET_ERROR : RC_TARGET_ERROR,
            CLIENT_ERROR : RC_CLIENT_ERROR,
            RUNTIME_ERROR : RC_RUNTIME_ERROR }

    def fs_status_to_rc(self, status):
        return self.target_status_rc_map[status]

    def execute(self):
        result = 0

        self.init_execute()

        # Get verbose level.
        vlevel = self.verbose_support.get_verbose_level()

        target = self.target_support.get_target()
        for fsname in self.fs_support.iter_fsname():

            # Install appropriate event handler.
            eh = self.install_eventhandler(LocalStopEventHandler(vlevel),
                    GlobalStopEventHandler(vlevel))

            fs_conf, fs = open_lustrefs(fsname, target,
                    nodes=self.nodes_support.get_nodeset(),
                    indexes=self.indexes_support.get_rangeset(),
                    event_handler=eh)

            mount_options = {}
            mount_paths = {}
            for target_type in [ 'mgt', 'mdt', 'ost' ]:
                mount_options[target_type] = fs_conf.get_target_mount_options(target_type)
                mount_paths[target_type] = fs_conf.get_target_mount_path(target_type)

            fs.set_debug(self.debug_support.has_debug())

            if not fs.target_servers:
                print "No `%s' target to stop on %s" % (fsname,
                        self.nodes_support.get_nodeset())
                rc = RC_FAILURE
                continue

            # Will call the handle_pre() method defined by the event handler.
            if hasattr(eh, 'pre'):
                eh.pre(fs)
                
            status = fs.stop()
            rc = self.fs_status_to_rc(status)
            if rc > result:
                result = rc

            if rc == RC_OK:
                if vlevel > 0:
                    print "Stop successful."
            elif rc == RC_RUNTIME_ERROR:
                for nodes, msg in fs.proxy_errors:
                    print "%s: %s" % (nodes, msg)

            if hasattr(eh, 'post'):
                eh.post(fs)

        return result

