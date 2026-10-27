import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk, ImageOps
import json
import os
import re
import sys
import random

try:
    import pygame
except ImportError:
    pygame = None


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR

ASSETS = RESOURCE_DIR / "Assets"

SAVE_DIR = (
    Path(os.getenv("LOCALAPPDATA") or Path.home())
    / "VisualNovel"
    / "Saves"
)

SAVE_VERSION = 1
SAVE_SLOTS = 3

WIDTH = 1280
HEIGHT = 720

BG = "#101318"
PANEL = "#101318"
TEXT = "#D5D9DF"
BLUE = "#A3C9E2"
MUTED = "#B4BAC3"
HOVER_BG = "#19222D"

FONT = "Consolas"

CHARACTERS = {
    "mc": "Me",
    "stranger": "Stranger",
    "mother": "Mother",
    None: ""
}

STORY = {
    "start": [
        ("scene", "Roadside"),
        ("mc", "I wonder whose note this is."),
        (None, "Looks like it belongs to a restaurant."),
        (None, "I should probably return it."),
        ("scene", "Stranger"),
        ("stranger", "Hey, that's mine!"),
        ("choice", [("Give it back", "Give"), ("Keep it", "Keep")])
    ],
    "Give": [
        ("scene", "Strangernote"),
        ("mc", "Oh, sorry! Here you go."),
        ("stranger", "You're fine! Thank you."),
        (None, "Well, good to know I found who it belongs to."),
        ("end",)
    ],
    "Keep": [
        ("scene", "Keepnote"),
        ("mc", "I don't believe you."),
        ("stranger", "..."),
        ("stranger", "You're right. I thought you were trying to steal it."),
        ("mc", "No, you're fine!"),
        (None, "Well, mystery solved."),
        ("end",)
    ]
}

app = tk.Tk()
app.title("Visual Novel")
app.geometry(f"{WIDTH}x{HEIGHT}")
app.minsize(800, 500)
app.configure(bg=BG)

canvas = tk.Canvas(
    app,
    bg=BG,
    highlightthickness=0,
    bd=0
)
canvas.pack(fill="both", expand=True)

audio_ready = False
active_sounds = []
menu_music_playing = False
sound_enabled = True

if pygame is not None:
    try:
        pygame.mixer.init()
        audio_ready = True
        print("Audio initialized:", pygame.mixer.get_init())
    except Exception as error:
        print("Audio initialization failed:", repr(error))
else:
    print("Pygame is not installed or could not be imported.")


def play_sound(filename):
    if not audio_ready or not sound_enabled:
        print("Cannot play sound: audio is unavailable.")
        return

    path = ASSETS / filename

    if not path.is_file():
        print("Missing sound file:", path)
        return

    try:
        sound = pygame.mixer.Sound(str(path))
        sound.play()
        active_sounds.append(sound)
        print("Playing sound:", filename)
    except Exception as error:
        print(f"Sound error ({filename}):", repr(error))


def stop_sounds():
    if audio_ready:
        pygame.mixer.stop()

    active_sounds.clear()


def play_menu_music():
    global menu_music_playing

    if not audio_ready or not sound_enabled:
        print("Menu music unavailable: mixer is not initialized.")
        return

    path = ASSETS / "MenuMusic.mp3"

    if not path.is_file():
        print("Missing menu music file:", path)
        return

    # Don't start the same track again if it is already playing.
    try:
        if pygame.mixer.music.get_busy():
            menu_music_playing = True
            return

        print("Loading menu music:", path)

        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play(-1)

        menu_music_playing = True
        print("Menu music started.")

    except Exception as error:
        menu_music_playing = False
        print("Menu music error:", repr(error))


def toggle_audio():
    global sound_enabled
    sound_enabled = not sound_enabled
    if sound_enabled:
        if mode == "menu":
            play_menu_music()
    else:
        stop_menu_music()
        stop_sounds()
    if mode == "menu":
        draw_menu()


