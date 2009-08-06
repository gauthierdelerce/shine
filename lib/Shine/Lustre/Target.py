# Target.py -- Lustre Target base class
# Copyright (C) 2007, 2008 CEA
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

import glob
import os 
import stat
import struct
import sys

from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import *

from Shine.Configuration.Globals import Globals

from Actions.Format import Format
from Actions.StartTarget import StartTarget
from Actions.StopTarget import StopTarget

from Disk import *
from Server import Server


class TargetOpInProgressException(Exception):
    pass

class TargetException(Exception):
    def __init__(self, target):
        self.target = target

class TargetError(TargetException):
    """
    Generic target related error.
    """

class TargetDeviceError(TargetError):
    """
    Target's underlying device error.
    """
    def __init__(self, target, message):
        TargetError.__init__(self, target)
        self.message = message

    def __str__(self):
        return self.message


# Constants for target/client states
(MOUNTED, RECOVERING, OFFLINE, INPROGRESS, CLIENT_ERROR, TARGET_ERROR, RUNTIME_ERROR) = range(7)


class Target(Disk):

    def __init__(self, fs, server, type, index, dev, jdev=None, group=None,
            tag=None, enabled=True):
        """
        Initialize a Lustre target object.
        """
        Disk.__init__(self, dev, jdev)

        #print "new Target %s %s %d (enabled=%s)" % (type, dev, index, enabled)

        ### Not serializable

        # attached file system
        self.fs = fs

        ### Serializable

        ## Always available variables

        # target's servers: master server is always self.servers[0]
        self.server = server # temp until HA is fully implemented
        self.servers = [ server ]

        # selected server
        self.selected_server = 0

        self.type = type            # 'mgt', 'mdt', 'ost', or 'client'
        assert index is not None
        self.index = int(index)
        self.group = group
        self.tag = tag

        if self.type == 'mgt':
            self.label = "MGS"
        else:
            self.label = "%s-%s%04x" % (self.fs.fs_name, self.type.upper(), self.index)

        self.action_enabled = enabled

        self.state = None   # Unknown
        self.status_info = None

        self.fs._attach_target(self)


    def __lt__(self, other):
        return self.target_order < other.target_order

    def match(self, other):
        return self.type == other.type and \
                self.dev == other.dev and \
                self.index == other.index and \
                str(self.servers[0]) == str(other.servers[0])

    def update(self, other):
        """
        Update my serializable fields from other/distant object.
        """
        Disk.update(self, other)
        self.dev_isblk = other.dev_isblk
        self.dev_size = other.dev_size
        self.label = other.label
        self.state = other.state
        self.status_info = other.status_info

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['fs']
        #print odict
        return odict

    def __setstate__(self, dict):
        self.__dict__.update(dict)
        self.fs = None

    def add_server(self, server):
        assert isinstance(server, Server)
        self.servers.append(server)

    def get_selected_server(self):
        return self.servers[self.selected_server]

    def get_id(self):
        """
        Get target human readable identifier.
        """
        if self.tag is not None:
            return self.tag

        return self.label
    
    def get_nids(self):
        """
        Return an ordered list of target's NIDs.
        """
        return [s.nid for s in self.servers]

    def _lustre_check(self):

        self.state = None   # Unknown

        # find pathnames matching wanted lustre procfs
        mntdev_path = glob.glob('/proc/fs/lustre/*/%s/mntdev' % self.label)
        assert len(mntdev_path) <= 1

        recov_path = glob.glob('/proc/fs/lustre/*/%s/recovery_status' % self.label)
        assert len(recov_path) <= 1

        # check for label presence in /proc : is this lustre target started?
        if len(mntdev_path) == 0 and len(recov_path) == 0:
            self.state = OFFLINE
        elif len(mntdev_path) == 0:
            self.state = TARGET_ERROR
            raise TargetDeviceError(self, "incoherent state in /proc/fs/lustre for %s" % \
                    self.label)
        else:
            # get target's real device
            f = open(mntdev_path[0])
            try:
                self.mntdev = f.readline().rstrip('\n')
            finally:
                f.close()

            loaded = True

            # check for presence in /proc/mounts
            f_proc_mounts = open("/proc/mounts", 'r')
            try:
                for line in f_proc_mounts:
                    if line.find("%s " % self.mntdev) == 0:
                        if line.split(' ', 3)[2] == "lustre":
                            if loaded:
                                self.state = MOUNTED
                            else:
                                self.state = TARGET_ERROR
                                raise TargetDeviceError(self, "multiple mounts detected for %s" % \
                                        self.label)
            finally:
                f_proc_mounts.close()

            if self.state != MOUNTED and loaded:
                self.state = TARGET_ERROR
                # up but not mounted = incoherent state
                # check for loaded state: ST, UP...
                raise TargetDeviceError(self, "incoherent state for %s (started but not mounted?)" % \
                       self.label)

            if self.state == MOUNTED and self.type != 'mgt':
                # check for MDT or OST recovery (MGS doesn't make any recovery)
                try:
                    f = open(recov_path[0], 'r')
                except (IOError, IndexError):
                    self.state = TARGET_ERROR
                    raise TargetDeviceError(self, "recovery_state file not found for %s" % \
                            self.label)

                try:
                    recovery_duration = -1
                    completed_clients = -1
                    time_remaining = -1

                    for line in f:
                        if line.startswith("status:"):
                            key, status = line.rstrip().split(' ', 2)
                            break
                    if status == "COMPLETE":
                        for line in f:
                            if line.startswith("recovery_duration:"):
                                key, recovery_duration = line.rstrip().split(' ', 2) 
                            if line.startswith("completed_clients:"):
                                key, completed_clients = line.rstrip().split(' ', 2)
                    if status == "RECOVERING":
                        for line in f:
                            if line.startswith("time_remaining:"):
                                key, time_remaining = line.rstrip().split(' ', 2)
                            if line.startswith("completed_clients:"):
                                key, completed_clients = line.rstrip().split(' ', 2)
                        self.state = RECOVERING
                        self.status_info = "%ss (%s)" % (time_remaining, completed_clients)
                finally:
                    f.close()

    def format(self, **kwargs):

        self.state = INPROGRESS
        self.fs._invoke('ev_format_start', target=self)

        try:
            self._device_check()
        except DiskDeviceError, e:
            self.state = TARGET_ERROR
            self.fs._invoke('ev_format_failed', target=self, rc=1, message=str(e))
            return

        try:
            self._lustre_check()

            if self.state == OFFLINE:
                # LBUG #18624 : workaround for "multiple mkfs.lustre on loop devices"
                if not self.dev_isblk:
                    # configure one engine client max per task (sequential, bah.)
                    task_self().set_info("fanout", 1)

                self.state = INPROGRESS
                action = Format(self, **kwargs)
                action.launch()
            else:
                # Target state is not DOWN... cannot format device.
                if self.state > LOADED:
                    reason = "Cannot format: target %s (%s) is started"
                else:
                    reason = "Cannot format: target %s (%s) is busy"
                self.state = TARGET_ERROR
                raise TargetDeviceError(self, reason % (self.label, self.dev))

        except TargetDeviceError, e:
            self.fs._invoke('ev_format_failed', target=self, rc=-1, message=str(e))

    def status(self):
        """
        Check target status.
        """
        self.fs._invoke('ev_statustarget_start', target=self)

        try:
            # check for disk level status
            self._disk_check(self.fs.fs_name, self.label)
        except DiskDeviceError, e:
            self.state = TARGET_ERROR
            self.fs._invoke('ev_statustarget_failed', target=self, rc=1, message=str(e))
            return

        # check for Lustre level status
        self._lustre_check()

        self.fs._invoke('ev_statustarget_done', target=self)

    def start(self, **kwargs):

        self.state = INPROGRESS
        self.fs._invoke('ev_starttarget_start', target=self)

        try:
            self._device_check()
            self._lustre_check()

            if self.state != OFFLINE:
                # already mounted ?
                if  self.state == RECOVERING or self.state == MOUNTED:
                    self.status_info = "%s is already started" % self.label
                    self.fs._invoke('ev_starttarget_done', target=self)
                    return
                raise TargetDeviceError(self, "bad state `%s' for %s" % \
                        (self.state, self.label))

            # LBUG #18624
            if not self.dev_isblk:
                task_self().set_info("fanout", 1)

            action = StartTarget(self, **kwargs)
            action.launch()

        except TargetDeviceError, e:
            self.fs._invoke('ev_starttarget_failed', target=self, rc=None, message=str(e))

    def _action_done(self, act):
        """Called by Actions.* when done"""
        self._lustre_check()
        self.fs._invoke('ev_%s_done' % act, target=self)

    def _action_timeout(self, act):
        """Called by Actions.* on timeout"""
        self._lustre_check()
        self.fs._invoke('ev_%s_timeout' % act, target=self)

    def _action_failed(self, act, rc, message):
        """Called by Actions.* on failure"""
        self._lustre_check()
        self.fs._invoke('ev_%s_failed' % act, target=self, rc=rc, message=message)

    def stop(self, **kwargs):

        self.state = INPROGRESS
        self.fs._invoke('ev_stoptarget_start', target=self)

        try:
            self._disk_check()
            self._lustre_check()

            if self.state == OFFLINE:
                self.status_info = "%s is already stopped" % self.label
                self.fs._invoke('ev_stoptarget_done', target=self)
                return

            # LBUG #18624
            if not self.dev_isblk:
                task_self().set_info("fanout", 1)

            action = StopTarget(self, **kwargs)
            action.launch()

        except TargetDeviceError, e:
            self.fs._invoke('ev_stoptarget_failed', target=self, rc=None, message=str(e))

    def _stop_done(self):
        """Called by Actions.StopTarget when done"""
        self._lustre_check()
        self.fs._invoke('ev_stoptarget_done', target=self)

    def _stop_timeout(self):
        """Called by Actions.StopTarget on timeout"""
        self._lustre_check()
        self.fs._invoke('ev_stoptarget_timeout', target=self)

    def _stop_failed(self, rc, message):
        """Called by Actions.StopTarget on failure"""
        self._lustre_check()
        self.fs._invoke('ev_stoptarget_failed', target=self, rc=rc, message=message)

    def fcsk(self):
        pass


class MGT(Target):

    target_order = 1

    def __init__(self, **kwargs):
        Target.__init__(self, type='mgt', **kwargs)


class MDT(Target):

    target_order = 4    # changed to 2 in writeconf mode

    def __init__(self, **kwargs):
        Target.__init__(self, type='mdt', **kwargs)


class OST(Target):

    target_order = 3

    def __init__(self, **kwargs):
        Target.__init__(self, type='ost', **kwargs)


