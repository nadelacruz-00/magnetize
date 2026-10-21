// Build the real preferences window outside GNOME Shell and save each page
// as a PNG, with settings kept in memory so nothing on the system changes.
//
// S=$(mktemp -d); cp -r metadata.json prefs.js actions.js presets.js schemas $S/
// glib-compile-schemas $S/schemas
// GI_TYPELIB_PATH=/usr/lib/gnome-shell/girepository-1.0 LD_LIBRARY_PATH=/usr/lib/gnome-shell \
//     GSETTINGS_BACKEND=memory gjs -m tests/prefs-screenshot.js $S out-dir
import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

Gio.Resource.load('/usr/share/gnome-shell/org.gnome.Shell.Extensions.src.gresource')._register();

const [extDir, outDir] = ARGV;
const dir = Gio.File.new_for_path(extDir);
const metadata = JSON.parse(new TextDecoder().decode(dir.get_child('metadata.json').load_contents(null)[1]));
Object.assign(metadata, {dir, path: dir.get_path()});
const {default: Prefs} = await import(`file://${dir.get_path()}/prefs.js`);

const app = new Adw.Application({application_id: 'dev.magnetize.PrefsScreenshot'});
app.connect('activate', () => {
    const window = new Adw.PreferencesWindow({application: app});
    new Prefs(metadata).fillPreferencesWindow(window);
    window.present();

    const pages = ['general', 'shortcuts'];
    const next = () => {
        const page = pages.shift();
        if (!page) {
            app.quit();
            return GLib.SOURCE_REMOVE;
        }
        window.visible_page_name = page;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 700, () => {
            const snapshot = new Gtk.Snapshot();
            new Gtk.WidgetPaintable({widget: window}).snapshot(snapshot, window.get_width(), window.get_height());
            window.get_native().get_renderer().render_texture(snapshot.to_node(), null)
                .save_to_png(`${outDir}/${page}.png`);
            print(`saved ${outDir}/${page}.png`);
            return next();
        });
        return GLib.SOURCE_REMOVE;
    };
    next();
});
app.run([]);