def stop_menu_music():
    global menu_music_playing

    if audio_ready:
        try:
            pygame.mixer.music.stop()
        except Exception as error:
            print("Error stopping menu music:", repr(error))

    menu_music_playing = False


SCENES = {
    "menu": "Menu.png",
    "Roadside": "Roadside.png",
    "Stranger": "Stranger.png",
    "Strangernote": "Strangernote.png",
    "Keepnote": "Keepnote.png",
    "mother_house": "mother_house.png",
    "endcredits": "endcredits.png"
}

image_cache = {}
background_photo = None


def get_image(name):
    if name == "black":
        return None

    if name in image_cache:
        return image_cache[name]

    filename = SCENES.get(name)

    if filename is None:
        return None

    path = ASSETS / filename

    if not path.exists():
        print("Missing image:", path)
        image_cache[name] = None
        return None

    try:
        image = Image.open(path).convert("RGB")
        image_cache[name] = image
        return image
    except Exception as error:
        print("Image error:", error)
        return None


def draw_background(name):
    global background_photo

    canvas.configure(bg="#000000")
    image = get_image(name)

    if image is None:
        return

    w = max(canvas.winfo_width(), 1)
    h = max(canvas.winfo_height(), 1)

    resized = ImageOps.fit(
        image,
        (w, h),
        method=Image.Resampling.LANCZOS
    )

    background_photo = ImageTk.PhotoImage(resized)

    canvas.create_image(
        0,
        0,
        image=background_photo,
        anchor="nw"
    )


mode = "menu"
current_label = "start"
story_index = 0
current_scene = "black"
current_line = None
current_choices = []
previous_mode = "menu"
save_snapshot = None
resize_job = None
dialogue_box = None


def clear_canvas():
    global dialogue_box

    if dialogue_box is not None:
        dialogue_box.destroy()
        dialogue_box = None

    canvas.delete("all")


def slot_path(slot):
    if not isinstance(slot, int) or not 1 <= slot <= SAVE_SLOTS:
        raise ValueError("Invalid save slot")
    return SAVE_DIR / f"slot_{slot}.json"


def capture_progress():
    if mode not in ("story", "choice"):
        return None

    return {
        "version": SAVE_VERSION,
        "label": current_label,
        "index": story_index,
        "scene": current_scene,
        "mode": mode,
        "line": list(current_line) if current_line else None,
        "choices": [list(choice) for choice in current_choices],
        "saved_at": datetime.now().isoformat(timespec="seconds")
    }


def read_slot(slot):
    path = slot_path(slot)

    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Invalid save data")

        if data.get("version") != SAVE_VERSION:
            raise ValueError("Unsupported save version")

        label = data["label"]
        index = data["index"]
        saved_mode = data["mode"]
        scene = data["scene"]

        if label not in STORY:
            raise ValueError("Unknown story route")

        if type(index) is not int:
            raise ValueError("Invalid story index")

        if not 0 <= index <= len(STORY[label]):
            raise ValueError("Story index out of range")

        if saved_mode not in ("story", "choice"):
            raise ValueError("Invalid game mode")

        if scene not in SCENES and scene != "black":
            raise ValueError("Invalid scene")

        if saved_mode == "story":
            line = data.get("line")

            if (
                not isinstance(line, list)
                or len(line) != 2
                or line[0] not in CHARACTERS
                or not isinstance(line[1], str)
            ):
                raise ValueError("Invalid dialogue")

            if index < 1:
                raise ValueError("Invalid dialogue position")

            expected = STORY[label][index - 1]

            if (
                len(expected) != 2
                or expected[0] != line[0]
                or expected[1] != line[1]
            ):
                raise ValueError("Dialogue does not match story")

        if saved_mode == "choice":
            choices = data.get("choices")

            if not isinstance(choices, list) or not choices:
                raise ValueError("Invalid choices")

            for choice in choices:
                if (
                    not isinstance(choice, list)
                    or len(choice) != 2
                    or not isinstance(choice[0], str)
                    or not isinstance(choice[1], str)
                    or choice[1] not in STORY
                ):
                    raise ValueError("Invalid choice")

            if index < 1:
                raise ValueError("Invalid choice position")

            expected = STORY[label][index - 1]

            if (
                expected[0] != "choice"
                or expected[1] != [tuple(c) for c in choices]
            ):
                raise ValueError("Choices do not match story")

        return data

    except (
        OSError, ValueError, KeyError,
        TypeError, IndexError
    ) as error:
        print("Save file error:", error)
        return None


