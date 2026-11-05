# KvyMD Video Player

This is a custom video player for Kivy using KivyMD components. The video player features play/pause, stop, volume, and fullscreen control buttons. It also shows the progress of the video, includes a thumbnail display, and supports local preview images.


![Screenhot of the custom video player](img.png)

## Installation

Clone the repository and navigate to the project directory:

```bash
git clone https://github.com/Noor-Kalibbala/CustomVideoPlayer.git
cd CustomVideoPlayer
```
## Dependencies

- Kivy >= 2.3.1, < 3 ([Installation](https://kivy.org/doc/stable/installation/installation.html))
- Python >= 3.10
- KivyMD >= 2.0.0, < 2.1
- ffpyplayer >= 4.5, < 5


To install these dependencies, you can use the `requirements.txt` file included in this project:

Install the required packages:
```bash
pip install -r requirements.txt

```

## Running the Application

Start the video player with the following command:
```bash
python custom_video_player.py
```
This plays the bundled sample video. Paths are resolved from this file, so the
launcher also works from another working directory. To play another file:

```bash
python custom_video_player.py "/absolute/path/to/video.mp4"
python custom_video_player.py "/absolute/path/to/video.mp4" --thumbnail "/path/to/preview.png"
```

On Debian/Ubuntu, PyCairo (a KivyMD 2 dependency) may need build prerequisites:

```bash
sudo apt install python3-venv python3-dev libcairo2-dev pkg-config
```

Use an `MDApp` when embedding `CustomVideoPlayer`. The updated controls use
`MDIconButton`, `MDSlider` plus `MDSliderHandle`, and the current label font roles.
The KV rules are scoped to this player and do not replace global VideoPlayer
rules. Stop, pause/play, seek, mute/volume, fullscreen/Escape and spacebar are
supported. Call `unload()` when disposing a player to release the decoder,
animations and window callbacks. The old unauthenticated URL thumbnail cache is
no longer used; supply a local thumbnail instead.

## Features

The video player includes the following features:

- Customizable control buttons.
- Responsive design.
- Full-screen mode.
- Volume control.
- Video progress bar.
- Keyboard controls.
- Auto-hide control buttons.
- Local preview images.
- Support for keyboard shortcuts.

## Directory Structure

- custom_video_player.py : The custom video player implementation.
- custom_video_player.kv : The Kivy layout file for the custom video player.
- video_files/ : Directory containing the video and thumbnail files.
- img.png : A screenshot of the application.
- README.md : This readme file.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
