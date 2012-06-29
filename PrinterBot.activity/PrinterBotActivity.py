# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

# The sharing bits have been taken from ReadEtexts

from __future__ import division

from sugar.activity import activity
import logging

from gettext import gettext as _

import time
import os
import gtk
import gobject

from sugar.graphics.alert import NotifyAlert
from sugar.graphics.objectchooser import ObjectChooser
from sugar import mime
from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.toolbarbox import ToolbarBox
from sugar.activity.widgets import ActivityToolbarButton
from sugar.activity.widgets import StopButton

from sugar import network
from sugar.datastore import datastore
import telepathy
import dbus

import ProgressDialog
import Printcore

_logger = logging.getLogger('PrinterBot-activity')


class PrinterBotHTTPRequestHandler(network.ChunkedGlibHTTPRequestHandler):
    """HTTP Request Handler for transferring document while collaborating.

    RequestHandler class that integrates with Glib mainloop. It writes
    the specified file to the client in chunks, returning control to the
    mainloop between chunks.

    """

    def translate_path(self, path):
        """Return the filepath to the shared document."""
        return self.server.filepath


class PrinterBotHTTPServer(network.GlibTCPServer):
    """HTTP Server for transferring document while collaborating."""

    def __init__(self, server_address, filepath):
        """Set up the GlibTCPServer with the PrinterBotHTTPRequestHandler.

        filepath -- path to shared document to be served.
        """
        self.filepath = filepath
        network.GlibTCPServer.__init__(self, server_address,
                                       PrinterBotHTTPRequestHandler)


class PrinterBotURLDownloader(network.GlibURLDownloader):
    """URLDownloader that provides content-length and content-type."""

    def get_content_length(self):
        """Return the content-length of the download."""
        if self._info is not None:
            return int(self._info.headers.get('Content-Length'))

    def get_content_type(self):
        """Return the content-type of the download."""
        if self._info is not None:
            return self._info.headers.get('Content-type')
        return None

PrinterBot_STREAM_SERVICE = 'PrinterBot-activity-http'



class PrinterBotActivity(activity.Activity):

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)

        self._object_id = handle.object_id

        self._fileserver = None
        self._fileserver_tube_id = None

        self.progressdialog = None

        toolbar_box = ToolbarBox()
        self._add_toolbar_buttons(toolbar_box)
        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()
        
        self.set_canvas(self.startprint_button)

    def handle_view_source(self):
        raise NotImplementedError

    def _add_toolbar_buttons(self, toolbar_box):
        activity_button = ActivityToolbarButton(self)
        toolbar_box.toolbar.insert(activity_button, 0)
        activity_button.show()

        startprint_button = ToolButton('startprint')
        startprint_button.set_tooltip(_('Start Print'))
        startprint_button.connect('clicked', self.startprint)
        toolbar_box.toolbar.insert(startprint_button, -1)
        startprint_button.show()

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        toolbar_box.toolbar.insert(spacer, -1)
        spacer.show()


        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

    def startprint(self, widget, data=None):
        logging.info('Printing')