def write_slot(slot):
    if save_snapshot is None:
        return

    data = dict(save_snapshot)
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")

    path = slot_path(slot)
    temporary = path.with_suffix(".tmp")

    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)

        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )

        os.replace(temporary, path)

        messagebox.showinfo(
            "Game Saved",
            f"Progress saved successfully to Slot {slot}."
        )

        return_from_slots()

    except OSError as error:
        messagebox.showerror("Save Error", str(error))


def restore_slot(slot):
    global mode, current_label, story_index
    global current_scene, current_line, current_choices
    global save_snapshot

    data = read_slot(slot)

    if data is None:
        messagebox.showwarning(
            "LOAD",
            "This slot is empty or its save file is invalid."
        )
        return

    stop_menu_music()
    stop_sounds()

    current_label = data["label"]
    story_index = data["index"]
    current_scene = data["scene"]

    current_line = (
        tuple(data["line"]) if data.get("line") else None
    )

    current_choices = [
        tuple(choice) for choice in data.get("choices", [])
    ]

    mode = data["mode"]
    save_snapshot = None

    if mode == "choice":
        draw_choices()
    else:
        draw_story()


def open_slots(screen_type):
    global mode, previous_mode, save_snapshot

    if screen_type == "save":
        if mode not in ("story", "choice"):
            return

        save_snapshot = capture_progress()
        previous_mode = mode
        mode = "save"

    elif screen_type == "load":
        if mode not in ("menu", "story", "choice"):
            return

        previous_mode = mode
        save_snapshot = None
        mode = "load"

    else:
        return

    draw_slots()


def draw_slots():
    clear_canvas()
    canvas.configure(cursor="", bg=BG)

    w = canvas.winfo_width()
    h = canvas.winfo_height()

    title = "SAVE GAME" if mode == "save" else "LOAD GAME"

    canvas.create_text(
        w / 2,
        h * 0.13,
        text=title,
        fill=BLUE,
        font=(FONT, 26, "bold")
    )

    for slot in range(1, SAVE_SLOTS + 1):
        data = read_slot(slot)
        y = h * 0.27 + (slot - 1) * h * 0.19
        tag = f"slot_{slot}"

        canvas.create_rectangle(
            w * 0.20,
            y - 42,
            w * 0.80,
            y + 42,
            fill="#141A22",
            outline="#607F93",
            tags=(tag,)
        )

        if data:
            route = data["label"].upper()

            if data.get("line"):
                preview = data["line"][1]
            else:
                preview = "Story choice"

            preview = preview.replace("{b}", "").replace("{/b}", "")
            preview = preview[:65]

            try:
                date = datetime.fromisoformat(
                    data["saved_at"]
                ).strftime("%b %d, %Y  %I:%M %p")
            except (ValueError, KeyError, TypeError):
                date = "Unknown date"

            description = f"{route}  |  {date}\n{preview}"

        else:
            description = "EMPTY SLOT"

        canvas.create_text(
            w * 0.24,
            y,
            text=f"SLOT {slot:02d}",
            fill=BLUE,
            font=(FONT, 16, "bold"),
            anchor="w",
            tags=(tag,)
        )

        canvas.create_text(
            w * 0.40,
            y,
            text=description,
            fill=TEXT,
            font=(FONT, 12),
            anchor="w",
            width=w * 0.37,
            tags=(tag,)
        )

        canvas.tag_bind(
            tag,
            "<Enter>",
            lambda event, t=tag: slot_hover(t, True)
        )

        canvas.tag_bind(
            tag,
            "<Leave>",
            lambda event, t=tag: slot_hover(t, False)
        )

        canvas.tag_bind(
            tag,
            "<Button-1>",
            lambda event, s=slot: select_slot(s)
        )

    canvas.create_text(
        w / 2,
        h * 0.90,
        text="ESC — BACK",
        fill=MUTED,
        font=(FONT, 13)
    )


