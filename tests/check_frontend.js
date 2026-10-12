const NativeGLib = imports.gi.GLib;
const requests = [];
const notifications = [];
const openedFolders = [];
let currentState = {installed: true, state: 'inactive', receiving: false,
    download_dir: '/tmp/downloads', receipt: null};
let timerId = 0;
const GLib = {
    PRIORITY_DEFAULT: 0, SOURCE_REMOVE: false, SOURCE_CONTINUE: true,
    FileTest: {IS_EXECUTABLE: 1},
    file_test: () => true,
    timeout_add_seconds: () => ++timerId,
    source_remove: () => {},
    markup_escape_text: text => text.replaceAll('<', '&lt;'),
};
const Gio = {
    File: {new_for_path: path => ({get_uri: () => 'file://' + path})},
    AppInfo: {launch_default_for_uri: uri => openedFolders.push(uri)},
    SubprocessFlags: {STDOUT_PIPE: 1, STDERR_PIPE: 2},
    Cancellable: class {cancel() {}},
    Subprocess: {new(argv) {
        requests.push(argv);
        return {
            force_exit() {}, get_successful: () => true,
            communicate_utf8_async(_input, _cancel, callback) {
                Promise.resolve().then(() => callback(this, null));
            },
            communicate_utf8_finish() {return [true, JSON.stringify(currentState), ''];},
        };
    }},
};
class Item {
    constructor(text, _params) {this.label = {text}; this.callbacks = {};}
    connect(signal, callback) {this.callbacks[signal] = callback;}
    setSensitive(value) {this.sensitive = value;}
    setToggleState(value) {
        if (this.state === value) return;
        this.state = value;
        this.callbacks.toggled?.(this, value);
    }
}
const PopupMenu = {PopupSubMenuMenuItem: class extends Item {constructor(...args) {super(...args); this.menu = {addMenuItem() {}};}}, PopupSwitchMenuItem: Item, PopupMenuItem: Item, PopupSeparatorMenuItem: Item};
const PanelMenu = {Button: class {
    constructor(...args) {this._init(...args);}
    _init() {this.menu = {addMenuItem() {}};}
    add_child() {} destroy() {}
}};
const GObject = {registerClass: value => value};
const St = {Icon: class {constructor(options) {Object.assign(this, options);}}};
const Main = {messageTray: {add() {}}, panel: {addToStatusArea() {}}, notify(...args) {notifications.push(args);}};
const MessageTray = {
    PrivacyScope: {USER: 0},
    Source: class {connect() {} addNotification(n) {notifications.push(n);} destroy() {}},
    Notification: class {constructor(options) {Object.assign(this, options); this.actions = [];}
        addAction(label, callback) {this.actions.push({label, callback});}
    },
};
class Extension {constructor() {this.uuid = 'test';}}
const [, bytes] = NativeGLib.file_get_contents(
    imports.system.programPath.replace(/tests\/check_frontend.js$/, 'extension/extension.js'));
const source = imports.byteArray.toString(bytes).replace(/^import .*;\n/gm, '')
    .replace('export default class', 'class');
const [, statusBytes] = NativeGLib.file_get_contents(
    imports.system.programPath.replace(/tests\/check_frontend.js$/, 'extension/status.js'));
const Status = new Function(imports.byteArray.toString(statusBytes).replace(/^export /gm, '') +
    '\nreturn {transferText, errorMessage, bytes, durationLabel, windowText};')();
const App = new Function('MessageTray', 'global', 'Status', 'Gio', 'GLib', 'GObject', 'St', 'Extension', 'Main', 'PanelMenu', 'PopupMenu',
    source + '\nreturn GnomeAirDropExtension;')(
    MessageTray, {create_app_launch_context() {}}, Status, Gio, GLib, GObject, St, Extension, Main, PanelMenu, PopupMenu);
const tick = async () => {for (let index = 0; index < 8; index++) await Promise.resolve();};
const check = (condition, text) => {if (!condition) throw new Error(text);};
const loop = new NativeGLib.MainLoop(null, false);
(async () => {
    const extension = new App();
    extension.enable();
    await tick();
    check(requests.filter(argv => argv[0] === '/usr/bin/pkexec').length === 0,
        'Loading state must not trigger a privileged action');
    currentState = {...currentState, state: 'active', receiving: true};
    await extension._refresh();
    check(extension._indicator.toggle.state === true, 'Active service should set the switch');
    check(requests.filter(argv => argv[0] === '/usr/bin/pkexec').length === 0,
        'Programmatic toggled event must not start the service');
    currentState = {...currentState, transfer: {phase: 'receiving', filename: 'photo.jpg',
        file_count: 1, wire_bytes: 1024, total_wire_bytes: null, bytes_per_second: 512}};
    await extension._refresh();
    check(extension._indicator.progress.label.text.includes('kB'), 'Byte count should be shown');
    check(!extension._indicator.progress.label.text.includes('%'), 'Unknown wire total must not invent percentages');
    currentState.transfer.total_wire_bytes = 2048;
    await extension._refresh();
    check(extension._indicator.progress.label.text.includes('50 %'), 'Known wire total can show percentage');
    currentState.transfer.phase = 'verifying';
    await extension._refresh();
    check(extension._indicator.progress.label.text.includes('Ověřuji'), 'Verification must be visible');
    currentState.transfer.last_result = {id: 'finished', phase: 'completed', file_count: 1, filename: '<test>.pdf', download_dir: '/tmp/actual-received'};
    await extension._refresh();
    await extension._refresh();
    check(notifications.length === 1, 'A received file should notify exactly once');
    check(notifications[0].actions.length === 1, 'Success notification must offer a folder action');
    check(notifications[0].useBodyMarkup === false, 'Filenames must remain plain text');
    notifications[0].actions[0].callback();
    check(openedFolders[0] === 'file:///tmp/actual-received', 'Action opens the receiving folder');
    currentState.transfer.last_result = {id: 'failed', phase: 'error', error: 'timeout'};
    await extension._refresh();
    await extension._refresh();
    check(notifications.length === 2, 'Failure notification is deduplicated');
    check(notifications[1].body.includes('znovu'), 'Failure offers a useful next step');
    check(Status.windowText({ends_at: 120}, 61) === 'Zbývá 0:59', 'Countdown shows remaining duration');
    check(Status.windowText({ends_at: 60}, 61).includes('dokončení'), 'Expired session describes graceful drain');
    await extension._change(false);
    await tick();
    const actions = requests.filter(argv => argv[0] === '/usr/bin/pkexec');
    check(actions.length === 1 && actions[0][2] === 'stop', 'User stop should invoke one action');
    extension.disable();
    const before = requests.length;
    await extension._refresh();
    check(requests.length === before, 'Disabled extension must stop polling');
    print('GNOME switch, notifications, stop action and disable checks OK');
})().then(() => loop.quit()).catch(error => {printerr(error.stack); imports.system.exit(1);});
loop.run();
