import time

from PyQt4.QtCore import QObject, pyqtSignal

from malcolm.gui.blockgui import BlockGui


class GuiOpener(QObject):
    open_gui_signal = pyqtSignal(object, object)

    def __init__(self):
        QObject.__init__(self)
        self.guis = {}
        self.open_gui_signal.connect(self._open_gui)

    def open_gui(self, block, process):
        self.open_gui_signal.emit(block, process)

    def _open_gui(self, block, process):
        if block not in self.guis:
            self.guis[block] = BlockGui(process, block)
            # If we don't sleep here we get a blank GUI, very strange...
            time.sleep(0.1)
        self.guis[block].show()
