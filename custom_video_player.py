import hashlib
import os
import weakref

from kivy.config import Config

# Must run before kivy.core.window is imported (the window reads it on creation).
# On Linux, Kivy's "probesysfs" provider treats laptop touchpads as touchscreens,
# so resting a finger on the touchpad sends stray taps that play/pause the video.
if Config.has_option("input", "%(name)s"):
    Config.remove_option("input", "%(name)s")
# Plain mouse input; also stops right-click from drawing multitouch red dots.
Config.set("input", "mouse", "mouse,disable_multitouch")

from kivy.animation import Animation  # noqa: E402  (after the Config tweak)
from kivy.clock import Clock, mainthread
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics.texture import Texture
from kivy.lang import Builder
from kivy.loader import Loader
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import (
    BooleanProperty,
    ColorProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.image import Image
from kivy.uix.videoplayer import VideoPlayer
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel

# SDL key codes used by the keyboard shortcuts.
KEY_ESCAPE = 27
KEY_SPACE = 32
KEY_F = 102
KEY_M = 109
KEY_RIGHT = 275
KEY_LEFT = 276
KEY_DOWN = 274
KEY_UP = 273

SEEK_STEP = 5  # seconds skipped with the left/right arrow keys
VOLUME_STEP = 0.1  # volume change with the up/down arrow keys


def format_time(seconds):
    """Format seconds as ``m:ss`` (or ``h:mm:ss`` for long videos)."""
    minutes, seconds = divmod(int(max(0, seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, seconds)
    return "%d:%02d" % (minutes, seconds)


_gradient_texture = None


def get_gradient_texture():
    """1px-wide texture fading from translucent black (bottom) to clear (top)."""
    global _gradient_texture
    if _gradient_texture is None:
        rows = 64
        buf = bytearray()
        for row in range(rows):  # row 0 is the bottom of the texture
            alpha = int(255 * 0.75 * (1 - row / (rows - 1)) ** 1.5)
            buf += bytes((0, 0, 0, alpha))
        tex = Texture.create(size=(1, rows), colorfmt="rgba")
        tex.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
        _gradient_texture = tex
    return _gradient_texture


class PlayerContainer(MDFloatLayout):
    """Holds the video (or thumbnail) texture."""


class PlayerButtonBox(MDBoxLayout):
    """
    Control bar overlaid on the bottom of the video: a full-width seek bar
    above a row with Play/Stop/Volume/Time/Full screen.
    """

    video = ObjectProperty()  # CustomVideoPlayer object
    gradient_texture = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gradient_texture = get_gradient_texture()


# ****************************** Progress bar ********************************
class ProgressBarVideo(Widget):
    """
    Lightweight seek bar.

    Draws plain rectangles (see the .kv rule) instead of the KivyMD progress
    indicator, whose anti-aliased rounded rectangles were rebuilt on every
    video frame. Supports click and drag to seek; the actual (expensive)
    seek only happens once, when the touch is released.

    While the mouse hovers over it the bar thickens, shows a handle, a
    lighter "preview" fill up to the cursor and a tooltip with the time
    under the cursor.
    """

    video = ObjectProperty(None, allownone=True)  # CustomVideoPlayer object
    value_normalized = NumericProperty(0.0)  # playback progress, 0..1
    hover_value = NumericProperty(0.0)  # cursor position along the bar, 0..1
    hover_text = StringProperty("")
    hovered = BooleanProperty(False)
    dragging = BooleanProperty(False)
    bar_height = NumericProperty(dp(4))
    track_color = ColorProperty([1, 1, 1, 0.3])
    indicator_color = ColorProperty([1, 1, 1, 1])

    def on_video(self, instance, video):
        if video is not None:
            video.fbind("position", self._sync_with_video)
            video.fbind("duration", self._sync_with_video)
            self._sync_with_video()

    def _sync_with_video(self, *args):
        if self.dragging:
            return  # the user is scrubbing: don't fight them
        duration = self.video.duration
        value = min(1.0, max(0.0, self.video.position / duration)) if duration > 0 else 0.0
        # Skip sub-pixel changes so the canvas isn't touched on every frame.
        if abs(value - self.value_normalized) * self.width >= 1 or value in (0.0, 1.0):
            self.value_normalized = value

    # ---------------------------- hover ----------------------------------
    def on_hovered(self, instance, value):
        self._animate_thickness()

    def on_dragging(self, instance, value):
        self._animate_thickness()

    def _animate_thickness(self):
        target = dp(6) if (self.hovered or self.dragging) else dp(4)
        Animation.cancel_all(self, "bar_height")
        Animation(bar_height=target, d=0.12).start(self)

    def _set_hover_x(self, x):
        if self.width <= 0:
            return
        self.hover_value = (max(self.x, min(self.right, x)) - self.x) / self.width
        if self.video and self.video.duration > 0:
            text = format_time(self.hover_value * self.video.duration)
        else:
            text = ""
        if text != self.hover_text:  # only re-render the tooltip when needed
            self.hover_text = text

    def update_hover(self, window_pos, enabled=True):
        """Called by the player with every mouse move (window coordinates)."""
        x, y = self.to_widget(*window_pos)
        self.hovered = bool(enabled and self.collide_point(x, y))
        if self.hovered:
            self._set_hover_x(x)

    # ---------------------------- seeking --------------------------------
    def _preview(self, x):
        self._set_hover_x(x)
        self.value_normalized = self.hover_value
        if self.video:
            self.video.set_time(self.value_normalized * self.video.duration)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or not self.video or self.video.duration <= 0:
            return False
        touch.grab(self)
        self.dragging = True
        self._preview(touch.x)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._preview(touch.x)
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._preview(touch.x)
        self.video.seek(self.value_normalized)
        self.dragging = False
        return True


# ************************* Custom control buttons ***************************
class BasePlayerButton(MDIconButton):
    """Basic button for video player buttons (styling in the .kv rule)."""

    video = ObjectProperty()  # CustomVideoPlayer object


class ButtonVideoStop(BasePlayerButton):
    def on_release(self, *args):
        self.video.state = "stop"
        self.video.position = 0  # resets the progress bar and time label
        return True


class ButtonVideoPlayPause(BasePlayerButton):
    def on_release(self, *args):
        self.video.toggle_play()
        return True


class ButtonVideoVolume(BasePlayerButton):
    def on_release(self, *args):
        self.video.toggle_mute()
        return True


class ButtonVideoFullScreen(BasePlayerButton):
    def on_release(self, *args):
        self.video.full_screen = not self.video.full_screen
        return True


class CustomVideoPlayer(VideoPlayer):
    """
    Custom video player.

    Mouse: click the video to play/pause, double-click for full screen.
    Keyboard (for the player last hovered/clicked, or the full-screen one):
    Space play/pause, Left/Right seek 5 s, Up/Down volume, M mute,
    F full screen, Escape leave full screen.
    """

    full_screen = BooleanProperty(False)
    title = None
    aspect_ratio = NumericProperty(1.0)
    should_cache = BooleanProperty(False)
    disable_full_screen = BooleanProperty(True)

    HIDE_CONTROLS_AFTER = 3  # seconds of mouse inactivity while playing

    # The player keyboard shortcuts apply to (weak reference).
    _active_player = None

    def __init__(self, **kwargs):
        self.video_ended = False
        self.original_parent = None
        self._controls_visible = True
        self._last_time_text = None
        self._window_bound = False
        self._volume_before_mute = 1.0
        # One reusable trigger instead of unschedule/schedule on every mouse move.
        self._hide_trigger = Clock.create_trigger(self._auto_hide, self.HIDE_CONTROLS_AFTER)
        # Kivy's Video defaults to "scale-down", which never enlarges a video
        # smaller than the player; "contain" scales it to fit, keeping its ratio.
        kwargs["options"] = {"fit_mode": "contain", **kwargs.get("options", {})}
        super().__init__(**kwargs)
        self.fbind("thumbnail", self.load_cached_thumbnail)
        self.fbind("state", self.handle_state_change)
        # Only refresh the time label when the displayed second changes.
        self.fbind("position", self._on_position)
        self.fbind("duration", self._on_position)
        if CustomVideoPlayer._active_player is None:
            self._make_active()
        self._update_center_icon(self.state, flash=False)

    # ------------------------ window bindings ----------------------------
    def on_parent(self, instance, parent):
        # Only listen to window events while we're actually on screen, so a
        # removed player doesn't keep reacting to every mouse move / key.
        self._bind_window(parent is not None)

    def _bind_window(self, bind):
        if bind == self._window_bound:
            return
        self._window_bound = bind
        if bind:
            Window.fbind("mouse_pos", self.mouse_pos_handler)
            Window.fbind("on_key_down", self.keyboard_on_key_down)
            Window.fbind("on_cursor_leave", self.on_cursor_leave_window)
        else:
            Window.funbind("mouse_pos", self.mouse_pos_handler)
            Window.funbind("on_key_down", self.keyboard_on_key_down)
            Window.funbind("on_cursor_leave", self.on_cursor_leave_window)

    def on_cursor_leave_window(self, *args):
        # Kivy stops reporting mouse_pos once the cursor is outside the window,
        # so the last position seen may still be inside the player (often over
        # the control bar, where auto-hide is paused). Treat leaving the window
        # as leaving the player.
        self.ids.button_box.ids.progress_bar.hovered = False
        if self.state == "play" and not self.ids.button_box.ids.progress_bar.dragging:
            self._hide_trigger.cancel()
            self.hide_button_box()

    def _make_active(self):
        CustomVideoPlayer._active_player = weakref.ref(self)

    def _is_active(self):
        ref = CustomVideoPlayer._active_player
        return self.full_screen or (ref is not None and ref() is self)

    # --------------------------- keyboard --------------------------------
    @staticmethod
    def _text_input_focused():
        keyboard = getattr(Window, "_system_keyboard", None)
        return keyboard is not None and keyboard.target is not None

    def keyboard_on_key_down(self, window, key, scancode, codepoint, modifiers, *args):
        if key == KEY_ESCAPE and self.full_screen:
            self.full_screen = False
            return True
        if not self._is_active() or self._text_input_focused() or modifiers:
            return False

        if key == KEY_SPACE:
            self.toggle_play()
        elif key == KEY_LEFT:
            self.seek_by(-SEEK_STEP)
        elif key == KEY_RIGHT:
            self.seek_by(SEEK_STEP)
        elif key == KEY_UP:
            self.volume = min(1.0, self.volume + VOLUME_STEP)
        elif key == KEY_DOWN:
            self.volume = max(0.0, self.volume - VOLUME_STEP)
        elif key == KEY_M:
            self.toggle_mute()
        elif key == KEY_F:
            self.full_screen = not self.full_screen
        else:
            return False
        self._poke_controls()
        return True

    # ---------------------------- actions --------------------------------
    def toggle_play(self):
        self.state = "pause" if self.state == "play" else "play"

    def toggle_mute(self):
        if self.volume > 0:
            self._volume_before_mute = self.volume
            self.volume = 0
        else:
            self.volume = self._volume_before_mute or 1.0

    def seek_by(self, seconds):
        if self.duration > 0:
            target = min(max(self.position + seconds, 0), self.duration)
            self.seek(target / self.duration)

    # ----------------------------- mouse ---------------------------------
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._make_active()
        box = self.ids.button_box
        if self._controls_visible and box.collide_point(*touch.pos):
            box.dispatch("on_touch_down", touch)
            return True  # don't toggle playback when clicking the control bar
        if touch.is_mouse_scrolling:
            return False
        if touch.is_double_tap:
            self.toggle_play()  # undo the toggle from the first click
            self.full_screen = not self.full_screen
        else:
            self.toggle_play()
        self._poke_controls()
        return True

    def mouse_pos_handler(self, window_sdl, mouse_pos):
        """
        Track the position of the mouse cursor.

        This fires for every mouse-motion event (hundreds per second), so it
        must stay cheap: animations only start when visibility actually
        changes, and the auto-hide timer is a reusable trigger.
        """
        if self.get_root_window() is None:
            return
        local_pos = self.to_widget(*mouse_pos)
        inside = self.collide_point(*local_pos)
        box = self.ids.button_box
        box.ids.progress_bar.update_hover(mouse_pos, enabled=inside and self._controls_visible)

        if inside:
            self._make_active()
        if self.state == "play":
            if inside:
                self.show_button_box()
                self._hide_trigger.cancel()
                if not box.collide_point(*local_pos):  # keep open while over controls
                    self._hide_trigger()
            else:
                self._hide_trigger.cancel()
                self.hide_button_box()
        elif inside or self.state == "pause":
            self.show_button_box()

    def _poke_controls(self):
        """Show the controls and restart the auto-hide timer."""
        self.show_button_box()
        self._hide_trigger.cancel()
        if self.state == "play":
            self._hide_trigger()

    def _auto_hide(self, *args):
        if self.state == "play" and not self.ids.button_box.ids.progress_bar.dragging:
            self.hide_button_box()

    # ---------------------------- state ----------------------------------
    def handle_state_change(self, instance, value):
        """Handle video state change."""
        if value == "stop":
            self.video_ended = True
            if self.thumbnail and self._video:
                self._video.set_texture_from_resource(self.thumbnail)
        else:
            self.video_ended = False

        self._update_center_icon(value, flash=True)
        self._hide_trigger.cancel()
        if value == "play":
            self._hide_trigger()
        else:
            self.show_button_box()  # keep the controls visible while paused / stopped

    def _update_center_icon(self, state, flash):
        """Big icon in the middle: always shown when stopped, flashed on play/pause."""
        icon = self.ids.center_icon
        Animation.cancel_all(icon)
        if state == "stop":
            icon.icon = "play"
            icon.opacity = 1
        elif flash:
            icon.icon = "play" if state == "play" else "pause"
            icon.opacity = 1
            Animation(opacity=0, d=0.6, t="in_quad").start(icon)
        else:
            icon.opacity = 0

    def _load_thumbnail(self, thumbnail):
        # Replaces Kivy's VideoPlayerPreview (dimmed image + its own play
        # overlay) with a plain image; our center icon does the overlay.
        if not self.container:
            return
        self.container.clear_widgets()
        if thumbnail:
            self._image = Image(source=thumbnail, fit_mode="contain", pos_hint={"x": 0, "y": 0})
            self.container.add_widget(self._image)

    # --------------------------- controls --------------------------------
    def _animated_widgets(self):
        widgets = [self.ids.button_box]
        if self.title is not None:
            widgets.append(self.title)
        return widgets

    def show_button_box(self, *args):
        """Fades in the control bar (it overlays the video, so no relayout)."""
        if self._controls_visible:
            return
        self._controls_visible = True
        for widget in self._animated_widgets():
            Animation.cancel_all(widget, "opacity")
            Animation(opacity=1, d=0.2).start(widget)

    def hide_button_box(self, *args):
        """Fades out the control bar."""
        if not self._controls_visible:
            return
        self._controls_visible = False
        self.ids.button_box.ids.progress_bar.hovered = False
        for widget in self._animated_widgets():
            Animation.cancel_all(widget, "opacity")
            Animation(opacity=0, d=0.3).start(widget)

    def _on_position(self, *args):
        if not self.ids.button_box.ids.progress_bar.dragging:
            self.set_time(self.position)

    def set_time(self, position=None):
        """Sets the timeline label (``current / total``) of the playback."""
        if position is None:
            position = self.position
        if self.duration > 0:
            text = "%s / %s" % (format_time(position), format_time(self.duration))
        else:  # e.g. webm videos with unknown duration
            text = format_time(position)
        # Re-rendering a label texture is expensive: skip if nothing changed.
        if text != self._last_time_text:
            self._last_time_text = text
            self.ids.button_box.ids.time.text = text

    def add_file_name_label(self, *args):
        """Adds a label with the path of the file being played."""
        if not self.title:
            self.title = MDLabel(
                text=self.source,
                pos_hint={"top": 0.93},
                bold=True,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color="white",
                x=dp(24),
                opacity=1 if self._controls_visible else 0,
            )
        # Added to the overlay layer: the video container is cleared when
        # playback starts, which used to remove the title.
        if self.title.parent is None:
            self.ids.stage.add_widget(self.title, index=1)

    def on_full_screen(self, instance, value):
        if not self.disable_full_screen:
            return

        def on_full_screen_complete(*args):
            self.full_screen = value

        if value:
            self.original_parent = self.parent
            self.parent.remove_widget(self)
            Window.add_widget(self)
            Window.fullscreen = "auto"
            anim = Animation(size=Window.size, pos=(0, 0), d=0.2)
        else:
            Window.fullscreen = False
            Window.remove_widget(self)
            if self.original_parent:
                self.original_parent.add_widget(self)
            anim = Animation(d=0.2)

        anim.bind(on_complete=on_full_screen_complete)
        anim.start(self)

    # ---------------------------- caching --------------------------------
    @staticmethod
    def cache_thumbnail(url):
        app_name = MDApp.get_running_app().name
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", app_name)
        os.makedirs(cache_dir, exist_ok=True)
        Logger.info(f"CACHE_DIR: {cache_dir}")
        head, _ = os.path.split(url)
        if os.path.basename(head) == app_name:
            return url
        filename = hashlib.md5(url.encode("utf-8")).hexdigest() + ".png"
        return os.path.join(cache_dir, filename)

    def load_cached_thumbnail(self, instance, url):
        if not self.should_cache or not url:
            return

        file_path = self.cache_thumbnail(url)
        if os.path.isfile(file_path):
            self.thumbnail = file_path
            texture = CoreImage(file_path).texture
            self.aspect_ratio = texture.width / float(texture.height)
            return

        @mainthread
        def save_to_cache(proxy_image, *args):
            texture = proxy_image.image.texture
            if texture:
                CoreImage(texture).save(file_path)
                self.thumbnail = file_path
                self.aspect_ratio = texture.width / float(texture.height)

        Loader.image(url).bind(on_load=save_to_cache)


Builder.load_file(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "custom_video_player.kv")
)


class TestVideoPlayer(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        video_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "video_files")
        root = CustomVideoPlayer()
        root.source = os.path.join(video_dir, "video_file.mp4")
        root.thumbnail = os.path.join(video_dir, "thumbnail.png")
        return root


if __name__ == "__main__":
    TestVideoPlayer().run()
