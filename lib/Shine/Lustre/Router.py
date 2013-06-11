# Router.py -- Shine Lustre Router
# Copyright (C) 2010-2013 CEA
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
# $Id: Client.py 248 2010-03-29 11:07:40Z ad-cea $

import os 

from Shine.Lustre.Component import Component, ComponentError, \
                                   MOUNTED, OFFLINE, TARGET_ERROR, RUNTIME_ERROR

from Shine.Lustre.Actions.Action import Result
from Shine.Lustre.Actions.StartRouter import StartRouter
from Shine.Lustre.Actions.StopRouter import StopRouter

class Router(Component):

    TYPE = 'router'
    DISPLAY_ORDER = 1
    START_ORDER = 1

    #
    # Text form for different router states. 
    #
    # Could be nearly merged with Target state_text_map if MOUNTED value
    # becomes the same.
    STATE_TEXT_MAP = { 
        None: "unknown",
        OFFLINE: "offline", 
        TARGET_ERROR: "ERROR", 
        MOUNTED: "online", 
        RUNTIME_ERROR: "CHECK FAILURE" 
    }

    def longtext(self):
        """
        Return the routeur server name.
        """
        return "router on %s" % self.server

    def lustre_check(self):
        """
        Check Router health at Lustre level.

        Check LNET routing capabilities and change object state
        based on the results.
        """

        # LNET is not loaded
        if not os.path.isfile("/proc/sys/lnet/routes"):
            self.state = OFFLINE
            return 

        # Read routing information
        try:
            routes = open("/proc/sys/lnet/routes")
            # read only first line
            state = routes.readline().strip().lower()
        except:
            self.state = RUNTIME_ERROR
            raise ComponentError(self, "Could not read routing information")

        # routing info tells this is ok?
        if state == "routing enabled":
            self.state = MOUNTED
        elif state == "routing disabled":
            self.state = TARGET_ERROR
            raise ComponentError(self, "Misconfigured router")
        else:
            self.state = RUNTIME_ERROR
            raise ComponentError(self, "Bad routing status")

    #
    # Client actions
    #

    def status(self):
        """
        Check router status.
        """
        self._action_start('status')

        try:
            self.full_check()
            self._action_done('status')
        except ComponentError, error:
            self._action_failed('status', Result(str(error)))


    def start(self, **kwargs):
        """
        Start a Lustre router
        """
        self._action_start('start')

        try:
            self.full_check()
            if self.state == MOUNTED:
                result = Result('router is already enabled')
                self._action_done('start', result=result)
            else:
                action = StartRouter(self)
                action.launch()

        except ComponentError, error:
            self._action_failed('start', Result(str(error)))

    def stop(self, **kwargs):
        """
        Stop a Lustre router
        """
        self._action_start('stop')

        try:
            self.full_check()
            if self.state == OFFLINE:
                result = Result('router is already disabled')
                self._action_done('stop', result=result)
            else:
                action = StopRouter(self)
                action.launch()

        except ComponentError, error:
            self._action_failed('stop', Result(str(error)))
