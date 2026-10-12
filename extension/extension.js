import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const CONTROL = '/opt/gnome-airdrop/bin/control.py';

function execute(argv, cancellable, timeoutSeconds = 8) {
    return new Promise((resolve, reject) => {
        let process;
        try {
            process = Gio.Subprocess.new(argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        } catch (error) {
            reject(error);
            return;
        }
        let timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, timeoutSeconds, () => {
            timeout = 0;
            process.force_exit();
            return GLib.SOURCE_REMOVE;
        });
        process.communicate_utf8_async(null, cancellable, (source, result) => {
            if (timeout)
                GLib.source_remove(timeout);
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(result);
                if (!source.get_successful())
                    throw new Error(stderr.trim() || 'Příkaz se nepodařilo dokončit.');
                resolve(stdout);
            } catch (error) {
                // Cancelling a Gio operation alone does not stop its child.
                process.force_exit();
                reject(error);
            }
        });
    });
}

const AirDropIndicator = GObject.registerClass(
class AirDropIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'GNOME AirDrop');
        this.icon = new St.Icon({icon_name: 'document-send-symbolic',
            style_class: 'system-status-icon'});
        this.add_child(this.icon);
        this.toggle = new PopupMenu.PopupSwitchMenuItem('Přijímat soubory', false);
        this.menu.addMenuItem(this.toggle);
        this.status = new PopupMenu.PopupMenuItem('Kontroluji stav…', {reactive: false});
        this.menu.addMenuItem(this.status);
        this.menu.addMenuItem(new PopupMenu.PopupMenuItem(
            'Během příjmu se běžná Wi-Fi odpojí.', {reactive: false}));
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.folder = new PopupMenu.PopupMenuItem('Otevřít přijaté soubory');
        this.menu.addMenuItem(this.folder);
        this.preferences = new PopupMenu.PopupMenuItem('Nastavení…');
        this.menu.addMenuItem(this.preferences);
    }
});

export default class GnomeAirDropExtension extends Extension {
    enable() {
        this._generation = (this._generation ?? 0) + 1;
        this._enabled = true;
        this._busy = false;
        this._polling = false;
        this._seenReceipt = undefined;
        this._cancellable = new Gio.Cancellable();
        this._indicator = new AirDropIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._indicator.toggle.connect('toggled', (_item, desired) => this._change(desired));
        this._indicator.folder.connect('activate', () => {
            if (!this._downloadDir)
                return;
            try {
                const uri = Gio.File.new_for_path(this._downloadDir).get_uri();
                Gio.AppInfo.launch_default_for_uri(uri, global.create_app_launch_context(0, -1));
            } catch (error) {
                Main.notify('AirDrop', 'Složku se nepodařilo otevřít.');
                console.error(error);
            }
        });
        this._indicator.preferences.connect('activate', () => this.openPreferences());
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }

    async _change(desired) {
        if (!this._enabled || this._busy || this._syncingToggle)
            return;
        this._busy = true;
        const generation = this._generation;
        this._indicator.toggle.setSensitive(false);
        this._indicator.status.label.text = 'Ověřte heslo nebo otisk…';
        try {
            await execute(['/usr/bin/pkexec', CONTROL, desired ? 'start' : 'stop'],
                this._cancellable, 120);
        } catch (error) {
            if (this._enabled && generation === this._generation) {
                Main.notify('AirDrop', 'Změna nebyla dokončena. Zkontrolujte stav v nabídce.');
                console.error(error);
            }
        } finally {
            if (generation !== this._generation)
                return;
            this._busy = false;
            if (this._enabled)
                this._refresh();
        }
    }

    async _refresh() {
        if (!this._enabled || this._polling)
            return;
        this._polling = true;
        const generation = this._generation;
        try {
            if (!GLib.file_test(CONTROL, GLib.FileTest.IS_EXECUTABLE))
                throw new Error('Backend není nainstalovaný.');
            const state = JSON.parse(await execute([CONTROL, 'status'], this._cancellable));
            if (!this._enabled || generation !== this._generation)
                return;
            this._downloadDir = state.download_dir;
            const receiving = state.receiving === true;
            const pending = state.state === 'activating' || state.state === 'deactivating';
            this._setToggleState(receiving || state.state === 'activating');
            this._indicator.toggle.setSensitive(state.installed && !this._busy && !pending);
            this._indicator.folder.setSensitive(Boolean(this._downloadDir));
            this._indicator.icon.opacity = receiving ? 255 : 120;
            if (!this._busy) {
                const labels = {
                    active: 'Příjem zapnutý · GNOME-AirDrop',
                    activating: 'Zapínám příjem…',
                    deactivating: 'Vypínám a obnovuji Wi-Fi…',
                    inactive: 'Příjem vypnutý',
                    failed: 'Start selhal · příjem je vypnutý',
                };
                this._indicator.status.label.text = state.installed
                    ? (labels[state.state] ?? 'Kontroluji stav…')
                    : 'Backend není nainstalovaný.';
            }
            const receipt = state.receipt;
            const receiptId = typeof receipt?.id === 'string' ? receipt.id : null;
            if (this._seenReceipt !== undefined && receiptId && receiptId !== this._seenReceipt) {
                const names = Array.isArray(receipt.files)
                    ? receipt.files.filter(name => typeof name === 'string') : [];
                if (names.length) {
                    const body = names.length === 1 ? names[0] : `${names.length} souborů`;
                    Main.notify('AirDrop: soubor přijat', GLib.markup_escape_text(body, -1));
                }
            }
            this._seenReceipt = receiptId;
        } catch (error) {
            if (this._enabled && generation === this._generation && !this._busy) {
                this._setToggleState(false);
                this._indicator.toggle.setSensitive(false);
                this._indicator.status.label.text = 'Backend není dostupný.';
            }
        } finally {
            if (generation === this._generation)
                this._polling = false;
        }
    }

    _setToggleState(state) {
        // GNOME 50 emits "toggled" for programmatic state changes too.
        this._syncingToggle = true;
        try {
            this._indicator.toggle.setToggleState(state);
        } finally {
            this._syncingToggle = false;
        }
    }

    disable() {
        this._generation++;
        this._enabled = false;
        if (this._timer) {
            GLib.source_remove(this._timer);
            this._timer = null;
        }
        this._cancellable?.cancel();
        this._indicator?.destroy();
        this._indicator = null;
        // The service belongs to the user, not to the Shell process. A Shell
        // restart must not interrupt a transfer or its recovery mechanism.
    }
}