def slot_hover(tag, active):
    for item in canvas.find_withtag(tag):
        if canvas.type(item) == "rectangle":
            canvas.itemconfigure(
                item,
                outline=BLUE if active else "#607F93",
                fill=HOVER_BG if active else "#141A22"
            )

    canvas.configure(cursor="hand2" if active else "")


def select_slot(slot):
    if mode == "save":
        path = slot_path(slot)

        if path.exists():
            confirm = messagebox.askyesno(
                "Overwrite Save",
                f"Overwrite Slot {slot}?"
            )

            if not confirm:
                return

        write_slot(slot)

    elif mode == "load":
        restore_slot(slot)


def return_from_slots():
    global mode, save_snapshot

    mode = previous_mode
    save_snapshot = None

    if mode == "menu":
        draw_menu()
    elif mode == "minigame":
        draw_flight()
    elif mode == "story":
        draw_story()
    elif mode == "choice":
        draw_choices()


def menu_hover(tag, active):
    canvas.itemconfigure(
        tag,
        fill=BLUE if active else MUTED
    )

    canvas.configure(cursor="hand2" if active else "")


def draw_menu():
    global mode

    mode = "menu"

    clear_canvas()
    canvas.configure(cursor="")

    draw_background("menu")
    play_menu_music()

    w = canvas.winfo_width()
    h = canvas.winfo_height()

    audio_tag = "audio_toggle"
    canvas.create_text(
        w - 28, 30, anchor="e",
        text="AUDIO: ON" if sound_enabled else "AUDIO: OFF",
        fill=BLUE if sound_enabled else MUTED,
        font=(FONT, 14, "bold"), tags=(audio_tag,)
    )
    canvas.tag_bind(audio_tag, "<Button-1>", lambda event: toggle_audio())

    x = w * 0.67
    y = h * 0.52

    canvas.create_rectangle(
        x - 135,
        y - 125,
        x + 135,
        y + 125,
        fill=PANEL,
        outline=""
    )

    buttons = [
        ("play", "▶  P L A Y", y - 70, start_game),
        ("minigame", "✦  N O T E  F L I G H T", y, launch_minigame),
        ("load", "▱  L O A D", y + 70, load_game)
    ]

    for tag, title, pos_y, command in buttons:
        canvas.create_text(
            x,
            pos_y,
            text=title,
            fill=MUTED,
            font=(FONT, 21),
            tags=(tag,)
        )

        canvas.tag_bind(
            tag,
            "<Button-1>",
            lambda event, c=command: c()
        )

        canvas.tag_bind(
            tag,
            "<Enter>",
            lambda event, t=tag: menu_hover(t, True)
        )

        canvas.tag_bind(
            tag,
            "<Leave>",
            lambda event, t=tag: menu_hover(t, False)
        )


def load_game():
    open_slots("load")


def show_content_disclaimer():
    message = (
        "Hi! This is my game.\n\nDo you wish to continue?"
    )

    return messagebox.askyesno("Start Game", message)

def start_game():
    global mode, current_label, story_index
    global current_scene, current_line, current_choices

    # Ask whether to start a new game.
    if not show_content_disclaimer():
        return

    stop_menu_music()
    stop_sounds()

    mode = "story"
    current_label = "start"
    story_index = 0
    current_scene = "black"
    current_line = None
    current_choices = []

    process_story()


def launch_minigame():
    stop_menu_music()
    stop_sounds()
    start_minigame()


# Note Flight: a short Flappy Bird-style intro. No extra art files needed.
flight_y = 0.0
flight_velocity = 0.0
flight_obstacles = []
flight_frame = 0
flight_score = 0
flight_status = "ready"
flight_job = None
FLIGHT_GOAL = 5


