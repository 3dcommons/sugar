# Copyright (C) 2008, One Laptop per Child
# Author: Sayamindu Dasgupta <sayamindu@laptop.org>
#
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

import ImageView
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

        self.zoom = None
        self._object_id = handle.object_id

        self._zoom_out_button = None
        self._zoom_in_button = None
        self._fileserver = None
        self._fileserver_tube_id = None

        self.view = ImageView.PrinterBot()
        self.progressdialog = None

        toolbar_box = ToolbarBox()
        self._add_toolbar_buttons(toolbar_box)
        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()

        vadj = gtk.Adjustment()
        hadj = gtk.Adjustment()
        self.sw = gtk.ScrolledWindow(hadj, vadj)

        self.sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.sw.add_with_viewport(self.view)
        # Avoid needless spacing
        self.view.parent.props.shadow_type = gtk.SHADOW_NONE

        self.set_canvas(self.sw)
        self.sw.show_all()

        self.unused_download_tubes = set()
        self._want_document = True
        self._download_content_length = 0
        self._download_content_type = None
        # Status of temp file used for write_file:
        self._tempfile = None
        self._close_requested = False
        self.connect("shared", self._shared_cb)
        h = hash(self._activity_id)
        self.port = 1024 + (h % 64511)

        self.is_received_document = False

        if self._shared_activity and handle.object_id == None:
            # We're joining, and we don't already have the document.
            if self.get_shared():
                # Already joined for some reason, just get the document
                self._joined_cb(self)
            else:
                # Wait for a successful join before trying to get the document
                self.connect("joined", self._joined_cb)
        elif self._object_id is None:
            self._show_object_picker = gobject.timeout_add(1000, \
                self._show_picker_cb)

    def handle_view_source(self):
        raise NotImplementedError

    def fullscreen(self):
        self.view.update_optimal_zoom()
        activity.Activity.fullscreen(self)

    def unfullscreen(self):
        activity.Activity.unfullscreen(self)
        self.view.update_optimal_zoom()

    def _add_toolbar_buttons(self, toolbar_box):
        activity_button = ActivityToolbarButton(self)
        toolbar_box.toolbar.insert(activity_button, 0)
        activity_button.show()

        self._zoom_out_button = ToolButton('zoom-out')
        self._zoom_out_button.set_tooltip(_('Zoom out'))
        self._zoom_out_button.connect('clicked', self.__zoom_out_cb)
        toolbar_box.toolbar.insert(self._zoom_out_button, -1)
        self._zoom_out_button.show()

        self._zoom_in_button = ToolButton('zoom-in')
        self._zoom_in_button.set_tooltip(_('Zoom in'))
        self._zoom_in_button.connect('clicked', self.__zoom_in_cb)
        toolbar_box.toolbar.insert(self._zoom_in_button, -1)
        self._zoom_in_button.show()

        zoom_tofit_button = ToolButton('zoom-best-fit')
        zoom_tofit_button.set_tooltip(_('Fit to window'))
        zoom_tofit_button.connect('clicked', self.__zoom_tofit_cb)
        toolbar_box.toolbar.insert(zoom_tofit_button, -1)
        zoom_tofit_button.show()

        zoom_original_button = ToolButton('zoom-original')
        zoom_original_button.set_tooltip(_('Original size'))
        zoom_original_button.connect('clicked', self.__zoom_original_cb)
        toolbar_box.toolbar.insert(zoom_original_button, -1)
        zoom_original_button.show()

        startprint_button = ToolButton('startprint')
        startprint_button.set_tooltip(_('Start Print'))
        startprint_button.connect('clicked', self.__startprint_cb)
        toolbar_box.toolbar.insert(startprint_button, -1)
        startprint_button.show()

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        toolbar_box.toolbar.insert(spacer, -1)
        spacer.show()

        rotate_anticlockwise_button = ToolButton('rotate_anticlockwise')
        rotate_anticlockwise_button.set_tooltip(_('Rotate anticlockwise'))
        rotate_anticlockwise_button.connect('clicked',
                self.__rotate_anticlockwise_cb)
        toolbar_box.toolbar.insert(rotate_anticlockwise_button, -1)
        rotate_anticlockwise_button.show()

        rotate_clockwise_button = ToolButton('rotate_clockwise')
        rotate_clockwise_button.set_tooltip(_('Rotate clockwise'))
        rotate_clockwise_button.connect('clicked', self.__rotate_clockwise_cb)
        toolbar_box.toolbar.insert(rotate_clockwise_button, -1)
        rotate_clockwise_button.show()

        spacer = gtk.SeparatorToolItem()
        spacer.props.draw = False
        toolbar_box.toolbar.insert(spacer, -1)
        spacer.show()

        fullscreen_button = ToolButton('view-fullscreen')
        fullscreen_button.set_tooltip(_('Fullscreen'))
        fullscreen_button.connect('clicked', self.__fullscreen_cb)
        toolbar_box.toolbar.insert(fullscreen_button, -1)
        fullscreen_button.show()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

    def __zoom_in_cb(self, button):
        self._zoom_in_button.set_sensitive(self.view.zoom_in())
        self._zoom_out_button.set_sensitive(True)

    def __zoom_out_cb(self, button):
        self._zoom_out_button.set_sensitive(self.view.zoom_out())
        self._zoom_in_button.set_sensitive(True)

    def __zoom_tofit_cb(self, button):
        self.view.set_optimal_zoom()

    def __zoom_original_cb(self, button):
        self.view.set_zoom(1)

    def __rotate_anticlockwise_cb(self, button):
        angle = self.view.get_property('angle')
        self.view.set_angle(angle + 90)

    def __rotate_clockwise_cb(self, button):
        angle = self.view.get_property('angle')
        if angle == 0:
            angle = 360

        self.view.set_angle(angle - 90)

    def __fullscreen_cb(self, button):
        self.fullscreen()

    def _show_picker_cb(self):
        if not self._want_document:
            return

        chooser = ObjectChooser(_('Choose document'), self,
            gtk.DIALOG_MODAL |
            gtk.DIALOG_DESTROY_WITH_PARENT, \
            what_filter=mime.GENERIC_TYPE_IMAGE)

        try:
            result = chooser.run()
            if result == gtk.RESPONSE_ACCEPT:
                jobject = chooser.get_selected_object()
                if jobject and jobject.file_path:
                    self.read_file(jobject.file_path)
        finally:
            chooser.destroy()
            del chooser

    def read_file(self, file_path):
        self._want_document = False

        tempfile = os.path.join(self.get_activity_root(), 'instance', \
            'tmp%i' % time.time())

        os.link(file_path, tempfile)
        self._tempfile = tempfile
        gobject.idle_add(self.__set_file_idle_cb, tempfile)

    def __set_file_idle_cb(self, file_path):
        self.view.set_file_location(file_path)

        try:
            self.zoom = int(self.metadata.get('zoom', '0'))
            if self.zoom > 0:
                self.view.set_zoom(self.zoom)
        except Exception:
            pass

        return False

    def write_file(self, file_path):
        if self._tempfile:
            self.metadata['activity'] = self.get_bundle_id()
            self.metadata['zoom'] = str(self.zoom)
            if self._close_requested:
                os.link(self._tempfile, file_path)
                os.unlink(self._tempfile)
                self._tempfile = None
        else:
            raise NotImplementedError

    def can_close(self):
        self._close_requested = True
        return True

    def _download_result_cb(self, getter, tempfile, suggested_name, tube_id):
        if self._download_content_type == 'text/html':
            # got an error page instead
            self._download_error_cb(getter, 'HTTP Error', tube_id)
            return

        del self.unused_download_tubes

        self._tempfile = tempfile
        file_path = os.path.join(self.get_activity_root(), 'instance',
                                    '%i' % time.time())
        _logger.debug("Saving file %s to datastore...", file_path)
        os.link(tempfile, file_path)
        self._jobject.file_path = file_path
        datastore.write(self._jobject, transfer_ownership=True)


        _logger.debug("Got document %s (%s) from tube %u",
                      tempfile, suggested_name, tube_id)

        self.progressdialog.destroy()

        gobject.idle_add(self.__set_file_idle_cb, tempfile)
        self.save()

    def _download_progress_cb(self, getter, bytes_downloaded, tube_id):
        if self._download_content_length > 0:
            _logger.debug("Downloaded %u of %u bytes from tube %u...",
                          bytes_downloaded, self._download_content_length,
                          tube_id)
        else:
            _logger.debug("Downloaded %u bytes from tube %u...",
                          bytes_downloaded, tube_id)
        total = self._download_content_length

        fraction = bytes_downloaded / total
        self.progressdialog.set_fraction(fraction)

        #gtk.main_iteration()

    def _download_error_cb(self, getter, err, tube_id):
        _logger.debug("Error getting document from tube %u: %s",
                      tube_id, err)
        self._alert('Failure', 'Error getting document from tube')
        self._want_document = True
        self._download_content_length = 0
        self._download_content_type = None
        gobject.idle_add(self._get_document)

    def _download_document(self, tube_id, path):
        # FIXME: should ideally have the CM listen on a Unix socket
        # instead of IPv4 (might be more compatible with Rainbow)
        chan = self._shared_activity.telepathy_tubes_chan
        iface = chan[telepathy.CHANNEL_TYPE_TUBES]
        addr = iface.AcceptStreamTube(tube_id,
                telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0,
                utf8_strings=True)
        _logger.debug('Accepted stream tube: listening address is %r', addr)
        # SOCKET_ADDRESS_TYPE_IPV4 is defined to have addresses of type '(sq)'
        assert isinstance(addr, dbus.Struct)
        assert len(addr) == 2
        assert isinstance(addr[0], str)
        assert isinstance(addr[1], (int, long))
        assert addr[1] > 0 and addr[1] < 65536
        port = int(addr[1])

        getter = PrinterBotURLDownloader("http://%s:%d/document"
                                           % (addr[0], port))
        getter.connect("finished", self._download_result_cb, tube_id)
        getter.connect("progress", self._download_progress_cb, tube_id)
        getter.connect("error", self._download_error_cb, tube_id)
        _logger.debug("Starting download to %s...", path)
        getter.start(path)
        self._download_content_length = getter.get_content_length()
        self._download_content_type = getter.get_content_type()

        return False

    def _get_document(self):
        if not self._want_document:
            return False

        # Assign a file path to download if one doesn't exist yet
        if not self._jobject.file_path:
            path = os.path.join(self.get_activity_root(), 'instance',
                                'tmp%i' % time.time())
        else:
            path = self._jobject.file_path

        # Pick an arbitrary tube we can try to download the document from
        try:
            tube_id = self.unused_download_tubes.pop()
        except (ValueError, KeyError), e:
            _logger.debug('No tubes to get the document from right now: %s',
                          e)
            return False

        # Avoid trying to download the document multiple times at once
        self._want_document = False
        gobject.idle_add(self._download_document, tube_id, path)
        return False

    def _joined_cb(self, also_self):
        """Callback for when a shared activity is joined.

        Get the shared document from another participant.
        """
        self.watch_for_tubes()

        self.progressdialog = ProgressDialog.ProgressDialog(self)
        self.progressdialog.show_all()

        gobject.idle_add(self._get_document)

    def _share_document(self):
        """Share the document."""
        # FIXME: should ideally have the fileserver listen on a Unix socket
        # instead of IPv4 (might be more compatible with Rainbow)

        _logger.debug('Starting HTTP server on port %d', self.port)
        self._fileserver = PrinterBotHTTPServer(("", self.port),
            self._tempfile)

        # Make a tube for it
        chan = self._shared_activity.telepathy_tubes_chan
        iface = chan[telepathy.CHANNEL_TYPE_TUBES]
        self._fileserver_tube_id = \
                iface.OfferStreamTube(PrinterBot_STREAM_SERVICE,
                {},
                telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                ('127.0.0.1', dbus.UInt16(self.port)),
                telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0)

    def watch_for_tubes(self):
        """Watch for new tubes."""
        tubes_chan = self._shared_activity.telepathy_tubes_chan

        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal('NewTube',
            self._new_tube_cb)
        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)

    def _new_tube_cb(self, tube_id, initiator, tube_type, service, params,
                     state):
        """Callback when a new tube becomes available."""
        _logger.debug('New tube: ID=%d initator=%d type=%d service=%s '
                      'params=%r state=%d', tube_id, initiator, tube_type,
                      service, params, state)
        if service == PrinterBot_STREAM_SERVICE:
            _logger.debug('I could download from that tube')
            self.unused_download_tubes.add(tube_id)
            # if no download is in progress, let's fetch the document
            if self._want_document:
                gobject.idle_add(self._get_document)

    def _list_tubes_reply_cb(self, tubes):
        """Callback when new tubes are available."""
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        """Handle ListTubes error by logging."""
        _logger.error('ListTubes() failed: %s', e)

    def _shared_cb(self, activityid):
        """Callback when activity shared.

        Set up to share the document.

        """
        # We initiated this activity and have now shared it, so by
        # definition we have the file.
        _logger.debug('Activity became shared')
        self.watch_for_tubes()
        self._share_document()

    def _alert(self, title, text=None):
        alert = NotifyAlert(timeout=5)
        alert.props.title = title
        alert.props.msg = text
        self.add_alert(alert)
        alert.connect('response', self._alert_cancel_cb)
        alert.show()

    def _alert_cancel_cb(self, alert, response_id):
        self.remove_alert(alert)