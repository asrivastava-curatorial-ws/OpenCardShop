# Original-program run and printing comparison

Date: 12 October 2026. Updated native application: OpenCardShop 1.1.0.

## What actually ran

The supplied 247,472-byte `CARDSHOP.EXE` was executed through classic **32-bit Wine 9** in an isolated, CPU-emulated Linux guest. The supplied executable and original files were copied into a private test installation. The test copy's INI artwork path was adjusted to its installation folder; the distributed originals were not changed. The guest had an X11 display, no network interface, and no real printer.

The original CardShop Plus editor opened with its occasion, artwork, message, and card palettes. `BDAY/BDAY1.CMK` was opened with the original File Open command. The drawing displayed its birthday-party artwork and text. Editing Receiver to Aditi and Sender to Ravi updated the front greeting to `Hey Aditi`. The window title identified `BDAY1.CMK` and the status identified a Side Fold card. An actual screenshot is in `screenshots/original-birthday.png`.

The original Print command created Print windows, and File > Print Preview opened a window titled Print Preview. These modal windows were incompletely painted in the compatibility runtime, appearing as black client rectangles. A small Print modal prevented further reliable inspection of that path and was dismissed. A basic window manager did not resolve the painting issue. No readable original print preview, printer job, or exported print file was obtained. Therefore this run confirms startup, opening a supplied card, artwork/text drawing, and name substitution; it does not establish exact original print output or full feature parity.

The first attempted Wine 11 runtime did not start the application successfully in this environment. Running Wine directly on the host was also blocked by the host's restriction on Unix-domain sockets. The emulated guest allowed the successful classic 32-bit run. These compatibility dependencies and the test guest are not required or distributed with the native application.

## Evidence used for the printing update

The runnable UI was supplemented by the supplied help and decoded executable resources. The following distinctions prevent static resource evidence from being mistaken for a completed original printer test.

| Feature | Original evidence | Native 1.1.0 result |
| --- | --- | --- |
| One-sided, four-face layout | Help explicitly says every card side prints on one side of the paper and upside-down faces become upright after folding | One PDF page contains Front, Back, and both Inside faces; independent physical-fold checks pass for side and top folds |
| Two folds and their order | Help describes two folds; portrait preview resource 194 labels the horizontal first fold and vertical second fold; landscape resource 196 reverses that order | Numbered guides in the live preview, separate directions for side and top folds, optional guides on practice copies |
| Clean finished cards | Help says fold lines appear in preview and are not printed on the card | Card PDFs have no guides by default, although preview guides remain visible |
| Legal paper | Help names Letter and Legal finished-card sizes | A4, Letter, and Legal selection, with finished physical dimensions shown |
| Four margins | Dialog resource 199 has Left, Right, Top, and Bottom fields | Four minimum margins, retained in portable saves; folded artwork remains centred on physical paper even when margins differ |
| Printer test | Help describes a rectangle for checking placement and margins; Print resource 198 includes Test Page | A marked test sheet with printable-area border, four face names, UP arrows, corners, numbered folds, and a 100 mm ruler |
| Copy count and printer selection | Original print/setup help and resource controls | CUPS queue selection and 1-99 copies, selected paper, one-sided output, and scaling disabled; submission checked with a simulated queue |
| Portable save | Help and Save As resource 205 name Full Save | Existing `.occard` saving embeds artwork and actual fonts; no unsupported legacy Full Save decoder was inferred from the checkbox |

The new diagnostic sheet extends the original rectangle test to make orientation and scaling easy to check on a modern printer. The larger opposing margins are matched for folded cards because an asymmetric printable rectangle must not move either crease away from the physical sheet's centre. Full-page designs use their separate margins directly.

No duplex layout was added: the recovered card format is a quarter-fold sheet, so all four visible faces are arranged on one printed side. The sheet's blank side becomes concealed between folded layers. A card printed on both sides and folded once would require a different layout and was not identified as an original feature.

The original paper order and postal registration forms are obsolete and were not recreated as native features. Unsupported embedded legacy bitmap classes were not implemented without samples of their serialized data.

## Native verification and remaining limits

All 43 automated checks passed: 15 core, 6 executable, 11 paper/folding, and 11 native desktop checks. These verify both fold orientations, all four faces, centring, Legal geometry, guide-free normal output, portable print settings, invalid margins, real PDF export, and simulated CUPS submission. Three exported practice PDFs were rendered and visually reviewed; their instructions are in `examples/print-tests/README.md`.

The source, asset bytes, and original executable in the package remain preserved. Exact Win16 font metrics, GDI rasterisation, an original Windows 3.1 print job, and real printer scale/paper handling are still outside this comparison. Use a plain-paper diagnostic print at Actual size / 100% before using card stock. The full validation record is in `VALIDATION_REPORT.md`.
