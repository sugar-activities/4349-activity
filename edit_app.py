'''A simple text editor for Sugar
Written mostly by Nate Theis
Some GTK code borrowed from Pippy
'''

from groupthink import sugar_tools, gtk_tools

from gettext import gettext as _

import gtk, pango
import time
import gtksourceview2 as gtksourceview

from sugar.graphics import style
from sugar.activity.activity import EditToolbar
from sugar.activity.widgets import ActivityToolbar
from sugar.graphics.toolbarbox import ToolbarBox
from sugar.graphics.toolbarbox import ToolbarButton
from sugar.activity.widgets import StopButton

import mdnames

from sugar.graphics.xocolor import XoColor
from sugar.graphics.icon import Icon
from sugar.bundle.activitybundle import ActivityBundle

def _create_activity_icon(metadata):
    '''Get the icon given an activity'''
    if metadata.get('icon-color', ''):
        color = XoColor(metadata['icon-color'])
    else:
        client = gconf.client_get_default()
        color = XoColor(client.get_string(
            '/desktop/sugar/user/color'))

    from sugar.activity.activity import get_bundle_path
    bundle = ActivityBundle(get_bundle_path())
    icon = Icon(file=bundle.get_icon(), xo_color=color)

    return icon

class ActivityToolbarButton(ToolbarButton):
    #thanks, sugar activity guide
    def __init__(self, activity, **kwargs):
        toolbar = ActivityToolbar(activity,
            orientation_left=True)
        toolbar.stop.hide()
        toolbar.keep.hide()

        ToolbarButton.__init__(self, page=toolbar,
            **kwargs)

        icon = _create_activity_icon(activity.metadata)
        self.set_icon_widget(icon)
        icon.show()

