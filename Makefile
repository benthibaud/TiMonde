PREFIX ?= /usr/local
DESTDIR ?=
BINDIR ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share
APPSDIR ?= $(DATADIR)/applications
ICONSDIR ?= $(DATADIR)/icons/hicolor/scalable

all: build

icons:
	python3 scripts/generate_png_icons.py

mo:
	@mkdir -p po/locale
	@for po in po/*.po; do \
		lang=$$(basename "$$po" .po); \
		mkdir -p "po/locale/$$lang/LC_MESSAGES"; \
		msgfmt -o "po/locale/$$lang/LC_MESSAGES/timonde.mo" "$$po"; \
	done

build: mo icons
	cargo build --release

install: build
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 target/release/timonde $(DESTDIR)$(BINDIR)/timonde
	install -d $(DESTDIR)$(APPSDIR)
	install -m 644 data/timonde.desktop $(DESTDIR)$(APPSDIR)/timonde.desktop
	install -d $(DESTDIR)$(DATADIR)/metainfo
	install -m 644 data/io.github.benthibaud.timonde.metainfo.xml $(DESTDIR)$(DATADIR)/metainfo/io.github.benthibaud.timonde.metainfo.xml
	install -d $(DESTDIR)$(ICONSDIR)/apps
	install -d $(DESTDIR)$(ICONSDIR)/panel
	install -m 644 data/icons/timonde_on.svg $(DESTDIR)$(ICONSDIR)/apps/timonde_on.svg
	install -m 644 data/icons/timonde_off.svg $(DESTDIR)$(ICONSDIR)/panel/timonde_off.svg
	install -m 644 data/icons/timonde_on.svg $(DESTDIR)$(ICONSDIR)/panel/timonde_on.svg
	install -m 644 data/icons/timonde_error.svg $(DESTDIR)$(ICONSDIR)/panel/timonde_error.svg
	cp -r data/icons/hicolor/* $(DESTDIR)$(DATADIR)/icons/hicolor/
	install -d $(DESTDIR)$(DATADIR)/timonde/icons
	install -m 644 data/icons/pan-end-symbolic*.svg $(DESTDIR)$(DATADIR)/timonde/icons/
	install -d $(DESTDIR)$(DATADIR)/timonde/scripts
	install -m 755 data/scripts/reorder_groups.py $(DESTDIR)$(DATADIR)/timonde/scripts/reorder_groups.py
	install -m 755 data/scripts/edit_station.py $(DESTDIR)$(DATADIR)/timonde/scripts/edit_station.py
	install -m 755 data/scripts/browse_bouquets.py $(DESTDIR)$(DATADIR)/timonde/scripts/browse_bouquets.py
	install -m 755 data/scripts/timonde_xembed_bridge.py $(DESTDIR)$(DATADIR)/timonde/scripts/timonde_xembed_bridge.py
	install -m 755 data/scripts/patch_cinnamon_status_applet.py $(DESTDIR)$(DATADIR)/timonde/scripts/patch_cinnamon_status_applet.py
	install -m 755 data/scripts/timonde_settings.py $(DESTDIR)$(DATADIR)/timonde/scripts/timonde_settings.py
	install -m 755 data/scripts/gnome_tray_helper.py $(DESTDIR)$(DATADIR)/timonde/scripts/gnome_tray_helper.py
	install -m 755 data/scripts/show_menu.py $(DESTDIR)$(DATADIR)/timonde/scripts/show_menu.py
	install -m 644 data/scripts/timonde_i18n.py $(DESTDIR)$(DATADIR)/timonde/scripts/timonde_i18n.py
	install -m 644 data/scripts/timonde_common.py $(DESTDIR)$(DATADIR)/timonde/scripts/timonde_common.py
	install -m 644 data/scripts/timonde_world_data.py $(DESTDIR)$(DATADIR)/timonde/scripts/timonde_world_data.py
	for mo in po/locale/*/LC_MESSAGES/timonde.mo; do \
		lang=$$(echo $$mo | cut -d/ -f3); \
		install -d $(DESTDIR)$(DATADIR)/locale/$$lang/LC_MESSAGES; \
		install -m 644 $$mo $(DESTDIR)$(DATADIR)/locale/$$lang/LC_MESSAGES/timonde.mo; \
	done
	install -d $(DESTDIR)$(DATADIR)/timonde/bouquets
	install -m 644 data/bouquets/*.xml $(DESTDIR)$(DATADIR)/timonde/bouquets/
	install -d $(DESTDIR)$(DATADIR)/timonde/examples
	install -m 644 data/examples/* $(DESTDIR)$(DATADIR)/timonde/examples/
	@if [ -d "/usr/share/cinnamon/applets/xapp-status@cinnamon.org" ] && [ -z "$(DESTDIR)" ]; then \
		python3 data/scripts/patch_cinnamon_status_applet.py --system || true; \
	fi

install-user: build
	install -d $(HOME)/.local/bin
	install -m 755 target/release/timonde $(HOME)/.local/bin/timonde
	install -d $(HOME)/.local/share/applications
	install -m 644 data/timonde.desktop $(HOME)/.local/share/applications/timonde.desktop
	install -d $(HOME)/.local/share/metainfo
	install -m 644 data/io.github.benthibaud.timonde.metainfo.xml $(HOME)/.local/share/metainfo/io.github.benthibaud.timonde.metainfo.xml
	install -d $(HOME)/.local/share/icons/hicolor/scalable/apps
	install -d $(HOME)/.local/share/icons/hicolor/scalable/panel
	install -m 644 data/icons/timonde_on.svg $(HOME)/.local/share/icons/hicolor/scalable/apps/timonde_on.svg
	install -m 644 data/icons/timonde_off.svg $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_off.svg
	install -m 644 data/icons/timonde_on.svg $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_on.svg
	install -m 644 data/icons/timonde_error.svg $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_error.svg
	cp -r data/icons/hicolor/* $(HOME)/.local/share/icons/hicolor/
	install -d $(HOME)/.local/share/timonde/icons
	install -m 644 data/icons/pan-end-symbolic*.svg $(HOME)/.local/share/timonde/icons/
	install -d $(HOME)/.local/share/timonde/scripts
	install -m 755 data/scripts/reorder_groups.py $(HOME)/.local/share/timonde/scripts/reorder_groups.py
	install -m 755 data/scripts/edit_station.py $(HOME)/.local/share/timonde/scripts/edit_station.py
	install -m 755 data/scripts/browse_bouquets.py $(HOME)/.local/share/timonde/scripts/browse_bouquets.py
	install -m 755 data/scripts/timonde_xembed_bridge.py $(HOME)/.local/share/timonde/scripts/timonde_xembed_bridge.py
	install -m 755 data/scripts/patch_cinnamon_status_applet.py $(HOME)/.local/share/timonde/scripts/patch_cinnamon_status_applet.py
	install -m 755 data/scripts/timonde_settings.py $(HOME)/.local/share/timonde/scripts/timonde_settings.py
	install -m 755 data/scripts/gnome_tray_helper.py $(HOME)/.local/share/timonde/scripts/gnome_tray_helper.py
	install -m 755 data/scripts/show_menu.py $(HOME)/.local/share/timonde/scripts/show_menu.py
	install -m 644 data/scripts/timonde_i18n.py $(HOME)/.local/share/timonde/scripts/timonde_i18n.py
	install -m 644 data/scripts/timonde_common.py $(HOME)/.local/share/timonde/scripts/timonde_common.py
	install -m 644 data/scripts/timonde_world_data.py $(HOME)/.local/share/timonde/scripts/timonde_world_data.py
	for mo in po/locale/*/LC_MESSAGES/timonde.mo; do \
		lang=$$(echo $$mo | cut -d/ -f3); \
		install -d $(HOME)/.local/share/locale/$$lang/LC_MESSAGES; \
		install -m 644 $$mo $(HOME)/.local/share/locale/$$lang/LC_MESSAGES/timonde.mo; \
	done
	install -d $(HOME)/.local/share/timonde/bouquets
	install -m 644 data/bouquets/*.xml $(HOME)/.local/share/timonde/bouquets/
	install -d $(HOME)/.local/share/timonde/examples
	install -m 644 data/examples/* $(HOME)/.local/share/timonde/examples/
	@if [ -d "$(HOME)/.local/share/cinnamon" ]; then \
		python3 data/scripts/patch_cinnamon_status_applet.py --user || true; \
	fi

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/timonde
	rm -f $(DESTDIR)$(APPSDIR)/timonde.desktop
	rm -f $(DESTDIR)$(DATADIR)/metainfo/io.github.benthibaud.timonde.metainfo.xml
	rm -f $(DESTDIR)$(ICONSDIR)/apps/timonde_on.svg
	rm -f $(DESTDIR)$(ICONSDIR)/panel/timonde_off.svg
	rm -f $(DESTDIR)$(ICONSDIR)/panel/timonde_on.svg
	rm -f $(DESTDIR)$(ICONSDIR)/panel/timonde_error.svg
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/*/apps/timonde_*.png
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/*/panel/timonde_*.png
	rm -rf $(DESTDIR)$(DATADIR)/timonde
	rm -f $(DESTDIR)$(DATADIR)/locale/*/LC_MESSAGES/timonde.mo
	@if [ -f "/usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js.orig_timonde" ] && [ -z "$(DESTDIR)" ]; then \
		python3 data/scripts/patch_cinnamon_status_applet.py --restore || true; \
	fi