def cancel_flight():
    global flight_job
    if flight_job is not None:
        app.after_cancel(flight_job)
        flight_job = None


def start_minigame():
    global mode, flight_y, flight_velocity, flight_obstacles
    global flight_frame, flight_score, flight_status
    cancel_flight()
    mode = "minigame"
    flight_y = max(canvas.winfo_height(), 500) * 0.48
    flight_velocity = 0.0
    flight_obstacles = []
    flight_frame = 0
    flight_score = 0
    flight_status = "ready"
    draw_flight()


def flap():
    global flight_velocity, flight_status
    if mode != "minigame":
        return
    if flight_status == "crashed":
        start_minigame()
        return
    if flight_status == "won":
        finish_minigame()
        return
    if flight_status == "ready":
        flight_status = "playing"
        flight_tick()
    flight_velocity = -6.5


def finish_minigame():
    cancel_flight()
    draw_menu()


def flight_tick():
    global flight_job, flight_y, flight_velocity, flight_frame
    global flight_score, flight_status
    flight_job = None
    if mode != "minigame" or flight_status != "playing":
        return
    w, h = max(canvas.winfo_width(), 800), max(canvas.winfo_height(), 500)
    flight_frame += 1
    flight_velocity = min(flight_velocity + 0.34, 7.5)
    flight_y += flight_velocity
    if flight_frame % 76 == 0:
        kind = random.choice(("lamp", "bird"))
        # A bird is an aerial hazard; a lamp rises from the pavement.
        flight_obstacles.append({"x": float(w + 35), "kind": kind,
                                 "y": random.uniform(h * .26, h * .65),
                                 "passed": False})
    for obj in flight_obstacles:
        obj["x"] -= 3.5
        ox, oy = obj["x"], obj["y"]
        if not obj["passed"] and ox + 32 < w * .25 - 20:
            obj["passed"] = True
            flight_score += 1
        if abs(ox - w * .25) < 37:
            if obj["kind"] == "bird":
                hit = abs(flight_y - oy) < 34
            else:
                hit = flight_y + 15 > oy
            if hit:
                flight_status = "crashed"
    flight_obstacles[:] = [o for o in flight_obstacles if o["x"] > -60]
    if flight_y < 18 or flight_y > h - 38:
        flight_status = "crashed"
    if flight_score >= FLIGHT_GOAL:
        flight_status = "won"
    draw_flight()
    if flight_status == "playing":
        flight_job = app.after(25, flight_tick)


def draw_flight():
    clear_canvas()
    canvas.configure(bg="#152331", cursor="")
    w, h = max(canvas.winfo_width(), 800), max(canvas.winfo_height(), 500)
    canvas.create_rectangle(0, h - 25, w, h, fill="#31343B", outline="")
    canvas.create_line(0, h - 25, w, h - 25, fill="#9BA8B1", width=3)
    for obj in flight_obstacles:
        x, y = obj["x"], obj["y"]
        if obj["kind"] == "lamp":
            canvas.create_line(x, h - 25, x, y, fill="#9BA8B1", width=8)
            canvas.create_line(x, y, x + 26, y, fill="#9BA8B1", width=6)
            canvas.create_oval(x + 18, y - 5, x + 35, y + 7,
                               fill="#FFE1A0", outline="")
        else:
            canvas.create_arc(x - 22, y - 10, x + 2, y + 12,
                              start=10, extent=155, style="arc",
                              outline="#F2F4F5", width=3)
            canvas.create_arc(x, y - 10, x + 24, y + 12,
                              start=15, extent=155, style="arc",
                              outline="#F2F4F5", width=3)
    x = w * .25
    canvas.create_polygon(x - 20, flight_y - 13, x + 19, flight_y - 13,
                          x + 19, flight_y + 13, x - 20, flight_y + 13,
                          fill="#F4E5BC", outline="#28323D", width=2)
    canvas.create_line(x - 20, flight_y - 13, x, flight_y + 1,
                       x + 19, flight_y - 13, fill="#647280", width=2)
    canvas.create_text(25, 25, anchor="nw", text=f"NOTE FLIGHT  {flight_score}/{FLIGHT_GOAL}",
                       fill=TEXT, font=(FONT, 19, "bold"))
    canvas.create_text(w - 20, 25, anchor="ne", text="SPACE / CLICK = FLAP   ESC = MENU",
                       fill=TEXT, font=(FONT, 12))
    messages = {
        "ready": "Keep the note flying!\\nAvoid streetlamps and birds.\\nCLICK or SPACE to start",
        "crashed": "THE NOTE FELL!\\nCLICK or SPACE to retry",
        "won": "YOU MADE IT!\\nCLICK or SPACE to continue the story"
    }
    if flight_status in messages:
        canvas.create_rectangle(w*.17, h*.32, w*.83, h*.67,
                                fill=PANEL, outline=BLUE, width=2)
        canvas.create_text(w/2, h/2, text=messages[flight_status],
                           justify="center", fill=TEXT, font=(FONT, 19, "bold"))


