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
import pronsole

_logger = logging.getLogger('PrinterBot-activity')

import os, gettext, Queue, re

if os.path.exists('/usr/share/pronterface/locale'):
    gettext.install('pronterface', '/usr/share/pronterface/locale', unicode=1)
else:
    gettext.install('pronterface', './locale', unicode=1)

import printcore, sys, glob, time, threading, traceback, traceback, cStringIO, subprocess
try:
    os.chdir(os.path.split(__file__)[0])
except:
    pass
StringIO=cStringIO

thread=threading.Thread

"""
class PrinterBotHTTPRequestHandler(network.ChunkedGlibHTTPRequestHandler):
    def translate_path(self, path):
        return self.server.filepath


class PrinterBotHTTPServer(network.GlibTCPServer):
    def __init__(self, server_address, filepath):
        self.filepath = filepath
        network.GlibTCPServer.__init__(self, server_address,
                                       PrinterBotHTTPRequestHandler)


class PrinterBotURLDownloader(network.GlibURLDownloader):

    def get_content_length(self):
        if self._info is not None:
            return int(self._info.headers.get('Content-Length'))

    def get_content_type(self):
        if self._info is not None:
            return self._info.headers.get('Content-type')
        return None

PrinterBot_STREAM_SERVICE = 'PrinterBot-activity-http'
"""
class PrinterBotActivity(activity.Activity, pronsole.pronsole):

    def __init__(self, handle, filename=None):
        activity.Activity.__init__(self, handle)
	pronsole.pronsole.__init__(self)

        toolbar_box = ToolbarBox()
        self._add_toolbar_buttons(toolbar_box)
        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()

    def handle_view_source(self):
        raise NotImplementedError

    def _add_toolbar_buttons(self, toolbar_box):
        activity_button = ActivityToolbarButton(self)
        toolbar_box.toolbar.insert(activity_button, 0)
        activity_button.show()

	connect_button = ToolButton('connect')
	connect_button.set_tooltip(_('Connect'))
	connect_button.connect('clicked',self.connection)
	toolbar_box.toolbar.insert(connect_button, -1)
	connect_button.show()

        self.serialport = self.scanserial()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

    def scanserial(self):
        #scan for available ports. return a list of device names.
        baselist=[]
        if os.name=="nt":
            try:
                key=_winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"HARDWARE\\DEVICEMAP\\SERIALCOMM")
                i=0
                while(1):
                    baselist+=[_winreg.EnumValue(key,i)[1]]
                    i+=1
            except:
                pass
        return baselist+glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') +glob.glob("/dev/tty.*")+glob.glob("/dev/cu.*")+glob.glob("/dev/rfcomm*")

    def connection(self,event):
        print _("Connecting...")
        port=None
        try:
            port=self.scanserial()[0]
        except:
            pass
        if self.serialport.GetValue()!="":
            port=str(self.serialport.GetValue())
        baud=115200
        try:
            baud=int(self.baud.GetValue())
        except:
            pass
        self.p.connection(port,baud)
        #self.statuscheck=True
        if port != self.settings.port:
            self.set("port",port)
        if baud != self.settings.baudrate:
            self.set("baudrate",str(baud))
        threading.Thread(target=self.statuschecker).start()