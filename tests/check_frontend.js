const NativeGLib = imports.gi.GLib;
const requests = [];
const notifications = [];
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
const PopupMenu = {PopupSwitchMenuItem: Item, PopupMenuItem: Item, PopupSeparatorMenuItem: Item};
const PanelMenu = {Button: class {
    constructor(...args) {this._init(...args);}
    _init() {this.menu = {addMenuItem() {}};}
    add_child() {} destroy() {}
}};
const GObject = {registerClass: value => value};
const St = {Icon: class {constructor(options) {Object.assign(this, options);}}};
const Main = {panel: {addToStatusArea() {}}, notify(...args) {notifications.push(args);}};
class Extension {constructor() {this.uuid = 'test';}}
const [, bytes] = NativeGLib.file_get_contents(
    imports.system.programPath.replace(/tests\/check_frontend.js$/, 'extension/extension.js'));
const source = imports.byteArray.toString(bytes).replace(/^import .*;\n/gm, '')
    .replace('export default class', 'class');
const App = new Function('Gio', 'GLib', 'GObject', 'St', 'Extension', 'Main', 'PanelMenu', 'PopupMenu',
    source + '\nreturn GnomeAirDropExtension;')(
    Gio, GLib, GObject, St, Extension, Main, PanelMenu, PopupMenu);
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
    currentState = {...currentState, receipt: {id: 'finished', files: ['test.pdf']}};
    await extension._refresh();
    await extension._refresh();
    check(notifications.length === 1, 'A received file should notify exactly once');
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
