"""Native Tk desktop interface. All content, editing and rendering are offline."""
from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import io
import traceback
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog

from PIL import Image, ImageTk

from . import __version__
from .assets import AssetStore, MINE_KEY, MINE_LABEL
from .formats import FormatError, read_cmk, read_wmf
from .model import CardDocument, CardObject, save_document, load_document
from .paths import default_library, open_path, save_settings
from .render import render_panel, export_panel
from .wmf import render_wmf

ROOT = Path(__file__).resolve().parents[1]
ACCENT, INK, MUTED, BASE = "#087f86", "#172f43", "#5b7080", "#f2f5f7"


class CardShopApp:
    def __init__(self, root: tk.Tk, asset_root: Path | None = None, initial_file: Path | None = None):
        self.root = root
        if asset_root is None:
            library, rendered = default_library()
            self.store = AssetStore(library, rendered)
        else:
            self.store = AssetStore(asset_root, None)
        self.doc = CardDocument()
        self.path: Path | None = None
        self.dirty = False
        self.side = "front"
        self.selected: set[str] = set()
        self.history: list[CardDocument] = []
        self.future: list[CardDocument] = []
        self.clipboard: list[CardObject] = []
        self.clip_art, self.clip_fonts = {}, {}
        self.photos = {}
        self.canvas_photo = None
        self.zoom = 1.0
        self.scale = 1.0
        self.origin = (32, 32)
        self.handles = {}
        self.drag = None
        self.render_job = None
        self.list_job = None
        self.name_job = None
        self.error_messages = []
        self._loading = False
        self.root.title("OpenCardShop")
        self.root.geometry(f"{max(1080, min(1440, self.root.winfo_screenwidth() - 60))}x{max(720, min(930, self.root.winfo_screenheight() - 80))}")
        self.root.minsize(1080, 720)
        self.root.configure(background=BASE)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Destroy>", self._cleanup, add=True)
        self.root.report_callback_exception = self._callback_error
        self._style()
        self._set_icon()
        self._menu()
        self._build()
        self._bindings()
        self.refresh_library()
        if initial_file:
            self.open_path(initial_file)
        else:
            starter = self.store.find("BDAY/BDAY1.CMK")
            if starter:
                self._set_document(CardDocument.from_legacy(read_cmk(starter), "Birthday card", "BDAY/BDAY1.CMK"))
            elif self.store.starter:
                first = next((o.cards[0] for o in self.store.starter.occasions.values() if o.cards), None)
                if first:
                    try:
                        doc = load_document(first.path)
                        doc.source = "starter/" + first.path.name
                        self._set_document(doc)
                    except Exception:  # a damaged starter card must never stop the editor starting
                        traceback.print_exc()
        self.start_job = self.root.after(80, self.render)

    def _cleanup(self, event):
        if event.widget == self.root:
            for name in ("render_job", "list_job", "name_job", "start_job"):
                identifier = getattr(self, name, None)
                if identifier:
                    self.root.after_cancel(identifier)
                    setattr(self, name, None)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("DejaVu Sans", 10), background=BASE, foreground=INK)
        style.configure("TButton", padding=(10, 7), width=0, background="#e5edf1", borderwidth=0)
        style.map("TButton", background=[("active", "#d1e3e7")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", "#096d75")])
        style.configure("Heading.TLabel", font=("DejaVu Sans", 11, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED, font=("DejaVu Sans", 9))
        style.configure("TNotebook", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(13, 8))
        style.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", ACCENT)])
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=64, borderwidth=0)
        style.configure("Treeview.Heading", padding=6)
        style.configure("Layers.Treeview", rowheight=30)
        style.configure("Messages.Treeview", rowheight=44)
        style.map("Treeview", background=[("selected", "#d5eaed")], foreground=[("selected", INK)])

    def _menu(self):
        menu = tk.Menu(self.root)
        file = tk.Menu(menu, tearoff=False)
        new = tk.Menu(file, tearoff=False)
        for label, fold in (("Side-fold card", "side"), ("Top-fold card", "top"), ("Full-page design", "full")):
            new.add_command(label=label, command=lambda f=fold: self.new_card(f))
        file.add_cascade(label="New", menu=new)
        for label, command, shortcut in (("Open card…", self.open_card, "Ctrl+O"), ("Save", self.save, "Ctrl+S"),
                                         ("Save as…", lambda: self.save(True), "Ctrl+Shift+S")):
            file.add_command(label=label, command=command, accelerator=shortcut)
        file.add_separator()
        file.add_command(label="Import artwork…", command=self.import_art)
        file.add_command(label="Open another asset folder…", command=self.open_assets)
        file.add_separator()
        file.add_command(label="Export current view as PNG…", command=self.export_png)
        file.add_command(label="Print / folded PDF…", command=self.print_dialog, accelerator="Ctrl+P")
        file.add_separator()
        file.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file)
        edit = tk.Menu(menu, tearoff=False)
        for label, command, shortcut in (("Undo", self.undo, "Ctrl+Z"), ("Redo", self.redo, "Ctrl+Y"),
                                         ("Cut", self.cut, "Ctrl+X"), ("Copy", self.copy, "Ctrl+C"),
                                         ("Paste", self.paste, "Ctrl+V"), ("Delete", self.delete, "Del"),
                                         ("Select all", self.select_all, "Ctrl+A")):
            edit.add_command(label=label, command=command, accelerator=shortcut)
        edit.add_separator()
        edit.add_command(label="Bring to front", command=lambda: self.reorder(True))
        edit.add_command(label="Send to back", command=lambda: self.reorder(False))
        edit.add_command(label="Centre horizontally", command=lambda: self.center_objects("x"))
        edit.add_command(label="Centre vertically", command=lambda: self.center_objects("y"))
        menu.add_cascade(label="Edit", menu=edit)
        view = tk.Menu(menu, tearoff=False)
        for side in ("front", "inside", "back"):
            view.add_command(label=side.title(), command=lambda s=side: self.switch_side(s))
        self.guides_var = tk.BooleanVar(value=True)
        view.add_checkbutton(label="Show centre fold in Inside view", variable=self.guides_var, command=self.schedule_render)
        view.add_command(label="Fit view", command=self.fit_view)
        menu.add_cascade(label="View", menu=view)
        library = tk.Menu(menu, tearoff=False)
        self._fill_library_menu(library)
        menu.add_cascade(label="My library", menu=library)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="User guide", command=lambda: self.show_document("USER_GUIDE.md"))
        help_menu.add_command(label="Recovery report", command=lambda: self.show_document("VALIDATION_REPORT.md"))
        help_menu.add_command(label="About OpenCardShop", command=self.about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)

    def _build(self):
        heading = tk.Frame(self.root, bg=INK, padx=22, pady=13)
        heading.pack(fill="x")
        tk.Label(heading, text="OpenCardShop", font=("DejaVu Sans", 20, "bold"), foreground="white", background=INK).pack(side="left")
        tk.Label(heading, text="Design, personalise and print folded cards.", font=("DejaVu Sans", 10), foreground="#c5d9e3", background=INK).pack(side="left", padx=24)
        ttk.Button(heading, text="Save card", style="Accent.TButton", command=self.save).pack(side="right")
        toolbar = ttk.Frame(self.root, padding=(14, 9))
        toolbar.pack(fill="x")
        for label, callback in (("New side fold", lambda: self.new_card("side")), ("New top fold", lambda: self.new_card("top")),
                                ("Full page", lambda: self.new_card("full")), ("Open", self.open_card),
                                ("Undo", self.undo), ("Redo", self.redo), ("Add text", self.add_text), ("Import art", self.import_art)):
            ttk.Button(toolbar, text=label, command=callback).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Print / PDF", command=self.print_dialog, style="Accent.TButton").pack(side="right", padx=3)
        names = ttk.Frame(self.root, padding=(18, 0, 18, 10))
        names.pack(fill="x")
        self.recipient_var, self.sender_var = tk.StringVar(), tk.StringVar()
        for label, variable in (("To", self.recipient_var), ("From", self.sender_var)):
            ttk.Label(names, text=label).pack(side="left", padx=(0, 8))
            entry = ttk.Entry(names, textvariable=variable, width=25)
            entry.pack(side="left", padx=(0, 22))
            variable.trace_add("write", lambda *args: self._names_changed())
        self.info_var = tk.StringVar()
        ttk.Label(names, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        self.status_var = tk.StringVar(value=self._welcome())
        status = ttk.Frame(self.root, padding=(18, 6))
        status.pack(side="bottom", fill="x")
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        left = ttk.Frame(body, padding=(0, 0, 8, 0), width=315)
        centre = ttk.Frame(body, width=680)
        right = ttk.Frame(body, padding=(12, 0, 0, 0), width=285)
        body.add(left, weight=0)
        body.add(centre, weight=1)
        body.add(right, weight=0)
        self._library_widgets(left)
        self._canvas_widgets(centre)
        property_canvas = tk.Canvas(right, background=BASE, highlightthickness=0, width=285)
        property_scroll = ttk.Scrollbar(right, orient="vertical", command=property_canvas.yview)
        property_scroll.pack(side="right", fill="y")
        property_canvas.pack(fill="both", expand=True)
        property_canvas.configure(yscrollcommand=property_scroll.set)
        property_frame = ttk.Frame(property_canvas)
        property_window = property_canvas.create_window(0, 0, window=property_frame, anchor="nw")
        property_frame.bind("<Configure>", lambda e: property_canvas.configure(scrollregion=property_canvas.bbox("all")))
        property_canvas.bind("<Configure>", lambda e: property_canvas.itemconfigure(property_window, width=e.width))
        property_canvas.bind("<MouseWheel>", lambda e: property_canvas.yview_scroll(-2 if e.delta > 0 else 2, "units"))
        property_canvas.bind("<Button-4>", lambda e: property_canvas.yview_scroll(-2, "units"))
        property_canvas.bind("<Button-5>", lambda e: property_canvas.yview_scroll(2, "units"))
        self._property_widgets(property_frame)

    def _library_widgets(self, frame):
        ttk.Label(frame, text="DESIGN LIBRARY", style="Heading.TLabel").pack(anchor="w", pady=(3, 8))
        self.occasion_var = tk.StringVar(value=next(iter(self.store.occasions.values()), ""))
        self.occasion_combo = ttk.Combobox(frame, textvariable=self.occasion_var, values=list(self.store.occasions.values()), state="readonly")
        self.occasion_combo.pack(fill="x", pady=(0, 8))
        self.occasion_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_library())
        self.search_var = tk.StringVar()
        search = ttk.Entry(frame, textvariable=self.search_var)
        search.pack(fill="x", pady=(0, 3))
        ttk.Label(frame, text="Search the cards, artwork or messages below", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        self.search_var.trace_add("write", lambda *args: self._schedule_library())
        self.library_tabs = ttk.Notebook(frame)
        self.card_tree = self._tree_tab("Cards", columns=("fold",), tree_width=230)
        self.card_tree.heading("fold", text="Fold")
        self.card_tree.column("fold", width=60, stretch=False)
        self.card_tree.bind("<Double-1>", lambda e: self.use_template())
        self.art_tree = self._tree_tab("Artwork", columns=(), tree_width=275)
        self.art_tree.bind("<Double-1>", lambda e: self.add_library_art())
        self.message_tree = self._tree_tab("Messages", columns=(), tree_width=275, style="Messages.Treeview")
        self.message_tree.bind("<Double-1>", lambda e: self.add_message())
        self.all_art_var = tk.BooleanVar(value=False)
        footer = ttk.Frame(frame)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Checkbutton(footer, text="Show all artwork", variable=self.all_art_var, command=self.refresh_library).pack(anchor="w", pady=(0, 4))
        self.library_count = tk.StringVar()
        ttk.Label(footer, textvariable=self.library_count, style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Button(footer, text="Add / open selected", style="Accent.TButton", command=self.use_library_selection).pack(fill="x")
        ttk.Button(footer, text="Add paired front + inside message", command=self.add_paired_message).pack(fill="x", pady=(5, 0))
        library_button = ttk.Menubutton(footer, text="My library ▾", direction="above")
        library_menu = tk.Menu(library_button, tearoff=False)
        self._fill_library_menu(library_menu)
        library_button.configure(menu=library_menu)
        library_button.pack(fill="x", pady=(5, 0))
        self.library_tabs.pack(fill="both", expand=True)

    def _tree_tab(self, label, columns, tree_width, style="Treeview"):
        tab = ttk.Frame(self.library_tabs)
        self.library_tabs.add(tab, text=label)
        tree = ttk.Treeview(tab, columns=columns, show="tree", selectmode="browse", style=style)
        tree.column("#0", width=tree_width, minwidth=200)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    def _canvas_widgets(self, frame):
        navigation = ttk.Frame(frame, padding=(10, 3, 10, 10))
        navigation.pack(fill="x")
        self.side_var = tk.StringVar(value="front")
        self.side_buttons = {}
        for side in ("front", "inside", "back"):
            button = ttk.Radiobutton(navigation, text=side.title(), variable=self.side_var, value=side,
                                     command=lambda s=side: self.switch_side(s))
            button.pack(side="left", padx=(0, 16))
            self.side_buttons[side] = button
        ttk.Button(navigation, text="Fit", command=self.fit_view).pack(side="right")
        ttk.Button(navigation, text="+", width=3, command=lambda: self.set_zoom(self.zoom * 1.25)).pack(side="right", padx=3)
        ttk.Button(navigation, text="−", width=3, command=lambda: self.set_zoom(self.zoom / 1.25)).pack(side="right", padx=3)
        area = ttk.Frame(frame)
        area.pack(fill="both", expand=True)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(area, background="#e3e9ed", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.canvas.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.bind("<Configure>", lambda e: self.schedule_render())
        self.canvas.bind("<Button-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Double-1>", self.double_click)
        self.canvas.bind("<MouseWheel>", self.mouse_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        ttk.Label(frame, text="Drag to move · drag a corner to resize · Ctrl-drag a corner to stretch art · double-click text to edit",
                  style="Muted.TLabel", wraplength=700).pack(anchor="w", padx=10, pady=(8, 2))

    def _property_widgets(self, frame):
        ttk.Label(frame, text="SELECTED OBJECT", style="Heading.TLabel").pack(anchor="w", pady=(3, 8))
        self.property_title = tk.StringVar(value="Click an object on the card")
        ttk.Label(frame, textvariable=self.property_title, style="Muted.TLabel", wraplength=260).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="Text / message").pack(anchor="w")
        self.text_editor = tk.Text(frame, height=5, width=28, wrap="word", relief="flat", borderwidth=1,
                                   font=("DejaVu Sans", 10), background="white", foreground=INK, undo=True)
        self.text_editor.pack(fill="x", pady=(4, 6))
        ttk.Label(frame, text="Names: <receiver> and <sender>", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        self.font_var = tk.StringVar(value=self._default_font())
        self.font_combo = ttk.Combobox(frame, textvariable=self.font_var,
                                       values=self._font_names(), state="normal")
        self.font_combo.pack(fill="x", pady=(0, 6))
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="Size (pt)").pack(side="left", padx=(0, 7))
        self.size_var = tk.StringVar(value="24")
        ttk.Spinbox(controls, from_=1, to=400, textvariable=self.size_var, width=6, increment=1).pack(side="left")
        self.color_var = tk.StringVar(value="#172d3f")
        ttk.Button(controls, text="Colour", command=self.choose_color).pack(side="right")
        self.bold_var, self.italic_var, self.underline_var, self.strike_var = (tk.BooleanVar() for _ in range(4))
        styles = ttk.Frame(frame)
        styles.pack(fill="x", pady=(7, 5))
        for label, variable in (("Bold", self.bold_var), ("Italic", self.italic_var), ("Underline", self.underline_var)):
            ttk.Checkbutton(styles, text=label, variable=variable).pack(side="left", padx=(0, 3))
        self.align_var = tk.StringVar(value="center")
        ttk.Combobox(frame, textvariable=self.align_var, values=("left", "center", "right"), state="readonly").pack(fill="x", pady=(0, 6))
        self.auto_fit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Fit text within its box", variable=self.auto_fit_var).pack(anchor="w", pady=(0, 6))
        position = ttk.Frame(frame)
        position.pack(fill="x")
        self.position_vars = {name: tk.StringVar(value="0") for name in ("x", "y", "w", "h")}
        for i, (name, label) in enumerate((("x", "X (in)"), ("y", "Y (in)"), ("w", "Width"), ("h", "Height"))):
            row, column = divmod(i, 2)
            ttk.Label(position, text=label).grid(row=row * 2, column=column, sticky="w", pady=(0, 2))
            ttk.Entry(position, textvariable=self.position_vars[name], width=12).grid(row=row * 2 + 1, column=column, sticky="ew", padx=(0, 8), pady=(0, 6))
        ttk.Button(frame, text="Apply changes", command=self.apply_properties, style="Accent.TButton").pack(fill="x", pady=(4, 8))
        arrange = ttk.Frame(frame)
        arrange.pack(fill="x")
        for label, callback in (("On top", lambda: self.reorder(True)), ("Behind", lambda: self.reorder(False)), ("Delete", self.delete)):
            ttk.Button(arrange, text=label, command=callback).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Label(frame, text="LAYERS", style="Heading.TLabel").pack(anchor="w", pady=(15, 6))
        self.layer_tree = ttk.Treeview(frame, show="tree", height=4, selectmode="extended", style="Layers.Treeview")
        self.layer_tree.pack(fill="both", expand=True)
        self.layer_tree.bind("<<TreeviewSelect>>", self.layer_selected)
        ttk.Button(frame, text="Centre selected object(s)", command=self.center_both).pack(fill="x", pady=(7, 0))

    def _bindings(self):
        commands = {"<Control-o>": self.open_card, "<Control-s>": self.save,
                    "<Control-Shift-S>": lambda: self.save(True), "<Control-p>": self.print_dialog}
        for event, command in commands.items():
            self.root.bind(event, lambda e, c=command: (c(), "break")[1])
        for event, command in (("<Control-z>", self.undo), ("<Control-y>", self.redo),
                               ("<Control-c>", self.copy), ("<Control-x>", self.cut),
                               ("<Control-v>", self.paste), ("<Control-a>", self.select_all), ("<Delete>", self.delete)):
            self.root.bind(event, lambda e, c=command: self._canvas_shortcut(c))
        for key, delta in (("Left", (-1, 0)), ("Right", (1, 0)), ("Up", (0, -1)), ("Down", (0, 1))):
            self.root.bind("<" + key + ">", lambda e, d=delta: self._nudge(e, *d))

    def _canvas_shortcut(self, command):
        if self.root.focus_get() == self.canvas:
            command()
            return "break"

    def _nudge(self, event, x, y):
        if self.root.focus_get() != self.canvas or not self.selected:
            return
        self.checkpoint()
        amount = 100 if event.state & 1 else 10
        for obj in self.selection():
            obj.x += x * amount
            obj.y += y * amount
        self.changed()
        return "break"

    def occasion(self):
        return next((key for key, name in self.store.occasions.items() if name == self.occasion_var.get()), next(iter(self.store.occasions), ""))

    def _schedule_library(self):
        if self.list_job:
            self.root.after_cancel(self.list_job)
        self.list_job = self.root.after(160, self.refresh_library)

    def refresh_library(self):
        if self.list_job:
            self.root.after_cancel(self.list_job)
            self.list_job = None
        query, occasion = self.search_var.get().casefold().strip(), self.occasion()
        if occasion == MINE_KEY:
            self.store.library_changed()
        self.card_tree.delete(*self.card_tree.get_children())
        self.art_tree.delete(*self.art_tree.get_children())
        self.message_tree.delete(*self.message_tree.get_children())
        self.photos.clear()
        self.template_rows, self.art_rows, self.message_rows = {}, {}, {}
        for i, template in enumerate(self.store.templates(occasion)):
            if query and query not in template.search:
                continue
            iid = "card" + str(i)
            photo = ImageTk.PhotoImage(self.store.template_thumbnail(template))
            self.photos[iid] = photo
            self.template_rows[iid] = template
            self.card_tree.insert("", "end", iid=iid, text=template.label, image=photo, values=(template.fold,))
        for i, name in enumerate(self.store.occasion_art(occasion, self.all_art_var.get())):
            if query and query not in name.casefold():
                continue
            iid = "art" + str(i)
            self.art_rows[iid] = name
            try:
                photo = ImageTk.PhotoImage(self.store.thumbnail(name))
                self.photos[iid] = photo
                label = Path(name).stem + ("  ·  bitmap preview" if name in self.store.issues else "")
                self.art_tree.insert("", "end", iid=iid, text=label, image=photo)
            except FormatError:
                self.art_tree.insert("", "end", iid=iid, text=Path(name).stem + "  ·  damaged source")
        for i, message in enumerate(self.store.messages(occasion)):
            if query and query not in (message.front + message.inside + message.back).casefold():
                continue
            iid = "message" + str(i)
            self.message_rows[iid] = message
            self.message_tree.insert("", "end", iid=iid, text=("Back: " if message.back else "") + message.label)
        self.library_count.set(f"{len(self.template_rows)} cards · {len(self.art_rows)} art · {len(self.message_rows)} messages")

    def use_library_selection(self):
        index = self.library_tabs.index(self.library_tabs.select())
        (self.use_template, self.add_library_art, self.add_message)[index]()

    def use_template(self):
        selection = self.card_tree.selection()
        if not selection or not self.confirm_save():
            return
        template = self.template_rows[selection[0]]
        if template.path.suffix.casefold() == ".occard":
            # A starter-pack card: opened as a new, unsaved copy so the original stays intact.
            doc = load_document(template.path)
            doc.source = "starter/" + template.path.name
        else:
            doc = CardDocument.from_legacy(read_cmk(template.path), Path(template.path).stem,
                                           str(template.path.relative_to(self.store.root)))
        doc.recipient, doc.sender = self.recipient_var.get(), self.sender_var.get()
        self._set_document(doc)
        self.status_var.set("Template opened. Edit any side and save your own copy.")

    def add_library_art(self):
        selection = self.art_tree.selection()
        if not selection:
            return
        name = self.art_rows[selection[0]]
        try:
            image = self.store.image(name)
            embedded = self.store.art_bytes(name) if name.startswith(("mine/", "starter/")) else None
            self.place_art(name, image.size, embedded)
            if name in self.store.issues:
                self.status_var.set(name + ": original bitmap preview used because the vector source is damaged.")
        except FormatError as exc:
            messagebox.showerror("Artwork unavailable", str(exc), parent=self.root)

    def place_art(self, name, size, embedded=None):
        units_w, units_h = self.doc.dimensions(self.side)
        fit = min(units_w * 0.65 / size[0], units_h * 0.65 / size[1])
        w, h = size[0] * fit, size[1] * fit
        obj = CardObject("art", (units_w - w) / 2, (units_h - h) / 2, w, h, art=name)
        self.checkpoint()
        if embedded:
            self.doc.embedded_art[name] = embedded
        self.doc.panels[self.side].append(obj)
        self.selected = {obj.id}
        self.changed()
        return obj

    def add_text(self, text="Your message", side=None, record=True):
        if not isinstance(text, str):
            text = "Your message"
        side = side or self.side
        w, h = self.doc.dimensions(side)
        box_w = w * (0.4 if side == "inside" and self.doc.fold == "side" else 0.8)
        box_h = h * (0.4 if side == "inside" and self.doc.fold == "top" else 0.3)
        x = w * 0.55 if side == "inside" and self.doc.fold == "side" else (w - box_w) / 2
        y = h * 0.55 if side == "inside" and self.doc.fold == "top" else (h - box_h) / 2
        obj = CardObject("text", x, y, box_w, box_h, text=text, size=24, font=self._default_font())
        if record:
            self.checkpoint()
        self.doc.panels[side].append(obj)
        self.side = side
        self.side_var.set(side)
        self.selected = {obj.id}
        self.changed()
        return obj

    def add_message(self):
        selection = self.message_tree.selection()
        if not selection:
            return
        message = self.message_rows[selection[0]]
        text = getattr(message, self.side) or message.front or message.inside or message.back
        self.add_text(text)

    def add_paired_message(self):
        selection = self.message_tree.selection()
        if not selection:
            return
        message = self.message_rows[selection[0]]
        if self.doc.fold == "full":
            self.add_text(message.front or message.inside or message.back, "front")
            return
        self.checkpoint()
        if message.front:
            self.add_text(message.front, "front", record=False)
        if message.inside:
            self.add_text(message.inside, "inside", record=False)
        if message.back:
            self.add_text(message.back, "back", record=False)
        self.status_var.set("Paired message added. Use Front and Inside to edit both parts.")

    def _set_document(self, doc, path=None):
        self.doc, self.path = doc, Path(path) if path else None
        self.dirty = False
        self.history.clear()
        self.future.clear()
        self.selected.clear()
        self.side, self.zoom = "front", 1.0
        self.side_var.set("front")
        self._loading = True
        self.recipient_var.set(doc.recipient)
        self.sender_var.set(doc.sender)
        self._loading = False
        self.changed(False)

    def new_card(self, fold):
        if self.confirm_save():
            self._set_document(CardDocument(fold=fold, recipient=self.recipient_var.get(), sender=self.sender_var.get()))

    def open_card(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Open a card",
                                              filetypes=[("Card files", "*.occard *.CMK *.cmk"), ("All files", "*")])
        if filename and self.confirm_save():
            self.open_path(Path(filename))

    def open_path(self, path):
        path = Path(path)
        try:
            if path.suffix.casefold() == ".cmk":
                doc = CardDocument.from_legacy(read_cmk(path), path.stem, str(path.name))
                self._set_document(doc)
            else:
                self._set_document(load_document(path), path)
        except Exception as exc:
            messagebox.showerror("Cannot open card", str(exc), parent=self.root)

    def save(self, save_as=False):
        self._flush_names()
        target = self.path
        if not target or save_as:
            filename = filedialog.asksaveasfilename(parent=self.root, title="Save your editable card", defaultextension=".occard",
                                                    initialfile=self.doc.title + ".occard", filetypes=[("OpenCardShop card", "*.occard")])
            if not filename:
                return False
            target = Path(filename)
        if target.suffix.casefold() != ".occard":
            target = target.with_suffix(".occard")
        try:
            save_document(self.doc, target, self.store)
            self.path = target
            self.dirty = False
            self.changed(False)
            self.status_var.set("Saved " + target.name + ". Artwork and fonts are embedded in the card.")
            return True
        except Exception as exc:
            messagebox.showerror("Cannot save card", str(exc), parent=self.root)
            return False

    def confirm_save(self):
        self._flush_names()
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved card", "Save this card before continuing?", parent=self.root)
        return self.save() if answer else answer is not None

    def close(self):
        if self.confirm_save():
            self.root.destroy()

    def open_assets(self):
        folder = filedialog.askdirectory(parent=self.root, title="Select the folder containing CARDSHOP.INI and ART")
        if not folder or not self.confirm_save():
            return
        try:
            store = AssetStore(folder)
            if not store.library_occasions or not store.art_files:
                raise FormatError("This folder does not contain a CardShop content library")
            self.store = store
            save_settings(library=str(Path(folder).resolve()))
            self.occasion_combo.configure(values=list(store.occasions.values()))
            self.occasion_var.set(next(iter(store.occasions.values())))
            self.font_combo.configure(values=self._font_names())
            self.status_var.set(self._welcome())
            self._set_document(CardDocument())
            self.refresh_library()
        except Exception as exc:
            messagebox.showerror("Cannot open asset folder", str(exc), parent=self.root)

    def import_art(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Import artwork", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.wmf *.WMF *.cmf *.CMF"), ("All files", "*")])
        if not filename:
            return
        try:
            path = Path(filename)
            image = self._read_picture(path)
            output = io.BytesIO()
            image.save(output, "PNG")
            data = output.getvalue()
            name = "import-" + hashlib.sha256(data).hexdigest()[:20] + ".png"
            self.place_art(name, image.size, data)
            self.status_var.set("Imported " + path.name)
        except Exception as exc:
            messagebox.showerror("Cannot import artwork", str(exc), parent=self.root)

    def checkpoint(self, before=None):
        self.history.append(before or self.doc.snapshot())
        self.history = self.history[-60:]
        self.future.clear()

    def changed(self, dirty=True):
        if dirty:
            self.dirty = True
        self.root.title(("* " if self.dirty else "") + self.doc.title + " — OpenCardShop")
        self.info_var.set({"side": "Side fold · 4¼ × 5½ in", "top": "Top fold · 5½ × 4¼ in", "full": "Full-page design"}[self.doc.fold])
        for side, button in self.side_buttons.items():
            button.configure(state="disabled" if self.doc.fold == "full" and side != "front" else "normal")
        self.update_layers()
        self.update_properties()
        self.schedule_render()

    def undo(self):
        self._flush_names()
        if self.history:
            self.future.append(self.doc.snapshot())
            self.doc = self.history.pop()
            self._sync_names()
            self.selected.clear()
            self.changed()

    def redo(self):
        if self.future:
            self.history.append(self.doc.snapshot())
            self.doc = self.future.pop()
            self._sync_names()
            self.selected.clear()
            self.changed()

    def _sync_names(self):
        self._loading = True
        self.recipient_var.set(self.doc.recipient)
        self.sender_var.set(self.doc.sender)
        self._loading = False

    def _names_changed(self):
        if self._loading:
            return
        if self.name_job:
            self.root.after_cancel(self.name_job)
        self.name_job = self.root.after(400, self._flush_names)

    def _flush_names(self):
        if self.name_job:
            self.root.after_cancel(self.name_job)
            self.name_job = None
        recipient, sender = self.recipient_var.get(), self.sender_var.get()
        if (recipient, sender) != (self.doc.recipient, self.doc.sender):
            self.checkpoint()
            self.doc.recipient, self.doc.sender = recipient, sender
            self.changed()

    def _read_picture(self, path: Path):
        if path.suffix.casefold() in (".wmf", ".cmf"):
            mf = read_wmf(path.read_bytes())
            w, h = mf.bounds[2] - mf.bounds[0], mf.bounds[3] - mf.bounds[1]
            scale = 1500 / max(w, h)
            return render_wmf(path.read_bytes(), (max(1, round(w * scale)), max(1, round(h * scale))), self.store.font)
        with Image.open(path) as original:
            if original.width * original.height > 40_000_000:
                raise FormatError("Picture is larger than 40 megapixels")
            return original.convert("RGBA")

    # My library: the user's own pictures, messages and designs, reusable in every card -----
    def _fill_library_menu(self, menu):
        for item in (("Add pictures…", self.library_add_pictures),
                     ("Add a message…", self.library_add_message),
                     None,
                     ("Save selected picture", self.library_save_picture),
                     ("Save selected text as a message", self.library_save_text),
                     ("Save this card as a design…", self.library_save_design),
                     None,
                     ("Remove selected item…", self.library_remove),
                     None,
                     ("Export My library…", self.library_export),
                     ("Import a library…", self.library_import),
                     ("Open My library folder", self.library_open_folder)):
            if item is None:
                menu.add_separator()
            else:
                menu.add_command(label=item[0], command=item[1])

    def _show_my_library(self, tab=None):
        self.store.library_changed()
        self.occasion_combo.configure(values=list(self.store.occasions.values()))
        self.occasion_var.set(MINE_LABEL)
        if tab is not None:
            self.library_tabs.select(tab)
        self.refresh_library()

    def library_add_pictures(self):
        files = filedialog.askopenfilenames(parent=self.root, title="Add pictures to My library",
                                            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.wmf *.WMF *.cmf *.CMF"), ("All files", "*")])
        added, failed = 0, []
        for filename in files or ():
            try:
                self.store.mine.add_picture(self._read_picture(Path(filename)), Path(filename).stem)
                added += 1
            except Exception as exc:
                failed.append(f"{Path(filename).name}: {exc}")
        if failed:
            messagebox.showerror("Some pictures were not added", "\n".join(failed[:10]), parent=self.root)
        if added:
            self._show_my_library(1)
            self.status_var.set(f"Added {added} picture(s) to My library. They are available in every card.")

    def library_add_message(self):
        MessageDialog(self.root, self._save_new_message)

    def _save_new_message(self, front, inside, back):
        if self.store.mine.add_message(front, inside, back):
            self._show_my_library(2)
            self.status_var.set("Message saved to My library.")

    def library_save_picture(self):
        pictures = [obj for obj in self.selection() if obj.kind == "art"]
        if not pictures:
            messagebox.showinfo("My library", "Select a picture on the card first.", parent=self.root)
            return
        try:
            for obj in pictures:
                self.store.mine.add_picture(self.store.image(obj.art, self.doc), Path(obj.art).stem)
        except (OSError, ValueError, FormatError) as exc:
            messagebox.showerror("Cannot save picture", str(exc), parent=self.root)
            return
        self._show_my_library(1)
        self.status_var.set(f"Saved {len(pictures)} picture(s) to My library.")

    def library_save_text(self):
        texts = [obj for obj in self.selection() if obj.kind == "text" and obj.text.strip()]
        if not texts:
            messagebox.showinfo("My library", "Select a text on the card first.", parent=self.root)
            return
        added = sum(self.store.mine.add_message(**{self.side: obj.text}) for obj in texts)
        self._show_my_library(2)
        self.status_var.set(f"Saved {added} message(s) to My library as {self.side} text." if added else "That message is already in My library.")

    def library_save_design(self):
        self._flush_names()
        title = simpledialog.askstring("Save design to My library", "Name this design:", initialvalue=self.doc.title, parent=self.root)
        if not title:
            return
        try:
            self.store.mine.add_card(self.doc, self.store, title)
        except (OSError, ValueError, FormatError) as exc:
            messagebox.showerror("Cannot save design", str(exc), parent=self.root)
            return
        self._show_my_library(0)
        self.status_var.set(f"Saved \"{title}\" to My library. Open it from Cards to start a new card from it.")

    def library_remove(self):
        if self.occasion() != MINE_KEY:
            messagebox.showinfo("My library", "Choose My library above the library list, select a card, picture or message, then remove it.", parent=self.root)
            return
        index = self.library_tabs.index(self.library_tabs.select())
        tree, rows = ((self.card_tree, self.template_rows), (self.art_tree, self.art_rows), (self.message_tree, self.message_rows))[index]
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("My library", "Select the item to remove first.", parent=self.root)
            return
        row = rows[selection[0]]
        label = tree.item(selection[0], "text")
        if not messagebox.askyesno("Remove from My library", f"Remove “{label}” from My library?\n\nCards you have already saved keep their own copy.", parent=self.root):
            return
        if index == 0:
            self.store.mine.remove_card(row.path)
        elif index == 1:
            self.store.mine.remove_picture(row)
        else:
            self.store.mine.remove_message(row)
        self._show_my_library(index)
        self.status_var.set("Removed from My library.")

    def library_export(self):
        filename = filedialog.asksaveasfilename(parent=self.root, title="Export My library", defaultextension=".zip",
                                                initialfile="my-library.zip", filetypes=[("Zip archive", "*.zip")])
        if not filename:
            return
        try:
            count = self.store.mine.export_zip(filename)
            self.status_var.set(f"Exported My library ({count} files and {len(self.store.mine.messages)} messages) to {Path(filename).name}.")
        except OSError as exc:
            messagebox.showerror("Cannot export My library", str(exc), parent=self.root)

    def library_import(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Import a library", filetypes=[("Zip archive", "*.zip")])
        if not filename:
            return
        try:
            added = self.store.mine.import_zip(filename)
        except Exception as exc:
            messagebox.showerror("Cannot import library", str(exc), parent=self.root)
            return
        self._show_my_library()
        self.status_var.set(f"Imported {added['pictures']} pictures, {added['cards']} designs and {added['messages']} messages into My library.")

    def library_open_folder(self):
        folder = self.store.mine.root
        for sub in ("art", "cards"):
            (folder / sub).mkdir(parents=True, exist_ok=True)
        try:
            open_path(folder)
            self.status_var.set("Copy pictures into the art folder, then choose My library again to see them.")
        except OSError:
            messagebox.showinfo("My library folder", str(folder), parent=self.root)

    def _set_icon(self):
        icon = ROOT / "assets/icons/opencardshop.png"
        if icon.is_file():
            try:
                self.window_icon = tk.PhotoImage(master=self.root, file=str(icon))
                self.root.iconphoto(True, self.window_icon)
            except tk.TclError:
                pass

    def selection(self):
        return [obj for obj in self.doc.panels[self.side] if obj.id in self.selected]

    def update_layers(self):
        self._loading_layers = True
        self.layer_tree.delete(*self.layer_tree.get_children())
        for obj in reversed(self.doc.panels[self.side]):
            label = (obj.text.replace("\n", " ") or "Empty text") if obj.kind == "text" else Path(obj.art).stem
            self.layer_tree.insert("", "end", iid=obj.id, text=("Text  ·  " if obj.kind == "text" else "Art  ·  ") + label[:45])
        existing = [identifier for identifier in self.selected if self.layer_tree.exists(identifier)]
        self.layer_tree.selection_set(existing)
        self._loading_layers = False

    def layer_selected(self, event=None):
        if getattr(self, "_loading_layers", False):
            return
        new = set(self.layer_tree.selection())
        if new != self.selected:
            self.selected = new
            self.update_properties()
            self.schedule_render()

    def update_properties(self):
        selected = self.selection()
        obj = selected[0] if len(selected) == 1 else None
        self.property_title.set(("Text" if obj.kind == "text" else Path(obj.art).stem) if obj else (f"{len(selected)} objects selected" if selected else "Click an object on the card"))
        self.text_editor.delete("1.0", "end")
        if obj:
            self.text_editor.insert("1.0", obj.text)
            self.font_var.set(obj.font)
            self.size_var.set(f"{obj.size:.2f}".rstrip("0").rstrip("."))
            self.color_var.set(obj.color)
            self.align_var.set(obj.align)
            self.bold_var.set(obj.bold)
            self.italic_var.set(obj.italic)
            self.underline_var.set(obj.underline)
            self.auto_fit_var.set(obj.auto_fit)
            for name, variable in self.position_vars.items():
                variable.set(f"{getattr(obj, name) / 1000:.3f}")

    def apply_properties(self):
        selected = self.selection()
        if len(selected) != 1:
            return
        obj = selected[0]
        try:
            coordinates = {name: float(variable.get()) * 1000 for name, variable in self.position_vars.items()}
            size = float(self.size_var.get())
            import math
            if not all(math.isfinite(v) and abs(v) <= 100_000 for v in coordinates.values()) or coordinates["w"] <= 0 or coordinates["h"] <= 0 or not 1 <= size <= 400:
                raise ValueError("Use positive width/height and a font size from 1 to 400 points.")
        except ValueError as exc:
            messagebox.showerror("Check object properties", str(exc), parent=self.root)
            return
        before = self.doc.snapshot()
        for name, value in coordinates.items():
            setattr(obj, name, value)
        if obj.kind == "text":
            obj.text = self.text_editor.get("1.0", "end-1c")
            obj.font = self.font_var.get().strip() or "Arial"
            if abs(size - obj.size) > 0.005:
                obj.legacy_cell_height = False
            obj.size = size
            obj.color = self.color_var.get()
            obj.align = self.align_var.get()
            obj.bold, obj.italic, obj.underline = self.bold_var.get(), self.italic_var.get(), self.underline_var.get()
            obj.auto_fit = self.auto_fit_var.get()
        if self.doc != before:
            self.checkpoint(before)
            self.changed()
            self.status_var.set("Object updated.")

    def choose_color(self):
        color = colorchooser.askcolor(self.color_var.get(), parent=self.root, title="Text colour")[1]
        if color:
            self.color_var.set(color)

    def switch_side(self, side):
        if self.doc.fold == "full" and side != "front":
            return
        self.side = side
        self.side_var.set(side)
        self.selected.clear()
        self.changed(False)

    def fit_view(self):
        self.zoom = 1.0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.schedule_render()

    def set_zoom(self, value):
        self.zoom = max(0.5, min(4.0, value))
        self.schedule_render()

    def mouse_wheel(self, event):
        if event.state & 4:
            self.set_zoom(self.zoom * (1.1 if event.delta > 0 else 1 / 1.1))
        else:
            self.canvas.yview_scroll(-2 if event.delta > 0 else 2, "units")

    def schedule_render(self):
        if self.render_job:
            self.root.after_cancel(self.render_job)
        self.render_job = self.root.after(25, self.render)

    def render(self):
        # Direct redraws also replace queued redraws (dragging and selection use
        # this path). Keep the pending Tcl callbacks from outliving the window.
        for name in ("render_job", "start_job"):
            identifier = getattr(self, name, None)
            if identifier:
                self.root.after_cancel(identifier)
                setattr(self, name, None)
        units_w, units_h = self.doc.dimensions(self.side)
        available_w, available_h = max(100, self.canvas.winfo_width() - 64), max(100, self.canvas.winfo_height() - 64)
        self.scale = min(available_w / units_w, available_h / units_h) * self.zoom
        pixels_w = max(1, round(units_w * self.scale))
        self.error_messages = []
        image = render_panel(self.doc, self.side, self.store, width=pixels_w, guides=self.guides_var.get(), errors=self.error_messages)
        ox = max(32, (self.canvas.winfo_width() - image.width) // 2)
        oy = max(32, (self.canvas.winfo_height() - image.height) // 2)
        self.origin = (ox, oy)
        self.canvas.delete("all")
        self.canvas.create_rectangle(ox + 6, oy + 6, ox + image.width + 6, oy + image.height + 6, fill="#c5cfd6", outline="")
        self.canvas_photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(ox, oy, image=self.canvas_photo, anchor="nw")
        self.canvas.create_rectangle(ox, oy, ox + image.width, oy + image.height, outline="#c1cbd2")
        self.canvas.configure(scrollregion=(0, 0, max(self.canvas.winfo_width(), ox + image.width + 32), max(self.canvas.winfo_height(), oy + image.height + 32)))
        self.handles = {}
        for obj in self.selection():
            x, y = ox + obj.x * self.scale, oy + obj.y * self.scale
            right, bottom = x + obj.w * self.scale, y + obj.h * self.scale
            self.canvas.create_rectangle(x, y, right, bottom, outline=ACCENT, width=2, dash=(5, 3))
            if len(self.selected) == 1:
                for name, hx, hy in (("nw", x, y), ("ne", right, y), ("sw", x, bottom), ("se", right, bottom)):
                    self.canvas.create_rectangle(hx - 5, hy - 5, hx + 5, hy + 5, fill="white", outline=ACCENT, width=2)
                    self.handles[name] = (hx, hy)
        if self.error_messages:
            self.status_var.set("Content issue: " + self.error_messages[0])

    def event_point(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        return x, y, (x - self.origin[0]) / self.scale, (y - self.origin[1]) / self.scale

    def press(self, event):
        self.canvas.focus_set()
        x, y, ux, uy = self.event_point(event)
        handle = next((name for name, (hx, hy) in self.handles.items() if abs(x - hx) <= 8 and abs(y - hy) <= 8), None)
        if handle and len(self.selected) == 1:
            mode = "resize"
        else:
            hit = next((o for o in reversed(self.doc.panels[self.side]) if o.x <= ux <= o.x + o.w and o.y <= uy <= o.y + o.h), None)
            if hit:
                if event.state & 1:
                    self.selected.symmetric_difference_update({hit.id})
                elif hit.id not in self.selected:
                    self.selected = {hit.id}
                mode = "move"
            else:
                if not event.state & 1:
                    self.selected.clear()
                mode = "marquee"
        self.drag = {"mode": mode, "handle": handle, "start": (ux, uy), "before": self.doc.snapshot(),
                     "objects": {o.id: (o.x, o.y, o.w, o.h) for o in self.selection()}, "append": bool(event.state & 1)}
        self.update_layers()
        self.update_properties()
        self.render()

    def motion(self, event):
        if not self.drag:
            return
        x, y, ux, uy = self.event_point(event)
        sx, sy = self.drag["start"]
        if self.drag["mode"] == "move":
            for obj in self.selection():
                bx, by, bw, bh = self.drag["objects"][obj.id]
                obj.x, obj.y = bx + ux - sx, by + uy - sy
        elif self.drag["mode"] == "resize":
            obj = self.selection()[0]
            bx, by, bw, bh = self.drag["objects"][obj.id]
            handle = self.drag["handle"]
            fixed_x = bx + bw if "w" in handle else bx
            fixed_y = by + bh if "n" in handle else by
            width, height = max(30, abs(ux - fixed_x)), max(30, abs(uy - fixed_y))
            if obj.kind == "art" and not event.state & 4:
                factor = max(width / bw, height / bh)
                width, height = bw * factor, bh * factor
            obj.w, obj.h = width, height
            obj.x = fixed_x - width if "w" in handle else fixed_x
            obj.y = fixed_y - height if "n" in handle else fixed_y
        else:
            self.canvas.delete("marquee")
            self.canvas.create_rectangle(self.origin[0] + sx * self.scale, self.origin[1] + sy * self.scale,
                                         x, y, outline=ACCENT, dash=(4, 3), tags="marquee")
            return
        self.render()

    def release(self, event):
        if not self.drag:
            return
        if self.drag["mode"] == "marquee":
            _, _, ux, uy = self.event_point(event)
            sx, sy = self.drag["start"]
            left, right = sorted((sx, ux))
            top, bottom = sorted((sy, uy))
            for obj in self.doc.panels[self.side]:
                if left <= obj.x and top <= obj.y and obj.x + obj.w <= right and obj.y + obj.h <= bottom:
                    self.selected.add(obj.id)
            self.changed(False)
        elif self.doc != self.drag["before"]:
            self.checkpoint(self.drag["before"])
            self.changed()
        self.drag = None

    def double_click(self, event):
        if len(self.selection()) == 1 and self.selection()[0].kind == "text":
            self.text_editor.focus_set()
            self.text_editor.tag_add("sel", "1.0", "end-1c")

    def select_all(self):
        self.selected = {o.id for o in self.doc.panels[self.side]}
        self.changed(False)

    def copy(self):
        self.clipboard = copy.deepcopy(self.selection())
        self.clip_art = dict(self.doc.embedded_art)
        self.clip_fonts = dict(self.doc.embedded_fonts)
        for obj in self.clipboard:
            if obj.kind == "art":
                self.clip_art[obj.art] = self.store.art_bytes(obj.art, self.doc)
            else:
                from .assets import font_key
                self.clip_fonts[font_key(obj.font, obj.bold, obj.italic)] = self.store.font_bytes(obj.font, self.doc, obj.bold, obj.italic)
        self.status_var.set(f"Copied {len(self.clipboard)} object(s).")

    def cut(self):
        self.copy()
        self.delete()

    def paste(self):
        if not self.clipboard:
            return
        self.checkpoint()
        self.selected.clear()
        self.doc.embedded_art.update(self.clip_art)
        self.doc.embedded_fonts.update(self.clip_fonts)
        for item in self.clipboard:
            obj = copy.deepcopy(item)
            obj.id = uuid.uuid4().hex
            obj.x += 80
            obj.y += 80
            self.doc.panels[self.side].append(obj)
            self.selected.add(obj.id)
        self.changed()

    def delete(self):
        if self.selected:
            self.checkpoint()
            self.doc.panels[self.side] = [o for o in self.doc.panels[self.side] if o.id not in self.selected]
            self.selected.clear()
            self.changed()

    def reorder(self, front):
        chosen = self.selection()
        if not chosen:
            return
        self.checkpoint()
        remaining = [o for o in self.doc.panels[self.side] if o.id not in self.selected]
        self.doc.panels[self.side] = remaining + chosen if front else chosen + remaining
        self.changed()

    def center_objects(self, axis):
        if not self.selected:
            return
        self.checkpoint()
        units_w, units_h = self.doc.dimensions(self.side)
        for obj in self.selection():
            if axis == "x":
                obj.x = (units_w - obj.w) / 2
            else:
                obj.y = (units_h - obj.h) / 2
        self.changed()

    def center_both(self):
        if not self.selected:
            return
        self.checkpoint()
        units_w, units_h = self.doc.dimensions(self.side)
        for obj in self.selection():
            obj.x, obj.y = (units_w - obj.w) / 2, (units_h - obj.h) / 2
        self.changed()

    def export_png(self):
        self._flush_names()
        filename = filedialog.asksaveasfilename(parent=self.root, title="Export current view", defaultextension=".png",
                                                initialfile=self.doc.title + "_" + self.side + ".png", filetypes=[("PNG image", "*.png")])
        if filename:
            export_panel(self.doc, self.side, self.store, filename)
            self.status_var.set("Exported " + Path(filename).name + " at 300 dpi.")

    def print_dialog(self):
        from .print_ui import PrintDialog
        self.print_controls = PrintDialog(self)

    def show_document(self, filename):
        path = ROOT / "docs" / filename
        text = path.read_text() if path.exists() else "Documentation is included in the docs folder."
        window = tk.Toplevel(self.root)
        window.title(filename.replace("_", " ").replace(".md", "").title())
        window.geometry("820x720")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        widget = tk.Text(frame, wrap="word", font=("DejaVu Sans", 10), background="white", relief="flat", padx=15, pady=15)
        scroll = ttk.Scrollbar(frame, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(fill="both", expand=True)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _welcome(self):
        if self.store.library_occasions:
            return "Choose a design, personalise its names, and edit any side."
        if self.store.starter:
            return ("Using the open starter pack. Choose a design, keep your own pictures and messages in My library, "
                    "or load your CardShop Plus CD with File → Open another asset folder….")
        return ("No CardShop Plus library found. Start a blank card with File → New and add your own text and pictures, "
                "or load your CD with File → Open another asset folder….")

    def _default_font(self):
        """CardShop's BluePrint when the CD is loaded, otherwise an open starter font."""
        names = {name.casefold(): name for name in self.store.fonts}
        return next((names[f.casefold()] for f in ("BluePrint", "Playfair Display") if f.casefold() in names), "Arial")

    def _font_names(self):
        return sorted(set(self.store.fonts) | {"Arial", "Times New Roman"}, key=str.casefold)

    def about(self):
        library = (f"CardShop Plus library: {self.store.library_occasions} occasions · {len(self.store.art_files)} graphics from {self.store.root}"
                   if self.store.library_occasions else "No CardShop Plus library loaded. Use File → Open another asset folder… with your CD.")
        if self.store.starter:
            library += (f"\nOpen starter pack: {len(self.store.starter.occasions)} occasions · {len(self.store.starter.art)} pictures · "
                        f"{sum(len(o.cards) for o in self.store.starter.occasions.values())} cards")
        library += f"\nFonts available: {len(self._font_names())}"
        messagebox.showinfo("OpenCardShop", f"OpenCardShop {__version__}\nNative, offline greeting-card editor.\n\n{library}\nCardShop Plus artwork and fonts retain their original copyright.\nNew application code is MIT licensed.\n\nThis program reconstructs the editor; it does not run the original executable.", parent=self.root)

    def _callback_error(self, exc_type, exc_value, tb):
        traceback.print_exception(exc_type, exc_value, tb)
        messagebox.showerror("OpenCardShop", str(exc_value), parent=self.root)


class MessageDialog:
    """Type a new front / inside / back message for My library."""

    def __init__(self, parent, on_save):
        self.on_save = on_save
        self.window = window = tk.Toplevel(parent)
        window.title("Add a message to My library")
        window.transient(parent)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Fill in any of the parts. Use <receiver> and <sender> where the names should appear.",
                  style="Muted.TLabel", wraplength=460).pack(anchor="w", pady=(0, 8))
        self.fields = {}
        for part in ("front", "inside", "back"):
            ttk.Label(frame, text=part.title()).pack(anchor="w")
            text = tk.Text(frame, width=56, height=3, wrap="word", font=("DejaVu Sans", 10))
            text.pack(fill="x", pady=(2, 8))
            self.fields[part] = text
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Save to My library", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=window.destroy).pack(side="right", padx=6)
        self.fields["front"].focus_set()

    def save(self):
        values = {part: widget.get("1.0", "end").strip() for part, widget in self.fields.items()}
        if not any(values.values()):
            messagebox.showinfo("My library", "Type a message first.", parent=self.window)
            return
        self.window.destroy()
        self.on_save(values["front"], values["inside"], values["back"])
