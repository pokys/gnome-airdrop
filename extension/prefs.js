import Adw from 'gi://Adw?version=1';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk?version=4.0';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const CONTROL = '/opt/gnome-airdrop/bin/control.py';

function run(argv) {
    return new Promise((resolve, reject) => {
        try {
            const process = Gio.Subprocess.new(argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            process.communicate_utf8_async(null, null, (source, result) => {
                try {
                    const [, stdout, stderr] = source.communicate_utf8_finish(result);
                    if (!source.get_successful())
                        throw new Error(stderr.trim());
                    resolve(stdout);
                } catch (error) { reject(error); }
            });
        } catch (error) { reject(error); }
    });
}

export default class AirDropPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const page = new Adw.PreferencesPage({title: 'AirDrop', icon_name: 'document-send-symbolic'});
        const group = new Adw.PreferencesGroup({title: 'Přijaté soubory',
            description: 'Složku můžete změnit, když je příjem vypnutý.'});
        const row = new Adw.ActionRow({title: 'Ukládat do', subtitle: 'Načítám…'});
        const button = new Gtk.Button({label: 'Vybrat složku…', valign: Gtk.Align.CENTER});
        row.add_suffix(button);
        group.add(row);
        page.add(group);
        window.add(page);
        let closed = false;
        window.connect('close-request', () => {closed = true; return false;});
        const refresh = async () => {
            try {
                const state = JSON.parse(await run([CONTROL, 'status']));
                if (closed) return;
                row.subtitle = state.download_dir;
                button.sensitive = ['inactive', 'failed'].includes(state.state);
            } catch (error) {
                if (!closed) { row.subtitle = 'Přijímač není dostupný.'; button.sensitive = false; }
            }
        };
        button.connect('clicked', () => {
            const dialog = new Gtk.FileDialog({title: 'Složka pro přijaté soubory'});
            if (row.subtitle.startsWith('/'))
                dialog.initial_folder = Gio.File.new_for_path(row.subtitle);
            dialog.select_folder(window, null, async (source, result) => {
                try {
                    const path = source.select_folder_finish(result)?.get_path();
                    if (!path || closed) return;
                    await run([CONTROL, 'set-download-dir', path]);
                    await refresh();
                } catch (error) {
                    if (closed || error.matches?.(Gtk.DialogError, Gtk.DialogError.DISMISSED)) return;
                    row.subtitle = error.message;
                }
            });
        });
        refresh();
    }
}