def process_story():
    global mode, story_index, current_scene
    global current_line, current_choices

    if mode != "story":
        return

    script = STORY[current_label]

    while story_index < len(script):
        entry = script[story_index]
        story_index += 1

        command = entry[0]

        if command == "scene":
            current_scene = entry[1]
            continue

        if command == "sound":
            play_sound(entry[1])
            continue

        if command == "choice":
            current_choices = entry[1]
            current_line = None
            mode = "choice"
            draw_choices()
            return

        if command == "end":
            mode = "ending"
            draw_ending()
            return

        current_line = entry
        draw_story()
        return

    mode = "ending"
    draw_ending()


def draw_story():
    global dialogue_box

    clear_canvas()
    canvas.configure(cursor="")

    draw_background(current_scene)

    if current_line is None:
        return

    speaker_id, dialogue = current_line
    speaker = CHARACTERS.get(speaker_id, speaker_id or "")

    w = canvas.winfo_width()
    h = canvas.winfo_height()

    x1 = w * 0.055
    x2 = w * 0.945
    y1 = h * 0.69
    y2 = h * 0.94

    canvas.create_rectangle(
        x1, y1, x2, y2,
        fill="#090D14",
        outline="#607F93",
        width=1
    )

    if speaker:
        canvas.create_text(
            x1 + 30,
            y1 + 30,
            text=speaker,
            fill=BLUE,
            font=(FONT, 19, "bold"),
            anchor="w"
        )

    dialogue_box = tk.Text(
        canvas,
        bg="#090D14",
        fg=TEXT,
        font=(FONT, 16),
        wrap="word",
        bd=0,
        highlightthickness=0,
        padx=0,
        pady=0,
        cursor="hand2",
        takefocus=0
    )

    dialogue_box.tag_configure(
        "bold",
        font=(FONT, 16, "bold")
    )

    parts = re.split(r"(\{b\}|\{/b\})", dialogue)
    bold_active = False

    for part in parts:
        if part == "{b}":
            bold_active = True
        elif part == "{/b}":
            bold_active = False
        elif part:
            if bold_active:
                dialogue_box.insert("end", part, "bold")
            else:
                dialogue_box.insert("end", part)

    dialogue_box.configure(state="disabled")

    canvas.create_window(
        x1 + 30,
        y1 + 73,
        window=dialogue_box,
        anchor="nw",
        width=max(int(x2 - x1 - 60), 100),
        height=max(int(y2 - y1 - 95), 35)
    )

    dialogue_box.bind(
        "<Button-1>",
        lambda event: next_dialogue()
    )

    canvas.create_text(
        x2 - 25,
        y2 - 18,
        text="▼",
        fill=BLUE,
        font=(FONT, 12)
    )


def next_dialogue(event=None):
    if mode != "story":
        return

    process_story()


