from kivy.logger import Logger
from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.loader import Loader
from kivy.metrics import sp, dp
from kivy.properties import ObjectProperty, BooleanProperty, NumericProperty
from kivy.uix.videoplayer import VideoPlayer
from kivymd.app import MDApp
from kivy.core.window import Keyboard
from kivymd.uix.button import MDIconButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.progressbar import MDProgressBar
from kivy.core.image import Image as CoreImage
import hashlib
import os
from kivy.lang import Builder

# Get the absolute path of the directory of the current file
dir_path = os.path.dirname(os.path.realpath(__file__))

# Construct the absolute path of the .kv file
kv_path = os.path.join(dir_path, 'custom_video_player.kv')

# Load the .kv file using its absolute path
Builder.load_file(kv_path)


class PlayerContainer(MDFloatLayout):
    pass


class PlayerButtonBox(MDGridLayout):
    """
    Implements a container for the control buttons of the video player:
    Stop/Play/Full screen/Volume and Progress sliders.
    """

    video = ObjectProperty()  # CustomVideoPlayer object


# **********************************Custom Slider****************************
class ProgressBarVideo(MDProgressBar):
    video = ObjectProperty()  # CustomVideoPlayer object

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return
        self._update_seek(touch.x)

    def _update_seek(self, x):
        if self.width == 0:
            return
        x = max(self.x, min(self.right, x)) - self.x
        self.video.seek(x / float(self.width))


# ***************************** Custom control buttons
class BasePlayerButton(MDIconButton):
    """Implements a basic button for video player buttons."""

    video = ObjectProperty()  # 'CustomVideoPlayer" object
    # Default property button.
    theme_icon_color = "Custom"
    icon_color = "white"
    icon_size = sp(16)


class ButtonVideoStop(BasePlayerButton):
    def on_release(self, *args):
        self.video.state = 'stop'
        self.video.position = 0
        return True


class ButtonVideoPlayPause(BasePlayerButton):
    def on_release(self, *args):
        self.video.state = "pause" if self.video.state == "play" else "play"
        return True


class ButtonVideoVolume(BasePlayerButton):
    current_volume = NumericProperty()
    """
    Saves the current volume
    """

    def on_release(self, *args):
        if self.video.volume > 0:
            self.current_volume = self.video.volume
            self.video.volume = 0
        else:
            self.video.volume = self.current_volume
        return True


class ButtonVideoFullScreen(BasePlayerButton):
    def on_release(self, *args):
        if not self.video.full_screen:
            self.video.full_screen = True
        else:
            self.video.full_screen = False
        return True


