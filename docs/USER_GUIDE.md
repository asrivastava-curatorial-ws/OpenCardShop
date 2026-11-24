# OpenCardShop user guide

## Opening and making cards

Start OpenCardShop from the Start menu (Windows installer), the applications menu or the `opencardshop` command (Debian package), or with `bash run.sh` in a source folder. The first screen opens a birthday design: the original BDAY1 card when your CardShop Plus CD is loaded, otherwise the open starter pack's balloons card. Use the occasion selector and Cards tab to find another design.

The occasion list holds the starter pack's 14 occasions, your **My library**, and, when the CD is loaded, its 28 occasions (the starter occasions are then marked "starter pack"). Double-click a card or select it and press **Add / open selected**. Opening a design makes an editable copy in memory.

The search field filters the current occasion's cards, artwork, and messages. Clear the field to restore the lists. The supplied blank CMKs are represented by **New side fold**, **New top fold**, and **Full page** rather than shown as empty templates. These buttons preserve the current To/From names.

Opening a starter-pack design or a design from My library also makes an editable copy; the original stays unchanged. Use **Open** for original `.CMK` cards or saved `.occard` cards. The supplied 1993 and V1.20 CMK variants are supported. Other CMK versions, embedded legacy Full Save variants, and other class schemas have not been verified and are rejected if their headers are unsupported.

## Names and messages

Enter the recipient in **To** and the author in **From**. Wherever a text object contains `<receiver>` or `<sender>`, the displayed and printed card uses those names. The placeholders remain in the editable text. Empty name fields leave their placeholders visible so that unfinished personalisation is apparent.

Choose the Messages tab to browse the occasion's messages. Double-click a message to insert its text on the current side. **Add paired front + inside message** inserts the message's corresponding front, inside, and back parts where available. It adds objects rather than replacing an existing design's text; remove or reposition unwanted text objects afterwards.

## My library

My library keeps your own pictures, messages and card designs, ready for every card. Use the **My library** menu, or the **My library ▾** button under the design library:

| Command | What it keeps |
| --- | --- |
| **Add pictures…** | PNG, JPEG, WebP, GIF, BMP, WMF or CMF pictures from your computer. Large pictures are reduced to 2400 pixels on the longer side. |
| **Add a message…** | A message you type, with separate front, inside and back parts. |
| **Save selected picture** | The selected picture on the card. |
| **Save selected text as a message** | The selected text, as a message for the side it is on. |
| **Save this card as a design…** | The whole card, with all its sides, under a name you choose. |

Choose **My library** in the occasion list to use the items: double-click a design to open a copy, a picture to add it, or a message to insert it, exactly like the built-in ones. To delete an item, select it there and choose **Remove selected item…**.

**Export My library…** writes the pictures, designs and messages to one `.zip` file. **Import a library…** adds such a file to your library, keeping what is already there and skipping messages you already have. Use this to move your library to another computer, to set up several kiosk computers the same way, or as a backup. **Open My library folder** opens the folder itself; pictures you copy into its `art` folder appear the next time you choose My library.