class EditActivity(sugar_tools.GroupActivity):
    '''A text editor for Sugar
    pylint says I need a docstring. Here you go.
    '''

    message_preparing = _("Loading...")
    message_joining = _("Joining shared activity...")
    message_loading = _("Reading journal entry...")


    def checkts(self):
        '''Check the timestamp
        If someone's modified our file in an external editor,
        we should reload the contents
        '''

        mtime = self.metadata[mdnames.sugartimestamp_md]
        etime = self.metadata[mdnames.cloudtimestamp_md]
        return mtime > etime

    def __init__(self, handle):
        '''We want to set up the buffer et al. early on
        sure there's early_setup, but that's not early enough
        '''
        
        self.buffer = gtksourceview.Buffer()
        self.refresh_buffer = False
        
        self.text_view = gtksourceview.View(self.buffer)
        self.scrollwindow = gtk.ScrolledWindow()

        self.scrollwindow.add(self.text_view)

        sugar_tools.GroupActivity.__init__(self, handle)
        
    def fix_mimetype(self):
        '''We must have a mimetype. Sometimes, we don't (when we get launched
        newly.) This  fixes that.'''
        if self.metadata[mdnames.mimetype_md] == '':
            self.metadata[mdnames.mimetype_md] = "text/plain"
            #we MUST have a mimetype
            
    def setup_toolbar(self):
        '''Setup the top toolbar. Groupthink needs some work here.'''
        toolbar_box = ToolbarBox()
        
        activity_button = ActivityToolbarButton(self)
        toolbar_box.toolbar.insert(activity_button, 0)
        activity_button.show()
        
        self.edit_toolbar = EditToolbar()
        edit_toolbar_button = ToolbarButton(
            page=self.edit_toolbar,
            icon_name='toolbar-edit')
        self.edit_toolbar.show()
        toolbar_box.toolbar.insert(edit_toolbar_button, -1)
        edit_toolbar_button.show()

        self.edit_toolbar.undo.connect('clicked', self.undobutton_cb)
        self.edit_toolbar.redo.connect('clicked', self.redobutton_cb)
        self.edit_toolbar.copy.connect('clicked', self.copybutton_cb)
        self.edit_toolbar.paste.connect('clicked', self.pastebutton_cb)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)
        separator.show()

        
        stop_button = StopButton(self)
        stop_button.props.accelerator = '<Ctrl><Shift>Q'
        toolbar_box.toolbar.insert(stop_button, -1)
        stop_button.show()

        self.set_toolbar_box(toolbar_box)
        toolbar_box.show()
        
    def initialize_display(self):
        '''Set up GTK and friends'''
        self.fix_mimetype()

        self.cloud.shared_buffer = gtk_tools.TextBufferSharePoint(self.buffer)

        self.setup_toolbar()
        #Some graphics code borrowed from Pippy


        lang_manager = gtksourceview.language_manager_get_default()
        if hasattr(lang_manager, 'list_languages'):
            langs = lang_manager.list_languages()
        else:
            lang_ids = lang_manager.get_language_ids()
            langs = [lang_manager.get_language(lang_id) for lang_id in lang_ids]
            for lang in langs:
                for mtype in lang.get_mime_types():  
                    if mtype == self.metadata[mdnames.mimetype_md]:
                        self.buffer.set_language(lang)
                        break
        

        self.text_view.set_editable(True)
        self.text_view.set_cursor_visible(True)

        if self.metadata[mdnames.mimetype_md] == "text/plain":
            self.text_view.set_show_line_numbers(False)
            self.text_view.set_wrap_mode(gtk.WRAP_WORD)
            font = pango.FontDescription("Bitstream Vera Sans " + 
                str(style.FONT_SIZE))
        else:
            if hasattr(self.buffer,'set_highlight'):
                self.buffer.set_highlight(True)
            else:
                self.buffer.set_highlight_syntax(True)

            self.text_view.set_show_line_numbers(True)

            self.text_view.set_wrap_mode(gtk.WRAP_CHAR)
            self.text_view.set_insert_spaces_instead_of_tabs(True)
            self.text_view.set_tab_width(2)
            self.text_view.set_auto_indent(True)
            font = pango.FontDescription("Monospace " + 
                str(style.FONT_SIZE))

        self.text_view.modify_font(font)

        if self.refresh_buffer:
            #see load_from_journal()
            self.buffer.begin_not_undoable_action()
            self.buffer.set_text(self.refresh_buffer)
            self.buffer.end_not_undoable_action()
        
        self.text_view.show()

        #Return the main widget. our parents take care of GTK stuff
        return self.scrollwindow

    def save_to_journal(self, filename, cloudstring):
        '''Saves to the journal.
        We use metadata magic to keep the collab. stuff'''
        self.metadata[mdnames.cloudstring_md] = cloudstring

        #Also write to file:
        fhandle = open(filename, "w")

        bounds = self.buffer.get_bounds()
        text = self.buffer.get_text(bounds[0], bounds[1])
        
        fhandle.write(text)
        fhandle.close()

        self.fix_mimetype()

        #We can do full-text search on all Edit documents, yay
        self.metadata[mdnames.contents_md] = text
    
        #If we edit the file in another way, we need to reload the contents
        #we fudge the timestamp forwards by 5 seconds
        #mmmm, fudge
        self.metadata[mdnames.cloudtimestamp_md] = time.clock()+5

    def load_from_journal(self, filename):
        '''Load the file. Duh.'''


        if mdnames.cloudstring_md in self.metadata:
            if self.checkts():
                #if we were edited in another program
                #we need to reload the text
                #setting self.refresh_buffer makes us do that
                text = open(filename, "r").read() #yay hackish one-line read
                self.refresh_buffer = text

            #File has been saved with Edit, thus
            #load the fancy collaboration data
            #instead of just the text
            return self.metadata[mdnames.cloudstring_md]

        else:
            text = open(filename, "r").read() #yay hackish one-line read

            self.buffer.set_text(text)
            return None

    def when_shared(self):
        self._edit_toolbar.undo.set_sensitive(False)
        self._edit_toolbar.redo.set_sensitive(False)

    def undobutton_cb(self, button):
        if self.buffer.can_undo():
            self.buffer.undo()

    def redobutton_cb(self, button):
        global text_buffer
        if self.buffer.can_redo():
            self.buffer.redo()

    def copybutton_cb(self, button):
        self.buffer.copy_clipboard(gtk.Clipboard())

    def pastebutton_cb(self, button):
        self.buffer.paste_clipboard(gtk.Clipboard(), None, True)
