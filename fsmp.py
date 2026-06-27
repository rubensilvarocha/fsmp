#!/usr/bin/env python3
import sys
import os
import subprocess
import random
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

class FFplayGTKPlaylistPlayer(Gtk.Window):
    def __init__(self):
        super().__init__(title="FSMP - Fucking Simple Music Player")
        self.set_border_width(15)
        self.set_default_size(500, 400)
        
        # Player state
        self.playlist = []
        self.current_index = -1
        self.ffplay_process = None
        self.active_filter = "anull"
        self.shuffle_enabled = False

        self.filters = {
            "Normal": "loudnorm=I=-16:TP=-1.5:LRA=11",
            "Fucking Great Sound": "extrastereo=m=2, loudnorm=I=-16:TP=-1.5:LRA=11",
            }

        # Main Layout (Vertical Box)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # 1. Top Control Bar (Browse & FX)
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        btn_browse = Gtk.Button(label="📁 Add Files")
        btn_browse.connect("clicked", self.on_file_browse)
        
        btn_clear = Gtk.Button(label="🗑️ Clear Queue")
        btn_clear.connect("clicked", self.on_clear_playlist)
        
        self.filter_combo = Gtk.ComboBoxText()
        for name in self.filters.keys():
            self.filter_combo.append_text(name)
        self.filter_combo.set_active(0)
        self.filter_combo.connect("changed", self.on_filter_changed)

        top_bar.pack_start(btn_browse, False, False, 0)
        top_bar.pack_start(btn_clear, False, False, 0)
        top_bar.pack_end(self.filter_combo, True, True, 0)
        vbox.pack_start(top_bar, False, False, 0)

        # 2. Playlist UI Display (ListStore & TreeView)
        self.listmodel = Gtk.ListStore(str, str) # columns: Status icon/text, Filename
        self.treeview = Gtk.TreeView(model=self.listmodel)
        self.treeview.connect("row-activated", self.on_row_activated)
        
        renderer_status = Gtk.CellRendererText()
        column_status = Gtk.TreeViewColumn("", renderer_status, text=0)
        column_status.set_min_width(40)
        self.treeview.append_column(column_status)

        renderer_name = Gtk.CellRendererText()
        column_name = Gtk.TreeViewColumn("Queue Tracks", renderer_name, text=1)
        self.treeview.append_column(column_name)

        # Wrap treeview inside a scrollable pane
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.treeview)
        vbox.pack_start(scroller, True, True, 0)

        # 3. Bottom Playback Row
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        control_box.set_halign(Gtk.Align.CENTER)
        
        btn_prev = Gtk.Button(label="⏮️")
        self.btn_play = Gtk.Button(label="▶️ Play")
        btn_next = Gtk.Button(label="⏭️")
        self.btn_shuffle = Gtk.ToggleButton(label="🔀 Shuffle")
        
        btn_prev.connect("clicked", self.on_prev_clicked)
        self.btn_play.connect("clicked", self.on_play_clicked)
        btn_next.connect("clicked", self.on_next_clicked)
        self.btn_shuffle.connect("toggled", self.on_shuffle_toggled)
        
        control_box.pack_start(btn_prev, False, False, 0)
        control_box.pack_start(self.btn_play, False, False, 0)
        control_box.pack_start(btn_next, False, False, 0)
        control_box.pack_start(self.btn_shuffle, False, False, 0)
        vbox.pack_start(control_box, False, False, 5)

        # Separator Line for the footer
        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 5)

        # 4. Footer Credits Row
        footer_label = Gtk.Label()
        footer_label.set_markup("<span foreground='#888888' size='small'>Great Music needs Great Sound - Created by Ruben Rocha - v0.1</span>")
        footer_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(footer_label, False, False, 0)

        # Setup periodic poll checker loop inside GLib background
        GLib.timeout_add(500, self.check_playback_status)
        self.connect("destroy", self.on_destroy)        
        
        # Setup periodic poll checker loop inside GLib background
        GLib.timeout_add(500, self.check_playback_status)
        self.connect("destroy", self.on_destroy)

    def on_file_browse(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Select Audio Files", parent=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )
        dialog.set_select_multiple(True)
        
        filter_audio = Gtk.FileFilter()
        filter_audio.set_name("Audio files")
        filter_audio.add_mime_type("audio/*")
        dialog.add_filter(filter_audio)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filenames = dialog.get_filenames()
            for f in sorted(filenames):
                self.playlist.append(f)
                self.listmodel.append(["", os.path.basename(f)])
            
            # Auto-target first added song if nothing is active
            if self.current_index == -1 and len(self.playlist) > 0:
                self.current_index = 0
                self.update_ui_markers()

        dialog.destroy()

    def on_clear_playlist(self, widget):
        self.stop_playback()
        self.playlist = []
        self.listmodel.clear()
        self.current_index = -1
        self.btn_play.set_label("▶️ Play")

    def on_row_activated(self, treeview, path, column):
        self.current_index = path.get_indices()[0]
        self.play_current_track()

    def on_filter_changed(self, combo):
        selected_text = combo.get_active_text()
        self.active_filter = self.filters[selected_text]
        if self.ffplay_process:
            self.play_current_track()

    def on_shuffle_toggled(self, button):
        self.shuffle_enabled = button.get_active()

    def play_current_track(self):
        self.stop_playback()
        if not (0 <= self.current_index < len(self.playlist)):
            return

        self.update_ui_markers()
        track_path = self.playlist[self.current_index]
        
        cmd = [
            "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
            "-af", self.active_filter, track_path
        ]
        
        try:
            self.ffplay_process = subprocess.Popen(cmd)
            self.btn_play.set_label("■ Stop")
        except Exception as e:
            print(f"Error launching playback backend: {e}")

    def stop_playback(self):
        if self.ffplay_process:
            self.ffplay_process.terminate()
            self.ffplay_process.wait()
            self.ffplay_process = None
        self.btn_play.set_label("▶️ Play")

    def on_play_clicked(self, widget):
        if len(self.playlist) == 0:
            return
        
        if self.ffplay_process:
            # Simple wrapper to act as stop/pause hook
            self.stop_playback()
        else:
            if self.current_index == -1:
                self.current_index = 0
            self.play_current_track()

    def on_next_clicked(self, widget):
        if len(self.playlist) == 0:
            return
        
        if self.shuffle_enabled:
            self.current_index = random.randint(0, len(self.playlist) - 1)
        else:
            self.current_index = (self.current_index + 1) % len(self.playlist)
        self.play_current_track()

    def on_prev_clicked(self, widget):
        if len(self.playlist) == 0:
            return
        self.current_index = (self.current_index - 1) % len(self.playlist)
        self.play_current_track()

    def update_ui_markers(self):
        for idx, row in enumerate(self.listmodel):
            if idx == self.current_index:
                row[0] = "▶️"
            else:
                row[0] = ""

    def check_playback_status(self):
        # Periodically executed by GLib engine loop
        if self.ffplay_process:
            poll = self.ffplay_process.poll()
            if poll is not None: # Background instance finished playing naturally
                self.ffplay_process = None
                self.on_next_clicked(None)
        return True # Keep running hook active

    def on_destroy(self, widget):
        self.stop_playback()
        Gtk.main_quit()

if __name__ == "__main__":
    app = FFplayGTKPlaylistPlayer()
    app.show_all()
    Gtk.main()