uninstall-user:
	rm -f $(HOME)/.local/bin/timonde
	rm -f $(HOME)/.local/share/applications/timonde.desktop
	rm -f $(HOME)/.local/share/metainfo/io.github.benthibaud.timonde.metainfo.xml
	rm -f $(HOME)/.local/share/icons/hicolor/scalable/apps/timonde_on.svg
	rm -f $(HOME)/.local/share/icons/hicolor/scalable/panel/timonde_*.svg
	rm -rf $(HOME)/.local/share/icons/hicolor/*/apps/timonde_*.png
	rm -rf $(HOME)/.local/share/icons/hicolor/*/panel/timonde_*.png
	rm -rf $(HOME)/.local/share/timonde
	rm -f $(HOME)/.local/share/locale/*/LC_MESSAGES/timonde.mo
	@if [ -d "$(HOME)/.local/share/cinnamon/applets/xapp-status@cinnamon.org" ]; then \
		python3 data/scripts/patch_cinnamon_status_applet.py --restore || true; \
	fi

check-arch:
	python3 scripts/check_architecture.py

test: check-arch
	cargo test
	python3 tests/test_timonde_common.py
	python3 tests/test_gtk_event_loop.py

clean:
	cargo clean
	rm -rf packaging/dist

deb: build
	packaging/deb/build_deb.sh

rpm: build
	packaging/rpm/build_rpm.sh
