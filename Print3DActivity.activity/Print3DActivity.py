from sugar.activity import activity
import logging 
import sys, os
import gtk 
class Print3DActivity(activity.Activity):
     def hello(self, widget, data=None):
         logging.info('Hello World')
 
     def __init__(self, handle):
         print "running activity init", handle
         activity.Activity.__init__(self, handle)
         print "activity running"
 
         # Creates the Toolbox. It contains the Activity Toolbar, which is the
         # bar that appears on every Sugar window and contains essential
         # functionalities, such as the 'Collaborate' and 'Close' buttons.
         toolbox = activity.ActivityToolbox(self)
         self.set_toolbox(toolbox)
         toolbox.show()
 
         # Creates a new button with the label "Hello World".
         self.button = gtk.Button("Hello World")
     
         # When the button receives the "clicked" signal, it will call the
         # function hello() passing it None as its argument.  The hello()
         # function is defined above.
         self.button.connect("clicked", self.hello, None)
     
         # Set the button to be our canvas. The canvas is the main section of
         # every Sugar Window. It fills all the area below the toolbox.
         self.set_canvas(self.button)
     
         # The final step is to display this newly created widget.
         self.button.show()
     
         print "AT END OF THE CLASS"