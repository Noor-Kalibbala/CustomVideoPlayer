import hashlib
import os

from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.loader import Loader
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty
from kivy.uix.videoplayer import VideoPlayer
from kivymd.app import MDApp
from kivymd.uix.button import MDIconButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator  # was MDProgressBar

ESCAPE = 27


class PlayerContainer(MDFloatLayout):
    pass


class PlayerButtonBox(MDGridLayout):
    """
    Container for the control buttons of the video player:
    Stop/Play/Full screen/Volume and Progress sliders.
    """

    video = ObjectProperty()  # CustomVideoPlayer object


# ****************************** Progress bar ********************************
class ProgressBarVideo(MDLinearProgressIndicator):
    video = ObjectProperty()  # CustomVideoPlayer object

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._update_seek(touch.x)
        return True

    def _update_seek(self, x):
        if self.width == 0:
            return
        x = max(self.x, min(self.right, x)) - self.x
        self.video.seek(x / float(self.width))


# ************************* Custom control buttons ***************************
class BasePlayerButton(MDIconButton):
    """Basic button for video player buttons (styling in the .kv rule)."""

    video = ObjectProperty()  # CustomVideoPlayer object


class ButtonVideoStop(BasePlayerButton):
    def on_release(self, *args):
        self.video.state = "stop"
        self.video.position = 0
        return True


class ButtonVideoPlayPause(BasePlayerButton):
    def on_release(self, *args):
        self.video.state = "pause" if self.video.state == "play" else "play"
        return True


class ButtonVideoVolume(BasePlayerButton):
    current_volume = NumericProperty(1.0)  # volume to restore on unmute

    def on_release(self, *args):
        if self.video.volume > 0:
            self.current_volume = self.video.volume
            self.video.volume = 0
        else:
            self.video.volume = self.current_volume or 1.0
        return True


class ButtonVideoFullScreen(BasePlayerButton):
    def on_release(self, *args):
        self.video.full_screen = not self.video.full_screen
        return True


class CustomVideoPlayer(VideoPlayer):
    """Custom video player."""

    full_screen = BooleanProperty(False)
    title = None
    aspect_ratio = NumericProperty(1.0)
    should_cache = BooleanProperty(False)
    disable_full_screen = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(thumbnail=self.load_cached_thumbnail)
        self.bind(state=self.handle_state_change)
        Window.bind(mouse_pos=self.mouse_pos_handler)
        Window.bind(on_key_down=self.keyboard_on_key_down)
        self.video_ended = False

    def keyboard_on_key_down(self, window, key, scancode, codepoint, modifiers, *args):
        """Exit full screen on Escape."""
        if key == ESCAPE and self.full_screen:
            self.full_screen = False
            return True
        return False

    @mainthread
    def mouse_pos_handler(self, window_sdl, mouse_pos):
        """Track the position of the mouse cursor."""
        local_pos = self.to_widget(*mouse_pos)
        inside_video_player = self.collide_point(*local_pos)

        if self.state == "play" and inside_video_player:
            Clock.unschedule(self.hide_button_box)
            self.show_button_box()
            Clock.schedule_once(self.hide_button_box, 5)
        elif self.state == "play" and not inside_video_player:
            Clock.unschedule(self.hide_button_box)
            self.hide_button_box()
        elif self.video_ended and inside_video_player:
            self.show_button_box()
        elif self.state == "pause":
            self.show_button_box()

    def handle_state_change(self, instance, value):
        """Handle video state change."""
        if value == "stop":
            self.video_ended = True
            if self.thumbnail and self._video:
                self._video.set_texture_from_resource(self.thumbnail)
        else:
            self.video_ended = False

    def _button_box_instances(self):
        box = self.ids.button_box
        instances = [
            box.ids.btn_stop,
            box.ids.btn_play_pause,
            box.ids.btn_full_screen,
            box.ids.volume_container,
            box.ids.time,
            box.ids.btn_volume,
            self.title,
        ]
        return [i for i in instances if i is not None]

    def show_button_box(self, *args):
        """Shows the container with the control box of the player."""

        def add_button_box(*args):
            self.ids.button_box.height = dp(56)
            self.ids.button_box.opacity = 1.0

        for instance in self._button_box_instances():
            Animation(opacity=1, d=0.2).start(instance)

        anim = Animation(opacity=1, d=0.2)
        anim.bind(on_complete=add_button_box)
        anim.start(self.ids.button_box.ids.progress_container)

    def hide_button_box(self, *args):
        """Hides the container with the control box of the player."""

        def remove_button_box(*args):
            self.ids.button_box.height = 0
            self.ids.button_box.opacity = 0.0

        for instance in self._button_box_instances():
            Animation(opacity=0, d=0.2).start(instance)

        anim = Animation(opacity=0, d=0.2)
        anim.bind(on_complete=remove_button_box)
        anim.start(self.ids.button_box.ids.progress_container)

    def set_time(self):
        """Sets the timeline of the current playback."""
        if self.duration == 0:  # for webm videos
            return
        minutes, seconds = divmod(int(self.position), 60)
        self.ids.button_box.ids.time.text = "%d:%02d" % (minutes, seconds)

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
                x=dp(24),  # was the string "24dp", which only works in kv
            )
        self.ids.container.add_widget(self.title)

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