def draw_choices():
    clear_canvas()
    canvas.configure(cursor="")

    draw_background(current_scene)

    w = canvas.winfo_width()
    h = canvas.winfo_height()
    x = w / 2

    canvas.create_text(
        x,
        h * 0.35,
        text="CHOOSE",
        fill=BLUE,
        font=(FONT, 16)
    )

    for i, (option, destination) in enumerate(current_choices):
        y = h * 0.46 + i * 85
        tag = f"choice_{i}"

        canvas.create_rectangle(
            x - 230,
            y - 27,
            x + 230,
            y + 27,
            fill=PANEL,
            outline="#607F93",
            tags=(tag,)
        )

        canvas.create_text(
            x,
            y,
            text=option,
            fill=TEXT,
            font=(FONT, 17),
            tags=(tag,)
        )

        canvas.tag_bind(
            tag,
            "<Enter>",
            lambda event, t=tag: choice_hover(t, True)
        )

        canvas.tag_bind(
            tag,
            "<Leave>",
            lambda event, t=tag: choice_hover(t, False)
        )

        canvas.tag_bind(
            tag,
            "<Button-1>",
            lambda event, d=destination: jump_to(d)
        )


def choice_hover(tag, active):
    for item in canvas.find_withtag(tag):
        if canvas.type(item) == "text":
            canvas.itemconfigure(
                item,
                fill=BLUE if active else TEXT
            )

    canvas.configure(cursor="hand2" if active else "")


def jump_to(destination):
    global current_label, story_index, mode
    global current_choices, current_line

    if destination not in STORY:
        print("Unknown story label:", destination)
        return

    current_label = destination
    story_index = 0
    current_choices = []
    current_line = None
    mode = "story"

    process_story()


def draw_ending():
    clear_canvas()
    canvas.configure(cursor="")

    draw_background(current_scene)

    w = canvas.winfo_width()
    h = canvas.winfo_height()

    if current_scene != "endcredits":
        canvas.create_text(
            w / 2,
            h / 2,
            text="END",
            fill=BLUE,
            font=(FONT, 28)
        )

    canvas.create_text(
        w / 2,
        h * 0.88,
        text="CLICK TO RETURN TO MENU",
        fill=TEXT,
        font=(FONT, 13)
    )


def handle_click(event):
    if mode == "minigame":
        flap()
    elif mode == "story":
        next_dialogue()
    elif mode == "ending":
        draw_menu()


def handle_key(event):
    key = event.keysym.lower()

    if key == "escape":
        cancel_flight()
        if mode in ("save", "load"):
            return_from_slots()
        elif mode != "menu":
            draw_menu()
        return

    if key == "s":
        if mode in ("story", "choice"):
            open_slots("save")
        return

    if key == "l":
        if mode in ("menu", "story", "choice"):
            open_slots("load")
        return

    if key in ("space", "return"):
        if mode == "minigame":
            flap()
        elif mode == "story":
            next_dialogue()
        elif mode == "ending":
            draw_menu()


canvas.bind("<Button-1>", handle_click)
app.bind("<Key>", handle_key)


def redraw():
    global resize_job
    resize_job = None

    if mode == "menu":
        draw_menu()
    elif mode == "story":
        draw_story()
    elif mode == "choice":
        draw_choices()
    elif mode == "ending":
        draw_ending()
    elif mode in ("save", "load"):
        draw_slots()


def on_resize(event):
    global resize_job

    if event.widget != canvas:
        return

    if resize_job is not None:
        app.after_cancel(resize_job)

    resize_job = app.after(120, redraw)


canvas.bind("<Configure>", on_resize)


def close_app():
    cancel_flight()
    stop_menu_music()
    stop_sounds()

    if audio_ready:
        pygame.mixer.quit()

    app.destroy()


app.protocol("WM_DELETE_WINDOW", close_app)

def launch_game():
    print("Starting Visual Novel...")
    draw_menu()

# Start the menu after Tkinter has initialized the window.
app.after(100, launch_game)

# Keep the game window open and respond to input.
app.mainloop()
