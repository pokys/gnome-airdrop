import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Status from './status.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
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
        this.transfer = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.progress = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.menu.addMenuItem(this.transfer);
        this.menu.addMenuItem(this.progress);
        this.window = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.menu.addMenuItem(this.window);
        this.duration = new PopupMenu.PopupSubMenuMenuItem('Doba příjmu');
        this.menu.addMenuItem(this.duration);
        this.durationChoices = [];
        for (const seconds of [0, 300, 600]) {
            const item = new PopupMenu.PopupMenuItem(Status.durationLabel(seconds));
            this.duration.menu.addMenuItem(item);
            this.durationChoices.push([seconds, item]);
        }
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
        this._seenResult = undefined;
        this._cancellable = new Gio.Cancellable();
        this._indicator = new AirDropIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._indicator.toggle.connect('toggled', (_item, desired) => this._change(desired));
        this._indicator.folder.connect('activate', () => this._openFolder(this._downloadDir));
        for (const [seconds, item] of this._indicator.durationChoices)
            item.connect('activate', () => this._setDuration(seconds));
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
                    active: `Příjem zapnutý · ${state.session?.receiver_name ?? 'GNOME-AirDrop'}`,
                    activating: 'Zapínám příjem…',
                    deactivating: 'Vypínám a obnovuji Wi-Fi…',
                    inactive: 'Příjem vypnutý',
                    failed: 'Start selhal · příjem je vypnutý',
                };
                this._indicator.status.label.text = state.installed
                    ? (labels[state.state] ?? 'Kontroluji stav…')
                    : 'Backend není nainstalovaný.';
            }
            this._indicator.window.label.text = receiving ? Status.windowText(state.session) : '';
            this._indicator.window.visible = Boolean(this._indicator.window.label.text);
            this._indicator.duration.label.text = `Doba příjmu · ${Status.durationLabel(state.preferences?.duration_seconds ?? 0)}`;
            this._indicator.duration.setSensitive(state.installed && !receiving && !pending && !this._busy);
            const [title, detail] = Status.transferText(state.transfer);
            this._indicator.transfer.label.text = title;
            this._indicator.progress.label.text = detail;
            this._indicator.transfer.visible = Boolean(title);
            this._indicator.progress.visible = Boolean(detail);
            const result = state.transfer?.last_result;
            const resultId = typeof result?.id === 'string' ? result.id : null;
            if (this._seenResult !== undefined && resultId && resultId !== this._seenResult)
                this._notifyResult(result);
            this._seenResult = resultId;
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

    _openFolder(path) {
        if (!path) return;
        try {
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(),
                global.create_app_launch_context(0, -1));
        } catch (error) {
            Main.notify('AirDrop', 'Složku se nepodařilo otevřít.');
            console.error(error);
        }
    }

    async _setDuration(seconds) {
        if (!this._enabled || this._busy) return;
        const generation = this._generation;
        this._busy = true;
        this._indicator.duration.setSensitive(false);
        try {
            await execute([CONTROL, 'set-preferences', JSON.stringify({duration_seconds: seconds})],
                this._cancellable);
        } catch (error) {
            if (this._enabled && generation === this._generation)
                Main.notify('AirDrop', 'Délku příjmu se nepodařilo uložit.');
        } finally {
            if (generation !== this._generation) return;
            this._busy = false;
            if (this._enabled) this._refresh();
        }
    }

    _notifyResult(result) {
        if (!['completed', 'error'].includes(result.phase)) return;
        if (!this._notificationSource) {
            const source = new MessageTray.Source({title: 'AirDrop', iconName: 'document-send-symbolic'});
            source.connect('destroy', () => {
                if (this._notificationSource === source) this._notificationSource = null;
            });
            Main.messageTray.add(source);
            this._notificationSource = source;
        }
        const success = result.phase === 'completed';
        const body = success
            ? (result.file_count > 1 ? `${result.file_count} souborů` : String(result.filename || 'Soubor přijat'))
            : Status.errorMessage(result.error);
        const notification = new MessageTray.Notification({source: this._notificationSource,
            title: success ? 'AirDrop: soubor přijat' : 'AirDrop: přenos nedokončen',
            body, useBodyMarkup: false, privacyScope: MessageTray.PrivacyScope.USER});
        if (success) {
            const path = result.download_dir ?? this._downloadDir;
            notification.addAction('Otevřít složku', () => this._openFolder(path));
        }
        this._notificationSource.addNotification(notification);
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
        this._notificationSource?.destroy();
        this._notificationSource = null;
        this._indicator?.destroy();
        this._indicator = null;
        // The service belongs to the user, not to the Shell process. A Shell
        // restart must not interrupt a transfer or its recovery mechanism.
    }
}