class CustomVideoPlayer(VideoPlayer):
    """Implements a custom video player"""
    full_screen = BooleanProperty(False)
    title = None
    aspect_ratio = NumericProperty(1.0)
    should_cache = BooleanProperty(False)
    disable_full_screen = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(thumbnail=self.load_cached_thumbnail)
        Window.bind(mouse_pos=self.mouse_pos_handler)
        self.bind(state=self.handle_state_change)
        Window.bind(on_key_down=self.keyboard_on_key_down)
        self.video_ended = False

        # Clock.schedule_once(self.add_file_name_label)

    def keyboard_on_key_down(self, window, keycode, scancode, key_str, modifiers, *args):
        """Handle keyboard events."""
        try:
            if isinstance(keycode, int):
                key = keycode
            else:
                key, key_str = keycode

            if key == 27 and self.full_screen:  # Escape key has a keycode of 27
                self.full_screen = False
                return True
        except Exception as e:
            print(f"Error in keyboard_on_key_down: {e}")
        return False

    @mainthread
    def mouse_pos_handler(self, window_sdl, mouse_pos):
        """Track the position of the mouse cursor"""
        # convert the mouse_pos from window coordinates to local widget coordinates
        local_pos = self.to_widget(*mouse_pos)

        # Check if the cursor is inside the CustomVideoPlayer
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

    def show_button_box(self, *args):
        """ Shows the container with the control box of the player."""

        def add_button_box(*args):
            self.ids.button_box.height = dp(56)
            self.ids.button_box.opacity = 1.0

        button_box = self.ids.button_box

        instances = [
            button_box.ids.btn_stop,
            button_box.ids.btn_play_pause,
            button_box.ids.btn_full_screen,
            button_box.ids.volume_container,
            button_box.ids.time,
            button_box.ids.btn_volume,
            self.title,
        ]

        for instance in instances:
            if instance is not None:  # Filter out None values
                Animation(opacity=1, d=0.2).start(instance)

        anim = Animation(opacity=1, d=0.2)
        anim.bind(on_complete=add_button_box)
        anim.start(button_box.ids.progress_container)

    def hide_button_box(self, *args):
        """ Hides the container with the control box of the player """

        def remove_button_box(*args):
            self.ids.button_box.height = 0
            self.ids.button_box.opacity = 0.

        button_box = self.ids.button_box

        instances = [
            button_box.ids.btn_stop,
            button_box.ids.btn_play_pause,
            button_box.ids.btn_full_screen,
            button_box.ids.volume_container,
            button_box.ids.time,
            button_box.ids.btn_volume,
            self.title,
        ]

        for instance in instances:
            if instance is not None:  # Filter out None values
                Animation(opacity=0, d=0.2).start(instance)

        anim = Animation(opacity=0, d=0.2)
        anim.bind(on_complete=remove_button_box)
        anim.start(button_box.ids.progress_container)

    def set_time(self):
        """Sets the timeline of the current playback."""

        if self.duration == 0:  # for webm videos
            return
        seek = self.position / self.duration
        d = self.duration * seek
        minutes = int(d / 60)
        seconds = int(d - minutes * 60)
        self.ids.button_box.ids.time.text = "%d:%02d" % (minutes, seconds)

    def add_file_name_label(self, *args):
        """
        Adds a label to the frame stream with the path to the file that is being played.
        :param args:
        :return:
        """
        if not self.title:
            self.title = MDLabel(
                text=self.source,
                pos_hint={"top": 0.93},
                bold=True,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color="white",
                x="24dp", )
        self.ids.container.add_widget(self.title)

    def on_full_screen(self, instance, value):
        if self.disable_full_screen:
            def on_full_screen_complete(*args):
                self.full_screen = value
                self.allow_stretch = value

            if value:
                self.original_parent = self.parent  # Store the original parent
                self.parent.remove_widget(self)
                Window.add_widget(self)
                Window.fullscreen = "auto"
                anim = Animation(
                    size=Window.size,
                    pos=(0, 0),
                    d=0.2
                )
            else:
                Window.fullscreen = False
                Window.remove_widget(self)
                if self.original_parent:  # Check if original_parent is not None
                    self.original_parent.add_widget(self)
                anim = Animation(
                    # size=self.original_parent.size,
                    # pos=self.original_parent.pos,
                    d=0.2
                )

            anim.bind(on_complete=on_full_screen_complete)
            anim.start(self)

    def _play_started(self, instance, value):
        """
        Override the video player method.Adds Label to the frame stream with the path to the file that is being played.
        :param instance:
        :param value:
        :return:
        """
        super()._play_started(instance, value)
        # self.add_file_name_label()

    @staticmethod
    def cache_thumbnail(url):
        app_name = MDApp.get_running_app().name
        CACHE_DIR = os.path.join(os.path.expanduser("~"), '.cache', app_name)
        os.makedirs(CACHE_DIR, exist_ok=True)
        Logger.info(f"CACHE_DIR: {CACHE_DIR}")  # Logging the CACHE_DIR
        head, tail = os.path.split(url)
        app_basename = os.path.basename(head)

        if app_basename == app_name:
            return url
        filename = hashlib.md5(url.encode('utf-8')).hexdigest() + '.png'
        file_path = os.path.join(CACHE_DIR, filename)

        return file_path

    def load_cached_thumbnail(self, instance, url):
        if not self.should_cache:
            return

        file_path = self.cache_thumbnail(url)
        if os.path.isfile(file_path):
            self.thumbnail = file_path
            img = CoreImage(file_path)
            self.aspect_ratio = img.texture.width / float(img.texture.height)

        else:
            @mainthread
            def save_to_cache(proxyImage, *args):
                if proxyImage.image.texture:
                    core_image = CoreImage(proxyImage.image.texture)
                    core_image.save(file_path)
                    self.thumbnail = file_path

                    self.aspect_ratio = core_image.texture.width / float(core_image.texture.height)

            proxyImage = Loader.image(
                url,
            )
            proxyImage.bind(on_load=save_to_cache)


class TestVideoPlayer(MDApp):
    def build(self):
        base_dir = os.path.dirname(os.path.realpath(__file__))  # Get the directory of the current file
        video_dir = os.path.join(base_dir, "video_files")  # Get the path to the 'video_files' directory
        source = os.path.join(video_dir, "video_file.mp4")  # Get the path to the video file
        thumbnail = os.path.join(video_dir, "thumbnail.png")  # Get the path to the thumbnail file

        root = CustomVideoPlayer()
        root.source = source
        root.thumbnail = thumbnail
        return root


if __name__ == '__main__':
    TestVideoPlayer().run()
