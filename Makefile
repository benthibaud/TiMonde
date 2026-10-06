PREFIX ?= /usr/local
DESTDIR ?=
BINDIR ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share
APPSDIR ?= $(DATADIR)/applications
ICONSDIR ?= $(DATADIR)/icons/hicolor/scalable

all: build

build:
	cargo build --release

install: build
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 target/release/timonde $(DESTDIR)$(BINDIR)/timonde
	install -d $(DESTDIR)$(APPSDIR)
	install -m 644 data/timonde.desktop $(DESTDIR)$(APPSDIR)/timonde.desktop
	install -d $(DESTDIR)$(ICONSDIR)/apps
	install -d $(DESTDIR)$(ICONSDIR)/panel
	install -m 644 data/icons/timonde_on.svg $(DESTDIR)$(ICONSDIR)/apps/timonde_on.svg
	install -m 644 data/icons/timonde_off.svg $(DESTDIR)$(ICONSDIR)/panel/timonde_off.svg
	install -m 644 data/icons/timonde_on.svg $(DESTDIR)$(ICONSDIR)/panel/timonde_on.svg
	install -m 644 data/icons/timonde_error.svg $(DESTDIR)$(ICONSDIR)/panel/timonde_error.svg
	install -d $(DESTDIR)$(DATADIR)/timonde/scripts
	install -m 755 data/scripts/reorder_groups.py $(DESTDIR)$(DATADIR)/timonde/scripts/reorder_groups.py

install-user: build
	install -d $(HOME)/.local/bin
	install -m 755 target/release/timonde $(HOME)/.local/bin/timonde
	install -d $(HOME)/.local/share/applications
	install -m 644 data/timonde.desktop $(HOME)/.local/share/applications/timonde.desktop
	install -d $(HOME)/.local/share/icons/hicolor/scalable/apps
	install -d $(HOME)/.local/share/icons/hicolor/scalable/panel
	install -m 644 data/icons/timonde_on.svg $(HOME)/.local/share/icons/hicolor/scalable/apps/timonde_on.svg
	install -m 644 data/icons/timonde_off.svg $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_off.svg
	install -m 644 data/icons/timonde_on.svg $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_on.svg
	install -m 644 data/icons/timonde_error.svg $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_error.svg
	install -d $(HOME)/.local/share/timonde/scripts
	install -m 755 data/scripts/reorder_groups.py $(HOME)/.local/share/timonde/scripts/reorder_groups.py

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/timonde
	rm -f $(DESTDIR)$(APPSDIR)/timonde.desktop
	rm -f $(DESTDIR)$(ICONSDIR)/apps/timonde_on.svg
	rm -f $(DESTDIR)$(ICONSDIR)/panel/timonde_off.svg
	rm -f $(DESTDIR)$(ICONSDIR)/panel/timonde_on.svg
	rm -f $(DESTDIR)$(ICONSDIR)/panel/timonde_error.svg

test:
	cargo test

clean:
	cargo clean
