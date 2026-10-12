import Adw from 'gi://Adw?version=1';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk?version=4.0';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const CONTROL = '/opt/gnome-airdrop/bin/control.py';

function run(argv, cancellable) {
    return new Promise((resolve, reject) => {
        let process;
        try {
            process = Gio.Subprocess.new(argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        } catch (error) { reject(error); return; }
        let timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 8, () => {
            timeout = 0;
            process.force_exit();
            return GLib.SOURCE_REMOVE;
        });
        process.communicate_utf8_async(null, cancellable, (source, result) => {
            if (timeout) GLib.source_remove(timeout);
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(result);
                if (!source.get_successful()) throw new Error(stderr.trim());
                resolve(stdout);
            } catch (error) { process.force_exit(); reject(error); }
        });
    });
}

export default class AirDropPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const cancellable = new Gio.Cancellable();
        let closed = false;
        window.connect('close-request', () => {closed = true; cancellable.cancel(); return false;});
        const page = new Adw.PreferencesPage({title: 'AirDrop', icon_name: 'document-send-symbolic'});
        const group = new Adw.PreferencesGroup({title: 'Příjem souborů',
            description: 'Změny se použijí při příštím zapnutí příjmu.'});
        const name = new Adw.EntryRow({title: 'Jméno na iPhonu'});
        const duration = new Adw.ComboRow({title: 'Výchozí délka příjmu',
            model: Gtk.StringList.new(['Do vypnutí', '5 minut', '10 minut'])});
        const folder = new Adw.ActionRow({title: 'Ukládat do', subtitle: 'Načítám…'});
        const choose = new Gtk.Button({label: 'Vybrat složku…', valign: Gtk.Align.CENTER});
        folder.add_suffix(choose);
        const save = new Gtk.Button({label: 'Uložit nastavení', valign: Gtk.Align.CENTER});
        const result = new Adw.ActionRow({title: 'Nastavení', subtitle: ''});
        result.add_suffix(save);
        for (const row of [name, duration, folder, result]) group.add(row);
        page.add(group);
        const diagnosticGroup = new Adw.PreferencesGroup({title: 'Diagnostika',
            description: 'Exportuje verze, stav služby a číselné údaje přenosu. Neobsahuje názvy souborů, osobní cesty, jména zařízení, adresy ani identitu.'});
        const diagnosticRow = new Adw.ActionRow({title: 'Report pro hlášení chyby'});
        const exportButton = new Gtk.Button({label: 'Uložit diagnostiku…', valign: Gtk.Align.CENTER});
        diagnosticRow.add_suffix(exportButton);
        diagnosticGroup.add(diagnosticRow);
        page.add(diagnosticGroup);
        window.add(page);
        let selectedFolder = null;
        save.sensitive = choose.sensitive = name.sensitive = duration.sensitive = false;
        const showError = error => {if (!closed) result.subtitle = error.message;};
        const dismissed = error => error.matches?.(Gtk.DialogError, Gtk.DialogError.DISMISSED)
            || error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED);
        run([CONTROL, 'status'], cancellable).then(output => {
            if (closed) return;
            const state = JSON.parse(output);
            const prefs = state.preferences;
            name.text = prefs.receiver_name;
            duration.selected = [0, 300, 600].indexOf(prefs.duration_seconds);
            selectedFolder = prefs.download_dir;
            folder.subtitle = selectedFolder;
            save.sensitive = choose.sensitive = name.sensitive = duration.sensitive = true;
        }).catch(showError);
        choose.connect('clicked', () => {
            const dialog = new Gtk.FileDialog({title: 'Složka pro přijaté soubory'});
            if (selectedFolder) dialog.initial_folder = Gio.File.new_for_path(selectedFolder);
            dialog.select_folder(window, cancellable, (source, response) => {
                try {
                    const path = source.select_folder_finish(response)?.get_path();
                    if (!path || closed) return;
                    selectedFolder = path;
                    folder.subtitle = path;
                    result.subtitle = 'Změna připravená. Klikněte na Uložit nastavení.';
                } catch (error) {if (!dismissed(error)) showError(error);}
            });
        });
        save.connect('clicked', async () => {
            save.sensitive = false;
            try {
                await run([CONTROL, 'set-preferences', JSON.stringify({download_dir: selectedFolder,
                    receiver_name: name.text.trim(), duration_seconds: [0, 300, 600][duration.selected]})], cancellable);
                if (!closed) result.subtitle = 'Uloženo. Použije se při příštím zapnutí příjmu.';
            } catch (error) {showError(error);}
            finally {if (!closed) save.sensitive = true;}
        });
        exportButton.connect('clicked', () => {
            const dialog = new Gtk.FileDialog({title: 'Uložit diagnostiku',
                initial_name: 'gnome-airdrop-diagnostics.json'});
            dialog.save(window, cancellable, async (source, response) => {
                try {
                    const file = source.save_finish(response);
                    if (!file || closed) return;
                    if (!file.get_path()) throw new Error('Vyberte místní soubor.');
                    const text = await run([CONTROL, 'diagnostics'], cancellable);
                    if (closed) return;
                    file.replace_contents(new TextEncoder().encode(text), null, false,
                        Gio.FileCreateFlags.PRIVATE, cancellable);
                    diagnosticRow.subtitle = 'Diagnostika uložená.';
                } catch (error) {
                    if (!closed && !dismissed(error)) diagnosticRow.subtitle = error.message;
                }
            });
        });
    }
}