My library belongs to your user account and is kept when OpenCardShop is updated or removed: `~/.local/share/opencardshop/my-library/` on Linux and `%LOCALAPPDATA%\OpenCardShop\my-library\` on Windows. Set the `OPENCARDSHOP_HOME` environment variable to keep it, the settings and the caches in a folder of your choice.

## Editing the canvas

Use **Front**, **Inside**, and **Back** above the canvas. Inside is a two-panel spread: its centre guide shows the final fold. Full-page designs use the Front view only.

Click an object to select it. Drag it to move it. Drag a square corner handle to resize it. Artwork normally keeps its proportions; hold Ctrl while resizing artwork to stretch it. Shift-click adds or removes objects from the selection. Drag empty canvas space to select a group. Layers also let you select objects hidden underneath others or outside the visible page.

Double-click text to focus its editor in the properties panel. Change the message, font family, point size, colour, style, and alignment, then press **Apply changes**. Properties are not committed merely by typing into the editor. X, Y, Width, and Height are measured in inches in the original logical page space. Position starts at the current view's top-left corner.

**Fit text within its box** reduces oversized text to fit. The size field remains the requested size, so the rendered text may be smaller. Text is clipped to its object box. Original positive cell-height font metrics are approximated with FreeType; editing a text object's properties switches it to the new editor's point-size layout.

Use **On top**, **Behind**, **Delete**, and the Edit menu to arrange objects. **Centre selected object(s)** centres each selected object in the current view. Some original source cards include objects beyond the page bounds; select those in Layers and centre them if you want them visible.

The properties panel scrolls on smaller screens. The three main panes have draggable dividers. Use **Fit**, **+**, and **−** to adjust the canvas. The minimum client area is 1080 × 720 pixels.

## Artwork and fonts

Choose Artwork to browse the current occasion's illustrations. **Show all artwork** shows every picture in the starter pack, or, with the CD loaded, all 616 unique CD entries. Double-click an illustration to add it. With the CD, three damaged sources use their original low-resolution bitmap previews; their rows are labelled. Two sources without usable previews are marked damaged and cannot be added.

**Import art** accepts PNG, JPEG, BMP, GIF, WebP, and the supported placeable-WMF/CMF subset. Imported artwork is rendered to a PNG resource in the card document. Animated GIFs use their first frame. Unsupported WMF commands are reported instead of silently ignored.

The font list holds the CD's fonts (when loaded), the starter pack's seven display fonts, and the fonts installed on your computer. Font files are used directly, without installing them system-wide. Arial and Times New Roman use the bundled Liberation equivalents; other unavailable families use DejaVu Sans. Saved cards embed the fonts they use, so a card made with an installed font looks the same on a computer that lacks it. The interface uses the desktop's available sans font.

## Saving and moving work

**Save card** writes an `.occard` ZIP document containing readable JSON, all used PNG images, and the actual font variants. You can copy it to another OpenCardShop installation without copying the original library or the fonts. The file opens as an editable card.

Saving uses a temporary file and an atomic replacement so a failed resource conversion does not overwrite the previous saved file. The original source CMK is never overwritten; new saves use `.occard`. The new format is not intended to be opened in the original Windows application. Use **Save as** to keep a different revision.

In a source folder, keep the program files, `assets/` and its fonts together. **File → Open another asset folder** loads CardShop Plus content from your CD or from any folder containing `CARDSHOP.INI`, and OpenCardShop remembers the choice for the next start. Prepared graphics are looked for in a sibling `rendered` folder; without them artwork is drawn by the built-in renderer. A different library may contain unverified formats and cannot be guaranteed to work.

## Printing folded cards

Open **Print / PDF** and select A4, Letter, or Legal. Set **Left**, **Right**, **Top**, and **Bottom** margins from 0 to 25 mm; **Defaults** restores 5 mm. The preview updates as you change settings. It always shows numbered fold guides, and displays the finished card's physical dimensions. Paper and margin choices are remembered in the card after a successful PDF export or printer submission; save the `.occard` to keep them between sessions.

The margins are minimum clearances. For folded cards, the larger left/right margin is reserved at both horizontal edges, and the larger top/bottom margin at both vertical edges. This keeps both creases at the exact centre of the physical sheet. Full-page designs use the separate margins directly. The default 5 mm does not measure your printer's unprintable area; use the test sheet to check it. Larger margins reduce the artwork.

**Save PDF** exports one page at 300 dpi. Print **one-sided**, on the selected paper size, at **Actual size / 100%**. Turn off additional Fit-to-page scaling in the PDF viewer. The artwork keeps the original Letter design proportions. On A4 or Legal the spare space is shared equally between each panel's two outer edges, so the design stays centred on the finished card, while every panel stays against the hinge so spreads remain joined. Fold the **whole sheet** at its centre, including the blank margins.

A normal card PDF has no fold lines. Enable **Print numbered fold guides** to include them on a practice copy. The numbers sit inside the reserved margins; the dashed lines mark the physical centre creases.

Choose **Folding and printer test** under **What to print** to export a diagnostic sheet instead of your artwork. It includes Front, Back, and both Inside faces, UP arrows, corner labels, a printable-area rectangle, and a 100 mm ruler. This leaves your design unchanged. Ready-made practice PDFs are in `examples/print-tests/`.

Place the printed side facing you and make the numbered folds:

| Card type | First fold | Second fold |
| --- | --- | --- |
| Side fold, portrait sheet | Top half behind bottom half | Left half behind right half |
| Top fold, landscape sheet | Left half behind right half | Top half behind bottom half |
| Full page | No folding | No folding |

The front starts in the lower-right quarter and remains visible after both folds. On a side-fold print, the inside is upside down across the upper half, with the back upright at lower left. On a top-fold print, the inside is upside down down the left half and the back is upside down at upper right. After folding, the front, back, and inside should all read upright. Wait for the ink to dry before folding.

This is the original quarter-fold, one-sheet method (**Layout: One-sided, fold twice**): all four physical faces print on **one side of one sheet**, and duplex is unnecessary. For a card twice the size, use the two-sided layout below.

### Two-sided, folded once

Choose **Layout: Two-sided, fold once (half-size card)** for a card half the size of the sheet (A5 from A4), printed on both sides and folded once. The PDF has two pages, and the preview shows them side by side:

| Card type | Sheet | Side 1 (outside) | Side 2 (inside) | Fold |
| --- | --- | --- | --- | --- |
| Side fold | Landscape | Back on the left half, front on the right half | Inside left, inside right | Vertical centre line |
| Top fold | Portrait | Back (upside down) on the top half, front on the bottom half | Inside top, inside bottom | Horizontal centre line |

Print **two-sided with flip on short edge** (in CUPS: `sides=two-sided-short-edge`; OpenCardShop sets it for you), at Actual size / 100%. Flip on long edge would print the inside upside down. Fold once along the centre line with side 1 outside.

Without a duplex unit, tick **No duplex unit: print side 1, then side 2**. OpenCardShop sends side 1, waits while you put the sheet back in the tray, then sends side 2. Printers differ in which way round a sheet must go back in, so print the **Folding and printer test** first, on plain paper:

- Hold it to the light. The red targets on the fold line should lie on top of each other; side 2's millimetre scale shows how far the printer shifted side 2. A shift of 1–3 mm is common, so keep important artwork away from the fold and the edges.
- If side 2 comes out upside down, tick **Turn side 2 upside down** and print the test again.
- If side 2 is printed on the same side as side 1, turn the sheet over before re-inserting it.

Many printers cannot duplex thick card stock automatically; the side 1, then side 2 method works with those. Margins are kept equal on opposite edges so the fold stays on the centre line of both sides.

From the command line: `opencardshop card.occard --layout half --export card.pdf`, then `lp -o media=A4 -o sides=two-sided-short-edge -o print-scaling=none card.pdf`.

Check the test ruler with a real ruler: its end ticks should be 100 mm apart. If the result is shorter, disable Fit-to-page or shrink-to-printable-area scaling. If the rectangle is clipped, increase the affected margin and try again on plain paper. Use card stock only after the test folds correctly.

On Windows, **Print** opens the print-ready PDF in your PDF viewer; print it from there at Actual size / 100% with Fit to page turned off: one-sided for the quarter-fold layout, or two-sided with flip on short edge for the half-fold layout. Linux without the CUPS tools does the same.

For direct printing on Linux, install the CUPS client tools `lp` and `lpstat` (`sudo apt install cups-client`) and configure a printer in Linux Settings. The app asks for a printer queue and 1-99 copies, then sends the selected card or test sheet with the selected media, one-sided output, and scaling disabled. The submission options were checked with a simulated queue; no real printer was available. Saving a PDF also works when CUPS is unavailable.

## Keyboard shortcuts

| Action | Shortcut |
| --- | --- |
| Open / Save / Save as | Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| Print / PDF | Ctrl+P |
| Undo / Redo | Ctrl+Z / Ctrl+Y |
| Cut / Copy / Paste | Ctrl+X / Ctrl+C / Ctrl+V |
| Select all / Delete | Ctrl+A / Delete |
| Nudge selected objects | Arrow keys |
| Larger nudge | Shift+arrow |
| Zoom with mouse | Ctrl+mouse wheel |

Object-editing shortcuts apply while the canvas has focus. Text widgets keep their normal text-editing shortcuts.

## Troubleshooting

**Missing Tk or ImageTk:** install all packages in the README's command. Ubuntu/Debian and Fedora split Pillow's Tk integration into an additional package. Virtual environments still require the system Tk library.

**Windows protected your PC:** the installer is not code-signed. Choose **More info → Run anyway** if you downloaded it from a source you trust.

**Nothing happens on Windows when OpenCardShop starts:** a start-up error is shown in a message box. For details, run `opencardshop-cli.cmd` from a Command Prompt in the installation folder (`%LOCALAPPDATA%\Programs\OpenCardShop`); it prints errors to the console.

**An installed font is missing from the list:** OpenCardShop lists TrueType and OpenType fonts (`.ttf`, `.otf`, `.ttc`). On Windows the list is cached in `%LOCALAPPDATA%\OpenCardShop\Cache`; delete `system-fonts.json` there to rebuild it. On Linux fonts are read from fontconfig (`fc-list`).

**No display / cannot connect to display:** start the graphical editor in a desktop session. A server can still use `main.py CARD --export OUTPUT.pdf` or `.png` without a display. Tk uses X11 or XWayland.

**Artwork shows a content issue:** check `assets/rendered/asset_report.json` and the recovery report. Keep the cache with the program. Rebuilding the cache with Inkscape is a developer action, not required for normal use.

**Properties or layers extend below the window:** scroll the right-hand panel. Increase the window size or move a pane divider for a larger canvas.

**Changed text is not visible:** press Apply changes, check the selected view and layer order, and check its bounds. Auto-fit can shrink a long message; enlarge the text box for more readable text.

**There is whitespace around the fold layout:** the design retains its original Letter proportions, so on A4 or Legal each panel is centred in its quarter of the sheet with equal space at its two outer edges. Use the fold guides in the preview and a practice sheet before using card stock.
