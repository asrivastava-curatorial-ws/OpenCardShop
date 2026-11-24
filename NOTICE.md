# Notices and asset provenance

The OpenCardShop Python application, launcher, packaging scripts, developer tools, tests and documentation are covered by `LICENSE` (MIT).

## Open content included with OpenCardShop

These files may be redistributed with the application, including in the Debian package and the Windows installer:

- **Starter pack clipart** (`assets/starter/art/`, except `bg-*.webp`) and the **application icon** (`assets/icons/`): Microsoft Fluent Emoji, <https://github.com/microsoft/fluentui-emoji>, Copyright (c) Microsoft Corporation, MIT licence (`assets/starter/LICENSE-FluentEmoji.txt`). Converted from SVG to WebP/PNG.
- **Starter pack backgrounds** (`assets/starter/art/bg-*.webp`), **ready-made cards** (`assets/starter/cards/`) and **messages** (`assets/starter/library.json`): newly made for OpenCardShop, MIT licence.
- **Starter pack fonts** (`assets/starter/fonts/`): Baloo 2, Caveat, Dancing Script, Great Vibes, Lobster, Pacifico and Playfair Display from Google Fonts, SIL Open Font License 1.1. Each font's copyright line and licence are in the `OFL-*.txt` file beside it.
- **Fallback fonts** (`assets/fallback_fonts/`): DejaVu Sans (`LICENSE-DejaVu.txt`) and Liberation Sans/Serif (SIL Open Font License 1.1, `LICENSE-Liberation.txt`). The Debian package links to the system's `fonts-dejavu-core` and `fonts-liberation` copies instead.

`assets/starter/ATTRIBUTION.md` lists the source of every starter-pack file. `tools/build_starter_pack.py` rebuilds the pack from those sources.

## Third-party software in the Windows installer

The Windows installer bundles Python (Python Software Foundation License, `runtime\LICENSE_PYTHON.txt`), Tcl/Tk (BSD-style licence, `runtime\tcl\tk8.6\license.terms`), the Microsoft Visual C++ runtime redistributable files, OpenSSL, zlib, libffi, SQLite, Expat, XZ and bzip2 as packaged by conda-forge (each licence text is in `runtime\licenses\<component>`), and Pillow (MIT-CMU licence, `runtime\Lib\site-packages\pillow-*.dist-info\licenses`). On Linux these come from the distribution.

## CardShop Plus content is not included

This repository and its packages contain no CardShop Plus content. The original program, clipart, card templates, fonts, previews, messages and help remain the property of their copyright holders. A program being out of print or described as abandonware does not place its content in the public domain or transfer any rights. Users supply that content themselves, from their own CD or a privately kept asset pack, and git ignores it: `assets/original/` (except its README), `assets/rendered/` (artwork rendered from the CD), the example cards and their images in `examples/` (saved cards embed CD artwork and fonts), and `docs/Original_CardShopPlus_help.txt`. The MIT licence does not apply to any of that content.

`docs/screenshots/starter.png` shows only open content. The other screenshots in `docs/screenshots/` show the editor working with CardShop Plus content, for documentation.
